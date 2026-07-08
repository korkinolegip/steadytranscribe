"""Страница «Расшифровка файлов».

UX: файл → чистый текст. На готовом результате — кнопка «Разделить по собеседникам»,
редактирование текста, имена собеседников, сохранение правок в историю.
"""
import json
import os
import re
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea,
    QTextEdit, QVBoxLayout, QWidget,
)

from ...core import convert, diarize
from ...core.transcriber import Transcriber, TranscriptionResult
from ...core.worker import DiarizationWorker, TranscriptionWorker
from ...storage import history, settings as settings_store, timings
from ..minigame import MiniGame
from ..widgets import card

# ниже этого порога уверенности расшифровку помечаем «проверьте текст»
LOW_CONFIDENCE = 0.6


def _format_size(path: str) -> str:
    size = os.path.getsize(path)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


class SpeakerCountDialog(QDialog):
    """Сколько собеседников на записи (для точного разделения)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Разделить по собеседникам")
        lay = QVBoxLayout(self)
        hint = QLabel("Укажите точное число людей, которые говорят на записи.\n"
                      "Это важно: программа узнаёт голоса по тембру, и с точным числом "
                      "разделение получается корректным.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.box = QComboBox()
        for n in range(2, 11):
            self.box.addItem(f"{n} человека" if n < 5 else f"{n} человек", n)
        self.box.addItem("Не знаю — определить автоматически (менее точно)", 0)
        self.box.setCurrentIndex(0)  # по умолчанию 2 — самый частый случай
        form = QFormLayout()
        form.addRow("Собеседников:", self.box)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Разделить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def value(self) -> int:
        return self.box.currentData()


class SpeakerNamesDialog(QDialog):
    """Переименование «Собеседник N» в реальные имена."""

    def __init__(self, speakers: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Имена собеседников")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for sp in speakers:
            edit = QLineEdit()
            edit.setPlaceholderText("Например: Ирина")
            form.addRow(f"{sp}:", edit)
            self.edits[sp] = edit
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Применить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def mapping(self) -> dict[str, str]:
        return {sp: e.text().strip() for sp, e in self.edits.items() if e.text().strip()}


class TranscribePage(QWidget):
    history_changed = Signal()

    def __init__(self, transcriber: Transcriber):
        super().__init__()
        self.transcriber = transcriber
        self.worker: TranscriptionWorker | None = None
        self.diar_worker: DiarizationWorker | None = None
        self.selected_file: str | None = None
        self.result_name: str | None = None       # имя файла, сохраняется после авто-очистки
        self.result: TranscriptionResult | None = None
        self._est_total: float = 0.0              # текущая оценка длительности операции, сек
        self.wav_path: str | None = None          # для диаризации после расшифровки
        self.plain_text: str | None = None        # исходный текст (без разделения)
        self.dialogue_text: str | None = None     # текст по собеседникам
        self.showing_dialogue = False
        self.entry_id: str | None = None          # запись в истории для сохранения правок
        self.setAcceptDrops(True)
        self._build()
        self._refresh()

    # ---------- интерфейс ----------

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(24, 20, 24, 24)
        col.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        title = QLabel("Расшифровка файлов")
        title.setObjectName("h1")
        sub = QLabel("Перетащите аудио- или видеофайл. Всё распознаётся локально, без интернета.")
        sub.setObjectName("subtitle")
        col.addWidget(title)
        col.addWidget(sub)

        # --- карточка файла ---
        self.file_card, fc = card()
        self.drop_zone = QLabel()
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setAlignment(Qt.AlignCenter)
        self.drop_zone.setMinimumHeight(120)
        self.drop_zone.setTextFormat(Qt.RichText)
        self.drop_zone.mousePressEvent = lambda e: self._pick_file()
        fc.addWidget(self.drop_zone)
        row = QHBoxLayout()
        self.file_label = QLabel()
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setFixedWidth(32)
        self.clear_btn.clicked.connect(self._reset_file)
        row.addWidget(self.file_label)
        row.addStretch()
        row.addWidget(self.clear_btn)
        fc.addLayout(row)
        self.go_btn = QPushButton("🎙  Расшифровать")
        self.go_btn.setObjectName("primary")
        self.go_btn.clicked.connect(self._start)
        fc.addWidget(self.go_btn)
        # пока модель не скачана — кнопка неактивна, подсказка объясняет почему
        self.model_wait = QLabel("⏳ Модель распознавания ещё скачивается — кнопка "
                                 "«Расшифровать» включится сама, как только всё будет готово.")
        self.model_wait.setObjectName("warn")
        self.model_wait.setWordWrap(True)
        self.model_wait.hide()
        fc.addWidget(self.model_wait)
        col.addWidget(self.file_card)
        # автоактивация: проверяем готовность модели, пока она не появится
        self._model_poll = QTimer(self)
        self._model_poll.setInterval(2000)
        self._model_poll.timeout.connect(self._check_model_ready)
        if not self._model_ready():
            self._model_poll.start()

        # --- прогресс ---
        self.progress_card, pc = card()
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.status = QLabel()
        self.time_label = QLabel()          # прошло / осталось
        self.time_label.setObjectName("hint")
        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.clicked.connect(self._cancel)
        prow = QHBoxLayout()
        prow.addWidget(self.status)
        prow.addStretch()
        prow.addWidget(self.time_label)
        prow.addWidget(self.cancel_btn)
        pc.addWidget(self.bar)
        pc.addLayout(prow)
        col.addWidget(self.progress_card)
        # мини-игра на время ожидания (как динозаврик в Chrome) — под прогрессом
        self.game = MiniGame()
        self.game.hide()
        col.addWidget(self.game)

        # таймер реального времени для ETA
        self._elapsed = QTimer(self)
        self._elapsed.setInterval(1000)
        self._elapsed.timeout.connect(self._tick)
        self._start_time = None
        self._last_progress = 0.0

        # --- ошибка ---
        self.error_card, ec = card()
        self.error_card.setObjectName("errorCard")
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("errorText")
        hide = QPushButton("Скрыть")
        hide.clicked.connect(self.error_card.hide)
        erow = QHBoxLayout()
        erow.addWidget(self.error_label, stretch=1)
        erow.addWidget(hide, alignment=Qt.AlignTop)
        ec.addLayout(erow)
        col.addWidget(self.error_card)

        # --- результат ---
        self.result_card, rc = card("Расшифровка готова")
        # поле имени — можно назвать расшифровку понятно (сохранится в историю)
        name_row = QHBoxLayout()
        name_lbl = QLabel("Название:")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например: Планёрка отдела 8 июля")
        self.name_edit.editingFinished.connect(self._rename_entry)
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.name_edit, stretch=1)
        rc.addLayout(name_row)
        self.stats = QLabel()
        self.stats.setObjectName("stats")
        rc.addWidget(self.stats)
        # предупреждение, если распознавание неуверенное — пользователю стоит проверить текст
        self.lowconf = QLabel("⚠️  Распознавание неуверенное — проверьте текст, "
                              "местами возможны ошибки.")
        self.lowconf.setObjectName("warn")
        self.lowconf.setWordWrap(True)
        self.lowconf.hide()
        rc.addWidget(self.lowconf)

        btns = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Копировать")
        self.copy_btn.clicked.connect(self._copy_current)
        self.export_btn = QPushButton("💾 Экспорт")
        self.export_btn.clicked.connect(self._export_result)
        self.split_btn = QPushButton("👥 Разделить по собеседникам")
        self.split_btn.clicked.connect(self._split_speakers)
        self.names_btn = QPushButton("✏️ Имена")
        self.names_btn.clicked.connect(self._rename_speakers)
        self.toggle_btn = QPushButton("Исходный")
        self.toggle_btn.clicked.connect(self._toggle_view)
        self.save_btn = QPushButton("💾 В историю")
        self.save_btn.clicked.connect(self._save_edits)
        for b in (self.copy_btn, self.export_btn, self.split_btn,
                  self.names_btn, self.toggle_btn, self.save_btn):
            btns.addWidget(b)
        btns.addStretch()
        rc.addLayout(btns)

        edit_hint = QLabel("Текст можно править прямо здесь — затем «Сохранить правки».")
        edit_hint.setObjectName("hint")
        rc.addWidget(edit_hint)

        self.text = QTextEdit()
        self.text.setReadOnly(False)          # правки разрешены
        self.text.setMinimumHeight(220)
        self.text.setMaximumHeight(360)
        rc.addWidget(self.text)
        col.addWidget(self.result_card)
        col.addStretch()

        self.toast = QLabel("Скопировано!", self)
        self.toast.setObjectName("toast")
        self.toast.hide()

    def _model_ready(self) -> bool:
        from ...core import models
        s = settings_store.load()
        key = s.get("model", models.DEFAULT_MODEL)
        # ЦЕЛАЯ модель, а не просто «файлы есть»: оборванная загрузка оставляла
        # полный model.bin без метки целостности → кнопка включалась → ошибка
        # «модель повреждена» (случай Анастасии, 08.07)
        return models.is_downloaded(key) and models.is_intact(key)

    def _check_model_ready(self):
        if self._model_ready():
            self._model_poll.stop()
            self._refresh()          # модель докачалась — кнопка включается сама
            return
        # модель скачана не полностью (обрыв сети/закрыли программу) —
        # ДОКАЧИВАЕМ САМИ с места обрыва, пользователь ничего не делает
        from ...core import models
        s = settings_store.load()
        key = s.get("model", models.DEFAULT_MODEL)
        if (models.is_downloaded(key) and not models.is_intact(key)
                and getattr(self, "_resume_worker", None) is None):
            from ...storage import analytics
            analytics.track("model_autoresume")
            from .models import DownloadWorker
            self._resume_worker = DownloadWorker(key, self)
            self._resume_worker.done.connect(
                lambda: setattr(self, "_resume_worker", None))
            self._resume_worker.failed.connect(
                lambda _m: setattr(self, "_resume_worker", None))
            self._resume_worker.start()
            self.model_wait.setText("⏳ Модель докачивается после обрыва — кнопка "
                                    "«Расшифровать» включится сама, ничего делать не нужно.")

    def _refresh(self):
        busy = ((self.worker and self.worker.isRunning())
                or (self.diar_worker and self.diar_worker.isRunning()))
        model_ready = self._model_ready()
        self.model_wait.setVisible(not model_ready)
        if self.selected_file:
            self.drop_zone.hide()
            est = getattr(self, "_file_estimate", "")
            txt = f"📄  {os.path.basename(self.selected_file)}   ({_format_size(self.selected_file)})"
            if est:
                txt += f"\n{est}"
            self.file_label.setText(txt)
            self.file_label.show()
            self.clear_btn.show()
            self.go_btn.show()
            self.go_btn.setEnabled(not busy and model_ready)
        else:
            self.drop_zone.setText(
                "<div style='font-size:15px'>⬆️<br><b>Выберите аудио- или видеофайл</b><br>"
                f"<span style='font-size:11px;color:#9A9A9A'>{convert.FORMATS_DESCRIPTION}</span></div>")
            self.drop_zone.show()
            self.file_label.hide()
            self.clear_btn.hide()
            self.go_btn.hide()
        self.progress_card.setVisible(bool(busy))
        self.error_card.hide()
        has_result = self.result is not None
        self.result_card.setVisible(has_result)
        if has_result:
            speed = self.result.duration / self.result.processing_time if self.result.processing_time else 0
            words = len((self.result.text or "").split())
            self.stats.setText(
                f"🕐 {self._fmt_long(self.result.duration)}    📝 {words} слов    "
                f"✅ {self.result.confidence * 100:.0f}%    ⚡ {speed:.1f}×")
            self.lowconf.setVisible(self.result.confidence < LOW_CONFIDENCE)
            can_split = diarize.is_available() and self.wav_path and not busy
            self.split_btn.setVisible(bool(can_split) and self.dialogue_text is None)
            self.names_btn.setVisible(self.dialogue_text is not None and self.showing_dialogue)
            self.toggle_btn.setVisible(self.dialogue_text is not None)
            self.toggle_btn.setText("Исходный" if self.showing_dialogue else "По собеседникам")

    def _set_text(self, text: str):
        self.text.setPlainText(text)

    # ---------- выбор файла ----------

    def _pick_file(self):
        exts = " ".join(f"*.{e}" for e in sorted(convert.SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Выберите аудио- или видеофайл", "",
                                              f"Аудио и видео ({exts})")
        if path:
            self.set_file(path)

    def set_file(self, path: str):
        if not convert.is_supported(path):
            self._show_error(convert.FORMATS_DESCRIPTION, auto_hide=True)
            return
        self._cleanup_wav()
        self.selected_file = path
        self.result = None
        self.result_name = None
        self.plain_text = self.dialogue_text = None
        self._original_text = ""
        self.showing_dialogue = False
        self.entry_id = None
        # оценка длительности и времени расшифровки
        self._file_estimate = self._estimate(path)
        self._refresh()

    def _estimate(self, path: str) -> str:
        """Оценка времени расшифровки. Коэффициент берётся из базы времён —
        со временем, накопив реальные замеры, прогноз становится точным."""
        dur = convert.probe_duration(path)
        self._est_seconds = 0.0
        if dur <= 0:
            return ""
        model = settings_store.load().get("model", "large-v3-turbo")
        est = timings.estimate_transcription(model, dur)
        self._est_seconds = est
        return (f"Длительность: {self._fmt_long(dur)}. "
                f"Расшифровка займёт примерно {self._fmt_long(est)}.")

    def _reset_file(self):
        self._cleanup_wav()
        self.selected_file = None
        self.result = None
        self.result_name = None
        self.plain_text = self.dialogue_text = None
        self._original_text = ""
        self.showing_dialogue = False
        self.entry_id = None
        self._refresh()

    def _cleanup_wav(self):
        if self.wav_path and os.path.exists(self.wav_path):
            try:
                os.remove(self.wav_path)
            except OSError:
                pass
        self.wav_path = None

    # ---------- транскрипция ----------

    def _start(self):
        if not self.selected_file or (self.worker and self.worker.isRunning()):
            return
        self.result = None
        self.dialogue_text = None
        self.showing_dialogue = False
        self._cleanup_wav()
        self.settings = settings_store.load()
        # parent=self ОБЯЗАТЕЛЕН: без родителя Python мог удалить QThread, пока
        # тот ещё завершается (особенно при отмене) → мгновенный крах приложения
        self.worker = TranscriptionWorker(self.transcriber, self.selected_file,
                                          self.settings, parent=self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        import time
        self._start_time = time.monotonic()
        self._last_progress = 0.0
        self._est_total = getattr(self, "_est_seconds", 0.0) or 60.0
        self.cancel_btn.setEnabled(True)
        self._elapsed.start()
        self.worker.start()
        self._refresh()
        self.progress_card.show()
        self.game.begin()          # таймкиллер на время ожидания

    def _cancel(self):
        # мгновенная реакция: гасим кнопку и сразу шлём сигнал отмены
        # (ffmpeg убивается принудительно, процесс разделения — тоже)
        from ...storage import analytics
        analytics.track("cancel")
        self.cancel_btn.setEnabled(False)
        self.status.setText("Отмена…")
        for w in (self.worker, self.diar_worker):
            if w:
                w.cancel()

    @staticmethod
    def _fmt(sec: float) -> str:
        sec = max(int(sec), 0)
        return f"{sec // 60}:{sec % 60:02d}"

    @staticmethod
    def _fmt_long(sec: float) -> str:
        """Человеческий формат: «11 мин 15 с», «45 с», «1 ч 3 мин»."""
        sec = max(int(round(sec)), 0)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h} ч {m} мин" if m else f"{h} ч"
        if m:
            return f"{m} мин {s} с" if s else f"{m} мин"
        return f"{s} с"

    def _tick(self):
        import time
        if not self._start_time:
            return
        # АВТО-регулировка нагрузки: окно активно (пользователь ждёт результат) →
        # обычный приоритет, быстрее; пользователь ушёл работать в другое приложение →
        # пониженный приоритет, уступаем ему ресурсы. Всё само, без настроек.
        from ...core import priority
        win = self.window()
        active = bool(win and win.isActiveWindow())
        priority.set_background(not active)
        # то же — для подпроцесса разделения по собеседникам: пока пользователь
        # ждёт у окна, он работает на полной скорости (иначе казался очень долгим)
        if self.diar_worker is not None:
            pid = self.diar_worker.proc_pid()
            if pid:
                priority.set_pid_background(pid, not active)

        elapsed = time.monotonic() - self._start_time
        p = self._last_progress
        # СТАБИЛЬНЫЙ ETA: не считаем «остаток» по мгновенному проценту (он скачет),
        # а ведём обратный отсчёт от предварительной оценки и МЯГКО подтягиваем её
        # к факту (EMA). Так цифра плавно уменьшается, а не прыгает вверх-вниз.
        if p > 0.05 and self._est_total > 0:
            measured = elapsed / p
            self._est_total += 0.15 * (measured - self._est_total)
        remaining = max(self._est_total - elapsed, 1.0)
        self.time_label.setText(
            f"прошло {self._fmt(elapsed)} · осталось ~{self._fmt(remaining)}")

    def _on_progress(self, status: str, value: float):
        self.status.setText(status)
        self.bar.setValue(int(value * 100))
        self._last_progress = value

    def _on_done(self, result: TranscriptionResult, wav_path: str):
        self.worker = None
        self._elapsed.stop()
        self.time_label.setText("")
        self.wav_path = wav_path
        self.result = result
        name = os.path.basename(self.selected_file or "")
        if not result.text.strip():
            self.result = None
            self._cleanup_wav()
            self._reset_file()
            self.game.hide_now()
            self._show_error("Речь не обнаружена — файл тишины или без голоса.")
            return
        self.game.finish("Расшифровка готова — пора работать!")
        # запоминаем реальное время расшифровки — прогноз следующих файлов точнее
        timings.record_transcription(self.settings["model"], result.duration,
                                     result.processing_time)
        from ...storage import analytics
        ext = os.path.splitext(self.selected_file or "")[1].lstrip(".").lower()
        analytics.track("transcribe", audio_sec=int(result.duration),
                        proc_sec=int(result.processing_time),
                        words=len(result.text.split()), model=self.settings["model"],
                        confidence=round(result.confidence, 2), ext=ext)
        self._notify_done(name)
        self.plain_text = result.text
        self._original_text = result.text     # для «правки → словарь»
        entry = history.add(name, result.duration,
                            result.processing_time, result.confidence, result.text,
                            self.settings["model"], result.language,
                            limit=int(self.settings.get("history_limit", 50)))
        self.entry_id = entry.id if entry else None
        self.name_edit.setText(name)
        self._set_text(result.text)
        # АВТО-ОЧИСТКА: файл больше не нужен — убираем его, чтобы можно было сразу
        # перетащить следующий (расшифровка уже готова и показана ниже).
        self.result_name = name
        self.selected_file = None
        self._file_estimate = ""
        self._refresh()
        self.history_changed.emit()

    def _rename_entry(self):
        name = self.name_edit.text().strip()
        if self.entry_id and name:
            history.rename(self.entry_id, name)
            self.history_changed.emit()

    def _on_failed(self, message: str):
        self.worker = None
        self.diar_worker = None
        self._elapsed.stop()
        self.time_label.setText("")
        self.cancel_btn.setEnabled(True)
        self.game.hide_now()
        self._refresh()
        # отмена — это не ошибка: тихо возвращаемся, без красной плашки
        if "Отменено" in message:
            return
        self._show_error(message)

    def _notify_done(self, name: str):
        """Системное уведомление, если окно свёрнуто/неактивно — «файл готов»."""
        win = self.window()
        if win and win.isActiveWindow():
            return
        from .. import notify
        notify.send(getattr(win, "tray", None), "Расшифровка готова",
                    f"Файл «{name}» распознан — можно открыть и посмотреть.", 5000)

    # ---------- диаризация по кнопке ----------

    def _split_speakers(self):
        if not (self.result and self.wav_path and self.result.words):
            self._show_error("Для разделения нужно заново расшифровать файл.")
            return
        dlg = SpeakerCountDialog(self)
        if not dlg.exec():
            return
        # освобождаем модель распознавания из памяти — чтобы разделению хватило RAM
        # (иначе на длинных файлах Windows может «убить» приложение из-за нехватки памяти)
        self.transcriber.unload()
        self._diar_speakers = dlg.value()
        # parent=self — см. комментарий у TranscriptionWorker (защита от краха при отмене)
        self.diar_worker = DiarizationWorker(self.wav_path, self.result.words,
                                             dlg.value(), parent=self)
        self.diar_worker.progress.connect(self._on_progress)
        self.diar_worker.finished_ok.connect(self._on_diarized)
        self.diar_worker.failed.connect(self._on_failed)
        # таймер прошло/осталось — разделение тоже небыстрое, показываем прогресс времени
        import time
        self._start_time = time.monotonic()
        self._last_progress = 0.0
        self._est_total = timings.estimate_diarization(self.result.duration or 0) or 30.0
        self.cancel_btn.setEnabled(True)
        self._elapsed.start()
        self.diar_worker.start()
        self._refresh()
        self.progress_card.show()
        self.game.begin()          # таймкиллер и на время разделения

    def _on_diarized(self, dialogue: str):
        self.diar_worker = None
        self._elapsed.stop()
        self.time_label.setText("")
        # запоминаем время разделения — прогноз следующих файлов точнее
        if self._start_time and self.result:
            import time
            elapsed = time.monotonic() - self._start_time
            timings.record_diarization(self.result.duration or 0, elapsed)
            from ...storage import analytics
            analytics.track("diarize", audio_sec=int(self.result.duration or 0),
                            proc_sec=int(elapsed),
                            speakers=getattr(self, "_diar_speakers", 0))
        self.dialogue_text = dialogue
        self.showing_dialogue = True
        self._set_text(dialogue)
        self.game.finish("Собеседники определены — пора работать!")
        self._refresh()

    def _toggle_view(self):
        self._stash_edits()
        self.showing_dialogue = not self.showing_dialogue
        self._set_text(self.dialogue_text if self.showing_dialogue else (self.plain_text or ""))
        self._refresh()

    def _stash_edits(self):
        """Правки в поле сохраняем в соответствующую версию текста."""
        current = self.text.toPlainText()
        if self.showing_dialogue:
            self.dialogue_text = current
        else:
            self.plain_text = current

    def _rename_speakers(self):
        self._stash_edits()
        speakers = sorted(set(re.findall(r"Собеседник \d+", self.dialogue_text or "")),
                          key=lambda s: int(s.split()[-1]))
        if not speakers:
            return
        dlg = SpeakerNamesDialog(speakers, self)
        if dlg.exec():
            from ...storage import analytics
            analytics.track("rename_speakers")
            for sp, name in dlg.mapping().items():
                self.dialogue_text = self.dialogue_text.replace(f"{sp}:", f"{name}:")
            self._set_text(self.dialogue_text)

    # ---------- копирование/экспорт/сохранение ----------

    def _current_text(self) -> str:
        return self.text.toPlainText()

    def _copy_current(self):
        from ...storage import analytics
        analytics.track("copy_text")
        QGuiApplication.clipboard().setText(self._current_text())
        self.toast.adjustSize()
        self.toast.move(self.width() - self.toast.width() - 24, 12)
        self.toast.show()
        QTimer.singleShot(2000, self.toast.hide)

    def _save_edits(self):
        self._stash_edits()
        if self.entry_id:
            history.update_text(self.entry_id, self._current_text())
            self.history_changed.emit()
            from ...storage import analytics
            analytics.track("save_history")
            added = self._learn_from_edits()
            msg = f"Сохранено · +{added} слов в словарь" if added else "Сохранено в историю"
            self.toast.setText(msg)
            self.toast.adjustSize()
            self.toast.move(self.width() - self.toast.width() - 24, 12)
            self.toast.show()
            QTimer.singleShot(2500, lambda: (self.toast.hide(), self.toast.setText("Скопировано!")))

    def _learn_from_edits(self) -> int:
        """Слова, которые пользователь вписал/исправил вручную (и которых не было в
        исходном распознавании), добавляем в словарь — имена, названия, термины.
        Так программа запомнит правильное написание для будущих расшифровок."""
        original = getattr(self, "_original_text", "") or ""
        edited = self.plain_text or ""
        if not original or not edited:
            return 0

        def tokens(text):
            return re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-]{2,}", text)

        orig_lower = {w.lower() for w in tokens(original)}
        new_words = []
        for w in tokens(edited):
            if w.lower() in orig_lower:
                continue
            # берём только то, что похоже на имя/название/термин, а не обычное слово:
            # с заглавной буквы, латиница (бренды) или CamelCase
            looks_named = (w[0].isupper() or re.search(r"[A-Za-z]", w)
                           or any(c.isupper() for c in w[1:]))
            if looks_named and w not in new_words:
                new_words.append(w)
        new_words = new_words[:15]
        if not new_words:
            return 0

        s = settings_store.load()
        existing = [x.strip() for x in re.split(r"[\n,]", s.get("initial_prompt", "")) if x.strip()]
        existing_lower = {x.lower() for x in existing}
        fresh = [w for w in new_words if w.lower() not in existing_lower]
        if not fresh:
            return 0
        s["initial_prompt"] = "\n".join(existing + fresh)
        settings_store.save(s)
        return len(fresh)

    def _export_result(self):
        from ...storage import analytics
        analytics.track("export")
        if self.result and self.result_name:
            export_transcription(self, self.result_name,
                                 self._current_text(), self.result.duration,
                                 self.result.processing_time, self.result.confidence,
                                 datetime.now())

    def _show_error(self, message: str, auto_hide: bool = False):
        from ...storage import analytics
        analytics.track("error_shown", msg=message[:160])
        self.error_label.setText(f"⚠️  {message}")
        self.error_card.show()
        if auto_hide:
            QTimer.singleShot(3000, self.error_card.hide)

    # ---------- drag & drop ----------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.drop_zone.setProperty("hover", True)
            self.drop_zone.style().polish(self.drop_zone)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop_zone.setProperty("hover", False)
        self.drop_zone.style().polish(self.drop_zone)

    def dropEvent(self, event):
        self.drop_zone.setProperty("hover", False)
        self.drop_zone.style().polish(self.drop_zone)
        urls = event.mimeData().urls()
        if urls:
            self.set_file(urls[0].toLocalFile())


def export_transcription(parent, file_name: str, text: str, duration: float,
                         processing: float, confidence: float, timestamp: datetime):
    """Экспорт TXT/JSON в формате оригинала (общий для страниц)."""
    base = os.path.splitext(file_name)[0] or "transcription"
    path, chosen = QFileDialog.getSaveFileName(
        parent, "Экспорт расшифровки", f"{base}_transcript.txt",
        "Текст (*.txt);;JSON (*.json)")
    if not path:
        return
    as_json = path.endswith(".json") or "json" in chosen.lower()
    # ТОЛЬКО macOS: NSSavePanel не подменяет расширение при выборе фильтра
    # JSON — нормализуем сами, иначе получится «имя.txt» с JSON внутри.
    # На Windows диалог делает это сам; трогать путь после подтверждения
    # нельзя (обошли бы предупреждение о перезаписи).
    if sys.platform == "darwin" and as_json and not path.endswith(".json"):
        path = os.path.splitext(path)[0] + ".json"
    if as_json:
        payload = {"confidence": confidence, "duration": duration,
                   "fileName": file_name, "processingTime": processing,
                   "text": text, "timestamp": timestamp.isoformat()}
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        content = (f"Transcription: {file_name}\n"
                   f"Date: {timestamp.strftime('%d.%m.%Y %H:%M')}\n"
                   f"Duration: {duration:.1f} s\n"
                   f"Processing Time: {processing:.1f} s\n"
                   f"Confidence: {confidence * 100:.1f}%\n"
                   f"---\n\n{text}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
