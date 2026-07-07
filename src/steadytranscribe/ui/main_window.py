"""Главное окно: sidebar с секциями (как FluidVoice) + страницы."""
import os
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ..core.resources import resource
from ..core.transcriber import Transcriber
from . import onboarding, updater


def _asset(name: str) -> str:
    return resource("assets", name)
from .pages.history_page import HistoryPage
from .pages.models import ModelsPage
from .pages.settings_page import SettingsPage
from .pages.stats_page import StatsPage
from .pages.transcribe import TranscribePage

APP_TITLE = "Транскрипция SteadyControl"

# (секция | None, заголовок, индекс страницы)
SIDEBAR = [
    ("ИСПОЛЬЗОВАНИЕ", None, None),
    (None, "📄  Расшифровка файлов", 0),
    ("НАСТРОЙКА", None, None),
    (None, "🧠  Модели", 1),
    (None, "⚙️  Настройки", 2),
    ("АКТИВНОСТЬ", None, None),
    (None, "🕘  История", 3),
    (None, "📊  Статистика", 4),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1000, 700)
        self.setMinimumSize(800, 500)
        icon_path = _asset("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        transcriber = Transcriber()
        self.transcribe_page = TranscribePage(transcriber)
        self.models_page = ModelsPage()
        self.settings_page = SettingsPage()
        self.history_page = HistoryPage()
        self.stats_page = StatsPage()
        self.transcribe_page.history_changed.connect(self.history_page.refresh)
        self.transcribe_page.history_changed.connect(self.stats_page.refresh)

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # sidebar
        side = QWidget()
        side.setFixedWidth(230)
        side.setStyleSheet("background: #0F0F0F;")
        slay = QVBoxLayout(side)
        slay.setContentsMargins(0, 0, 0, 0)
        slay.setSpacing(0)
        logo = QLabel()
        logo_path = _asset("header_logo.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaledToWidth(210, Qt.SmoothTransformation))
            logo.setContentsMargins(12, 14, 12, 10)
        else:
            logo.setText("🎙 SteadyControl")
            logo.setObjectName("appName")
        slay.addWidget(logo)
        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setIconSize(QSize(0, 0))
        for section, title, page_idx in SIDEBAR:
            if section:
                item = QListWidgetItem(section)
                item.setFlags(Qt.NoItemFlags)
                font = item.font()
                font.setPointSize(10)
                font.setBold(True)
                item.setFont(font)
                item.setForeground(Qt.gray)
                self.nav.addItem(item)
            else:
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, page_idx)
                self.nav.addItem(item)
        self.nav.currentItemChanged.connect(self._on_nav)
        slay.addWidget(self.nav, stretch=1)
        version = QLabel("v1.3.7 · всё локально")
        version.setObjectName("tertiary")
        version.setContentsMargins(14, 8, 8, 12)
        slay.addWidget(version)
        lay.addWidget(side)

        # страницы
        self.stack = QStackedWidget()
        for page in (self.transcribe_page, self.models_page, self.settings_page,
                     self.history_page, self.stats_page):
            self.stack.addWidget(page)
        lay.addWidget(self.stack, stretch=1)
        self.setCentralWidget(root)

        # выбрать «Расшифровка файлов»
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == 0:
                self.nav.setCurrentRow(i)
                break

        # тихая проверка обновлений при запуске
        self._update_checker = updater.check_async(self)
        # мини-обучение и базовая модель при первом запуске
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, lambda: onboarding.maybe_show(self))

    def _on_nav(self, current: QListWidgetItem, _prev):
        if current is None:
            return
        idx = current.data(Qt.UserRole)
        if idx is None:
            return
        self.stack.setCurrentIndex(idx)
        if idx == 3:
            self.history_page.refresh()
        elif idx == 4:
            self.stats_page.refresh()
        elif idx == 1:
            self.models_page.refresh_rows()

    def closeEvent(self, event):
        if self._update_checker.isRunning():
            self._update_checker.wait(500)
        for w in (self.transcribe_page.worker, self.transcribe_page.diar_worker):
            if w and w.isRunning():
                if QMessageBox.question(self, APP_TITLE,
                                        "Идёт обработка. Прервать и выйти?") != QMessageBox.Yes:
                    event.ignore()
                    return
                w.cancel()
                w.wait(3000)
        self.transcribe_page._cleanup_wav()
        event.accept()
