"""Главное окно: карточки как в File Transcription из FluidVoice."""
import json
import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from ..core import convert
from ..core.transcriber import Transcriber, TranscriptionResult
from ..core.worker import TranscriptionWorker
from ..storage import history, settings as settings_store
from .settings_dialog import SettingsDialog

APP_TITLE = "Транскрипция SteadyControl"


def _card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        lay.addWidget(lbl)
    return frame, lay


def _format_size(path: str) -> str:
    size = os.path.getsize(path)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def _relative_time(dt: datetime) -> str:
    delta = datetime.now() - dt
    sec = int(delta.total_seconds())
    if sec < 60:
        return "только что"
    if sec < 3600:
        return f"{sec // 60} мин назад"
    if sec < 86400:
        return f"{sec // 3600} ч назад"
    return f"{sec // 86400} дн назад"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(760, 860)
        self.setAcceptDrops(True)

        self.settings = settings_store.load()
        self.transcriber = Transcriber()
        self.worker: TranscriptionWorker | None = None
        self.selected_file: str | None = None
        self.result: TranscriptionResult | None = None
        self.selected_entry: history.Entry | None = None

        self._build_ui()
        self._refresh_all()

    # ---------- построение интерфейса ----------

    def _build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.column = QVBoxLayout(content)
        self.column.setContentsMargins(24, 20, 24, 24)
        self.column.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.setCentralWidget(root)

        # Шапка
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        t1 = QLabel(APP_TITLE)
        t1.setObjectName("h1")
        t2 = QLabel("Перетащите аудио- или видеофайл для расшифровки. Всё локально.")
        t2.setObjectName("subtitle")
        title_box.addWidget(t1)
        title_box.addWidget(t2)
        header.addLayout(title_box)
        header.addStretch()
        self.settings_btn = QPushButton("⚙ Настройки")
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(self.settings_btn, alignment=Qt.AlignTop)
        self.column.addLayout(header)

        # Карточка выбора файла
        self.file_card, fc = _card()
        self.drop_zone = QLabel()
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setAlignment(Qt.AlignCenter)
        self.drop_zone.setMinimumHeight(120)
        self.drop_zone.setTextFormat(Qt.RichText)
        self.drop_zone.mousePressEvent = lambda e: self._pick_file()
        fc.addWidget(self.drop_zone)

        row = QHBoxLayout()
        self.file_label = QLabel()
        self.file_label.setObjectName("fileName")
        self.clear_file_btn = QPushButton("✕")
        self.clear_file_btn.setObjectName("iconBtn")
        self.clear_file_btn.setFixedWidth(32)
        self.clear_file_btn.clicked.connect(self._reset_file)
        row.addWidget(self.file_label)
        row.addStretch()
        row.addWidget(self.clear_file_btn)
        fc.addLayout(row)

        self.transcribe_btn = QPushButton("🎙  Расшифровать")
        self.transcribe_btn.setObjectName("primary")
        self.transcribe_btn.clicked.connect(self._start)
        fc.addWidget(self.transcribe_btn)
        self.column.addWidget(self.file_card)

        # Карточка прогресса
        self.progress_card, pc = _card()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.status_label = QLabel()
        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.clicked.connect(self._cancel)
        prow = QHBoxLayout()
        prow.addWidget(self.status_label)
        prow.addStretch()
        prow.addWidget(self.cancel_btn)
        pc.addWidget(self.progress_bar)
        pc.addLayout(prow)
        self.column.addWidget(self.progress_card)

        # Карточка ошибки
        self.error_card, ec = _card()
        self.error_card.setObjectName("errorCard")
        erow = QHBoxLayout()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("errorText")
        dismiss = QPushButton("Скрыть")
        dismiss.clicked.connect(lambda: self.error_card.hide())
        erow.addWidget(self.error_label, stretch=1)
        erow.addWidget(dismiss, alignment=Qt.AlignTop)
        ec.addLayout(erow)
        self.column.addWidget(self.error_card)

        # Карточка результата
        self.result_card, rc = _card("Расшифровка готова")
        self.stats_label = QLabel()
        self.stats_label.setObjectName("stats")
        rc.addWidget(self.stats_label)
        btns = QHBoxLayout()
        copy_btn = QPushButton("📋 Копировать")
        copy_btn.clicked.connect(lambda: self._copy(self.result.text if self.result else ""))
        export_btn = QPushButton("💾 Экспорт")
        export_btn.clicked.connect(lambda: self._export_result())
        btns.addWidget(copy_btn)
        btns.addWidget(export_btn)
        btns.addStretch()
        rc.addLayout(btns)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(300)
        rc.addWidget(self.result_text)
        self.column.addWidget(self.result_card)

        # История
        self.history_header = QHBoxLayout()
        hist_title = QLabel("Недавние расшифровки")
        hist_title.setObjectName("h2")
        self.clear_all_btn = QPushButton("Очистить всё")
        self.clear_all_btn.clicked.connect(self._clear_history)
        self.history_header.addWidget(hist_title)
        self.history_header.addStretch()
        self.history_header.addWidget(self.clear_all_btn)
        self.history_header_widget = QWidget()
        self.history_header_widget.setLayout(self.history_header)
        self.column.addWidget(self.history_header_widget)

        self.history_box = QVBoxLayout()
        self.history_box.setSpacing(6)
        self.history_widget = QWidget()
        self.history_widget.setLayout(self.history_box)
        self.column.addWidget(self.history_widget)

        # Детальная карточка истории
        self.detail_card, dc = _card("Из истории")
        self.detail_stats = QLabel()
        self.detail_stats.setObjectName("stats")
        dc.addWidget(self.detail_stats)
        dbtns = QHBoxLayout()
        d_copy = QPushButton("📋 Копировать")
        d_copy.clicked.connect(lambda: self._copy(self.selected_entry.text if self.selected_entry else ""))
        d_export = QPushButton("💾 Экспорт")
        d_export.clicked.connect(self._export_entry)
        d_delete = QPushButton("🗑 Удалить")
        d_delete.clicked.connect(self._delete_entry)
        for b in (d_copy, d_export, d_delete):
            dbtns.addWidget(b)
        dbtns.addStretch()
        dc.addLayout(dbtns)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(300)
        dc.addWidget(self.detail_text)
        self.column.addWidget(self.detail_card)

        self.column.addStretch()

        # Тост «Скопировано!»
        self.toast = QLabel("Скопировано!", self)
        self.toast.setObjectName("toast")
        self.toast.hide()

    # ---------- обновление состояний ----------

    def _refresh_all(self):
        busy = self.worker is not None and self.worker.isRunning()
        if self.selected_file:
            self.drop_zone.hide()
            self.file_label.setText(
                f"📄  {os.path.basename(self.selected_file)}   ({_format_size(self.selected_file)})")
            self.file_label.show()
            self.clear_file_btn.show()
            self.transcribe_btn.show()
            self.transcribe_btn.setEnabled(not busy)
        else:
            self.drop_zone.setText(
                "<div style='font-size:15px'>⬆️<br><b>Выберите аудио- или видеофайл</b><br>"
                f"<span style='font-size:11px'>{convert.FORMATS_DESCRIPTION}</span></div>")
            self.drop_zone.show()
            self.file_label.hide()
            self.clear_file_btn.hide()
            self.transcribe_btn.hide()
        self.progress_card.setVisible(busy)
        self.error_card.hide()
        self.result_card.setVisible(self.result is not None)
        if self.result:
            speed = self.result.duration / self.result.processing_time if self.result.processing_time else 0
            self.stats_label.setText(
                f"🕐 {self.result.duration:.1f} с    ✅ {self.result.confidence * 100:.0f}%    ⚡ {speed:.1f}×")
            self.result_text.setPlainText(self.result.text)
        self._refresh_history()

    def _refresh_history(self):
        while self.history_box.count():
            item = self.history_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = history.list_entries()
        self.history_header_widget.setVisible(bool(entries))
        self.history_widget.setVisible(bool(entries))
        for entry in entries:
            row = QPushButton()
            row.setObjectName("historyRow")
            selected = self.selected_entry and entry.id == self.selected_entry.id
            mark = "▶ " if selected else ""
            row.setText(f"{mark}📄 {entry.file_name}   ·   {_relative_time(entry.dt)}\n{entry.preview_text}")
            row.setProperty("selected", bool(selected))
            row.clicked.connect(lambda _=False, e=entry: self._select_entry(e))
            self.history_box.addWidget(row)
        self.detail_card.setVisible(self.selected_entry is not None)
        if self.selected_entry:
            e = self.selected_entry
            self.detail_stats.setText(
                f"🕐 {e.duration:.1f} с    ✅ {e.confidence * 100:.0f}%    📅 {e.dt.strftime('%d.%m.%Y %H:%M')}")
            self.detail_text.setPlainText(e.text)

    # ---------- действия ----------

    def _pick_file(self):
        exts = " ".join(f"*.{e}" for e in sorted(convert.SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Выберите аудио- или видеофайл", "",
                                              f"Аудио и видео ({exts})")
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        if not convert.is_supported(path):
            self._show_error(convert.FORMATS_DESCRIPTION, auto_hide=True)
            return
        self.selected_file = path
        self.result = None
        self._refresh_all()

    def _reset_file(self):
        self.selected_file = None
        self.result = None
        self._refresh_all()

    def _start(self):
        if not self.selected_file or (self.worker and self.worker.isRunning()):
            return
        self.result = None
        self.settings = settings_store.load()
        self.worker = TranscriptionWorker(self.transcriber, self.selected_file, self.settings)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self._refresh_all()
        self.progress_card.show()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.status_label.setText("Отмена…")

    def _on_progress(self, status: str, value: float):
        self.status_label.setText(status)
        self.progress_bar.setValue(int(value * 100))

    def _on_done(self, result: TranscriptionResult):
        self.result = result
        if not result.text.strip():
            self._show_error("Речь не обнаружена — файл тишины или без голоса.")
            self.result = None
        else:
            entry = history.add(
                os.path.basename(self.selected_file or ""), result.duration,
                result.processing_time, result.confidence, result.text,
                self.settings["model"], result.language,
                limit=int(self.settings.get("history_limit", 50)))
            self.selected_entry = None
        self.worker = None
        self._refresh_all()

    def _on_failed(self, message: str):
        self.worker = None
        self._refresh_all()
        self._show_error(message)

    def _show_error(self, message: str, auto_hide: bool = False):
        self.error_label.setText(f"⚠️  {message}")
        self.error_card.show()
        if auto_hide:
            QTimer.singleShot(3000, self.error_card.hide)

    def _copy(self, text: str):
        QGuiApplication.clipboard().setText(text)
        self.toast.adjustSize()
        self.toast.move(self.width() - self.toast.width() - 24, 16)
        self.toast.show()
        QTimer.singleShot(2000, self.toast.hide)

    # ---------- экспорт (формат оригинала) ----------

    def _export(self, file_name: str, text: str, duration: float,
                processing: float, confidence: float, timestamp: datetime):
        base = os.path.splitext(file_name)[0] or "transcription"
        path, chosen = QFileDialog.getSaveFileName(
            self, "Экспорт расшифровки", f"{base}_transcript.txt",
            "Текст (*.txt);;JSON (*.json)")
        if not path:
            return
        if path.endswith(".json") or "json" in chosen.lower():
            payload = {
                "confidence": confidence, "duration": duration,
                "fileName": file_name, "processingTime": processing,
                "text": text, "timestamp": timestamp.isoformat(),
            }
            content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            content = (f"Transcription: {file_name}\n"
                       f"Date: {timestamp.strftime('%d.%m.%Y %H:%M')}\n"
                       f"Duration: {duration:.1f} s\n"
                       f"Processing Time: {processing:.1f} s\n"
                       f"Confidence: {confidence * 100:.1f}%\n"
                       f"---\n\n{text}")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            self._show_error(f"Не удалось сохранить файл: {e}")

    def _export_result(self):
        if self.result and self.selected_file:
            self._export(os.path.basename(self.selected_file), self.result.text,
                         self.result.duration, self.result.processing_time,
                         self.result.confidence, datetime.now())

    def _export_entry(self):
        if self.selected_entry:
            e = self.selected_entry
            self._export(e.file_name, e.text, e.duration, e.processing_time,
                         e.confidence, e.dt)

    # ---------- история ----------

    def _select_entry(self, entry: history.Entry):
        self.selected_entry = None if (self.selected_entry and self.selected_entry.id == entry.id) else entry
        self._refresh_history()

    def _delete_entry(self):
        if self.selected_entry:
            history.delete(self.selected_entry.id)
            self.selected_entry = None
            self._refresh_history()

    def _clear_history(self):
        if QMessageBox.question(self, APP_TITLE, "Удалить всю историю расшифровок?") == QMessageBox.Yes:
            history.clear()
            self.selected_entry = None
            self._refresh_history()

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.settings = settings_store.load()

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
            self._set_file(urls[0].toLocalFile())

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, APP_TITLE,
                                    "Идёт расшифровка. Прервать и выйти?") != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(3000)
        event.accept()
