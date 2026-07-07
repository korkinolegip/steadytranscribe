"""Страница «Расшифровка файлов» — карточки как в оригинале."""
import json
import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from ...core import convert, diarize
from ...core.transcriber import Transcriber, TranscriptionResult
from ...core.worker import TranscriptionWorker
from ...storage import history, settings as settings_store
from ..widgets import card


def _format_size(path: str) -> str:
    size = os.path.getsize(path)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


class TranscribePage(QWidget):
    history_changed = Signal()

    def __init__(self, transcriber: Transcriber):
        super().__init__()
        self.transcriber = transcriber
        self.worker: TranscriptionWorker | None = None
        self.selected_file: str | None = None
        self.result: TranscriptionResult | None = None
        self.setAcceptDrops(True)
        self._build()
        self._refresh()

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
        sub = QLabel("Перетащите аудио- или видеофайл. Всё распознаётся локально.")
        sub.setObjectName("subtitle")
        col.addWidget(title)
        col.addWidget(sub)

        # выбор файла
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
        # опция разделения по собеседникам
        diar_row = QHBoxLayout()
        self.split_check = QCheckBox("Разделять по собеседникам")
        self.split_check.setEnabled(diarize.is_available())
        self.split_check.toggled.connect(self._on_split_toggle)
        self.speakers_box = QComboBox()
        self.speakers_box.addItem("Определить автоматически", 0)
        for n in range(2, 9):
            self.speakers_box.addItem(f"{n} собеседника" if n < 5 else f"{n} собеседников", n)
        self.speakers_box.setEnabled(False)
        diar_row.addWidget(self.split_check)
        diar_row.addWidget(self.speakers_box)
        diar_row.addStretch()
        fc.addLayout(diar_row)
        diar_hint = QLabel("Каждая реплика будет подписана «Собеседник 1/2…». "
                           "Точность зависит от записи; работает локально, добавляет времени.")
        diar_hint.setObjectName("hint")
        diar_hint.setWordWrap(True)
        fc.addWidget(diar_hint)

        self.go_btn = QPushButton("🎙  Расшифровать")
        self.go_btn.setObjectName("primary")
        self.go_btn.clicked.connect(self._start)
        fc.addWidget(self.go_btn)
        col.addWidget(self.file_card)

        # прогресс
        self.progress_card, pc = card()
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.status = QLabel()
        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.clicked.connect(self._cancel)
        prow = QHBoxLayout()
        prow.addWidget(self.status)
        prow.addStretch()
        prow.addWidget(self.cancel_btn)
        pc.addWidget(self.bar)
        pc.addLayout(prow)
        col.addWidget(self.progress_card)

        # ошибка
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

        # результат
        self.result_card, rc = card("Расшифровка готова")
        self.stats = QLabel()
        self.stats.setObjectName("stats")
        rc.addWidget(self.stats)
        btns = QHBoxLayout()
        copy_btn = QPushButton("📋 Копировать")
        copy_btn.clicked.connect(lambda: self._copy(self.result.text if self.result else ""))
        export_btn = QPushButton("💾 Экспорт")
        export_btn.clicked.connect(self._export_result)
        btns.addWidget(copy_btn)
        btns.addWidget(export_btn)
        btns.addStretch()
        rc.addLayout(btns)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(180)
        self.text.setMaximumHeight(320)
        rc.addWidget(self.text)
        col.addWidget(self.result_card)
        col.addStretch()

        self.toast = QLabel("Скопировано!", self)
        self.toast.setObjectName("toast")
        self.toast.hide()

    def _refresh(self):
        busy = self.worker is not None and self.worker.isRunning()
        if self.selected_file:
            self.drop_zone.hide()
            self.file_label.setText(
                f"📄  {os.path.basename(self.selected_file)}   ({_format_size(self.selected_file)})")
            self.file_label.show()
            self.clear_btn.show()
            self.go_btn.show()
            self.go_btn.setEnabled(not busy)
        else:
            self.drop_zone.setText(
                "<div style='font-size:15px'>⬆️<br><b>Выберите аудио- или видеофайл</b><br>"
                f"<span style='font-size:11px;color:#9A9A9A'>{convert.FORMATS_DESCRIPTION}</span></div>")
            self.drop_zone.show()
            self.file_label.hide()
            self.clear_btn.hide()
            self.go_btn.hide()
        self.progress_card.setVisible(busy)
        self.error_card.hide()
        self.result_card.setVisible(self.result is not None)
        if self.result:
            speed = self.result.duration / self.result.processing_time if self.result.processing_time else 0
            self.stats.setText(
                f"🕐 {self.result.duration:.1f} с    ✅ {self.result.confidence * 100:.0f}%    ⚡ {speed:.1f}×")
            self.text.setPlainText(self.result.text)

    # ---- действия ----
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
        self.selected_file = path
        self.result = None
        self._refresh()

    def _reset_file(self):
        self.selected_file = None
        self.result = None
        self._refresh()

    def _on_split_toggle(self, checked: bool):
        self.speakers_box.setEnabled(checked)

    def _start(self):
        if not self.selected_file or (self.worker and self.worker.isRunning()):
            return
        self.result = None
        self.settings = settings_store.load()
        self.worker = TranscriptionWorker(
            self.transcriber, self.selected_file, self.settings,
            split_speakers=self.split_check.isChecked(),
            num_speakers=self.speakers_box.currentData())
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self._refresh()
        self.progress_card.show()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.status.setText("Отмена…")

    def _on_progress(self, status: str, value: float):
        self.status.setText(status)
        self.bar.setValue(int(value * 100))

    def _on_done(self, result: TranscriptionResult):
        self.result = result
        if not result.text.strip():
            self.result = None
            self.worker = None
            self._refresh()
            self._show_error("Речь не обнаружена — файл тишины или без голоса.")
            return
        history.add(os.path.basename(self.selected_file or ""), result.duration,
                    result.processing_time, result.confidence, result.text,
                    self.settings["model"], result.language,
                    limit=int(self.settings.get("history_limit", 50)))
        self.worker = None
        self._refresh()
        self.history_changed.emit()

    def _on_failed(self, message: str):
        self.worker = None
        self._refresh()
        self._show_error(message)

    def _show_error(self, message: str, auto_hide: bool = False):
        self.error_label.setText(f"⚠️  {message}")
        self.error_card.show()
        if auto_hide:
            QTimer.singleShot(3000, self.error_card.hide)

    def _copy(self, text: str):
        QGuiApplication.clipboard().setText(text)
        self.toast.adjustSize()
        self.toast.move(self.width() - self.toast.width() - 24, 12)
        self.toast.show()
        QTimer.singleShot(2000, self.toast.hide)

    def _export_result(self):
        if not (self.result and self.selected_file):
            return
        export_transcription(self, os.path.basename(self.selected_file), self.result.text,
                             self.result.duration, self.result.processing_time,
                             self.result.confidence, datetime.now())

    # ---- drag & drop ----
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
    if path.endswith(".json") or "json" in chosen.lower():
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
