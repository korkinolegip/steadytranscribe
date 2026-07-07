"""Страница «История»: поиск + список слева, детали справа (как в FluidVoice)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from ...storage import history
from .transcribe import export_transcription


def _relative_time(dt) -> str:
    from datetime import datetime
    sec = int((datetime.now() - dt).total_seconds())
    if sec < 60:
        return "только что"
    if sec < 3600:
        return f"{sec // 60} мин назад"
    if sec < 86400:
        return f"{sec // 3600} ч назад"
    return f"{sec // 86400} дн назад"


class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.selected: history.Entry | None = None
        self.query = ""

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()

        # левая панель
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(16, 16, 8, 16)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Поиск по расшифровкам…")
        self.search.textChanged.connect(self._on_search)
        llay.addWidget(self.search)
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QFrame.NoFrame)
        self.list_container = QWidget()
        self.list_lay = QVBoxLayout(self.list_container)
        self.list_lay.setSpacing(6)
        self.list_lay.addStretch()
        self.list_scroll.setWidget(self.list_container)
        llay.addWidget(self.list_scroll, stretch=1)
        footer = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setObjectName("hint")
        self.clear_btn = QPushButton("Очистить всё")
        self.clear_btn.clicked.connect(self._clear_all)
        footer.addWidget(self.count_label)
        footer.addStretch()
        footer.addWidget(self.clear_btn)
        llay.addLayout(footer)
        left.setMinimumWidth(280)
        split.addWidget(left)

        # правая панель — детали
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(16, 16, 24, 16)
        self.detail_title = QLabel("Детали расшифровки")
        self.detail_title.setObjectName("h2")
        self.meta = QLabel()
        self.meta.setObjectName("stats")
        self.meta.setWordWrap(True)
        btns = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Копировать")
        self.copy_btn.clicked.connect(self._copy)
        self.export_btn = QPushButton("💾 Экспорт")
        self.export_btn.clicked.connect(self._export)
        self.delete_btn = QPushButton("🗑 Удалить")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self._delete)
        for b in (self.copy_btn, self.export_btn, self.delete_btn):
            btns.addWidget(b)
        btns.addStretch()
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.empty_label = QLabel("Выберите расшифровку")
        self.empty_label.setObjectName("tertiary")
        self.empty_label.setAlignment(Qt.AlignCenter)
        rlay.addWidget(self.detail_title)
        rlay.addWidget(self.meta)
        rlay.addLayout(btns)
        rlay.addWidget(self.text, stretch=1)
        rlay.addWidget(self.empty_label, stretch=1)
        right.setMinimumWidth(380)
        split.addWidget(right)
        split.setSizes([320, 560])
        outer.addWidget(split)

        self.toast = QLabel("Скопировано!", self)
        self.toast.setObjectName("toast")
        self.toast.hide()
        self.refresh()

    def refresh(self):
        while self.list_lay.count() > 1:
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = history.list_entries()
        if self.query:
            q = self.query.lower()
            entries = [e for e in entries if q in e.text.lower() or q in e.file_name.lower()]
        for i, e in enumerate(entries):
            row = QPushButton(f"📄 {e.file_name}   ·   {_relative_time(e.dt)}\n{e.preview_text}")
            row.setObjectName("historyRow")
            row.setProperty("selected", bool(self.selected and e.id == self.selected.id))
            row.clicked.connect(lambda _=False, entry=e: self._select(entry))
            self.list_lay.insertWidget(i, row)
        self.count_label.setText(f"Записей: {len(entries)}")
        self.clear_btn.setVisible(bool(entries))
        has_sel = self.selected is not None
        for w in (self.detail_title, self.meta, self.text,
                  self.copy_btn, self.export_btn, self.delete_btn):
            w.setVisible(has_sel)
        self.empty_label.setVisible(not has_sel)
        if self.selected:
            e = self.selected
            self.meta.setText(
                f"📄 {e.file_name}    🕐 {e.duration:.1f} с    ✅ {e.confidence * 100:.0f}%    "
                f"📅 {e.dt.strftime('%d.%m.%Y %H:%M')}    🧠 {e.model}")
            self.text.setPlainText(e.text)

    def _on_search(self, text: str):
        self.query = text.strip()
        self.refresh()

    def _select(self, entry: history.Entry):
        self.selected = entry
        self.refresh()

    def _copy(self):
        if self.selected:
            QGuiApplication.clipboard().setText(self.selected.text)
            self.toast.adjustSize()
            self.toast.move(self.width() - self.toast.width() - 24, 12)
            self.toast.show()
            QTimer.singleShot(2000, self.toast.hide)

    def _export(self):
        if self.selected:
            e = self.selected
            export_transcription(self, e.file_name, e.text, e.duration,
                                 e.processing_time, e.confidence, e.dt)

    def _delete(self):
        if self.selected:
            history.delete(self.selected.id)
            self.selected = None
            self.refresh()

    def _clear_all(self):
        n = len(history.list_entries())
        if QMessageBox.question(
                self, "Очистить историю",
                f"Будут безвозвратно удалены все записи ({n} шт.). Это действие необратимо.") == QMessageBox.Yes:
            history.clear()
            self.selected = None
            self.refresh()
