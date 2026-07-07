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
from .pages.help_page import HelpPage
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
    (None, "❓  Как пользоваться", 5),
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
        app_icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        # системный трей — уведомление «файл готов», когда окно свёрнуто
        from PySide6.QtWidgets import QSystemTrayIcon
        try:
            self.tray = QSystemTrayIcon(app_icon, self)
            self.tray.setToolTip("SteadyTranscribe")
            self.tray.show()
        except Exception:  # noqa: BLE001
            self.tray = None

        transcriber = Transcriber()
        self.transcribe_page = TranscribePage(transcriber)
        self.models_page = ModelsPage()
        self.settings_page = SettingsPage()
        self.history_page = HistoryPage()
        self.stats_page = StatsPage()
        self.help_page = HelpPage()
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
        version = QLabel(f"v{updater.CURRENT_VERSION} · всё локально")
        version.setObjectName("tertiary")
        version.setContentsMargins(14, 8, 8, 12)
        slay.addWidget(version)
        lay.addWidget(side)

        # страницы
        self.stack = QStackedWidget()
        for page in (self.transcribe_page, self.models_page, self.settings_page,
                     self.history_page, self.stats_page, self.help_page):
            self.stack.addWidget(page)
        lay.addWidget(self.stack, stretch=1)
        self.setCentralWidget(root)

        # выбрать «Расшифровка файлов»
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == 0:
                self.nav.setCurrentRow(i)
                break

        # обновления по схеме Chrome: тихо скачать → отложить → применить
        # при простое / при выходе / при следующем запуске (см. updater.py).
        self._installing = False            # установка уже запущена (не дублировать)
        self._auto_downloader = None
        self._update_checker = self._start_update_flow()
        # таймер простоя: окно неактивно ≥10 мин и ничего не обрабатывается →
        # ставим отложенное обновление, вернёмся свёрнутыми (фокус не крадём)
        import time
        from PySide6.QtCore import QTimer
        self._last_active = time.monotonic()
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._idle_tick)
        self._idle_timer.start()
        # повторная проверка обновлений раз в час (программу держат открытой днями;
        # 4 часа было слишком редко — обновление, вышедшее после запуска, «не доходило»)
        self._recheck_timer = QTimer(self)
        self._recheck_timer.setInterval(3600 * 1000)
        self._recheck_timer.timeout.connect(
            lambda: setattr(self, "_update_checker", self._start_update_flow()))
        self._recheck_timer.start()
        # мини-обучение и базовая модель при первом запуске
        QTimer.singleShot(300, lambda: onboarding.maybe_show(self))

    def _start_update_flow(self):
        from ..storage import settings as settings_store
        checker = updater.UpdateChecker(self)
        auto = settings_store.load().get("auto_update", True)
        # тихое обновление дважды сорвалось? — переходим на ВИДИМЫЙ диалог:
        # пользователь увидит ошибку и сможет обновиться кнопкой (внутри программы)
        if updater.consume_update_failed():
            auto = False
        if auto:
            checker.update_available.connect(self._on_update_found)
        else:
            checker.update_available.connect(
                lambda v, url: updater.UpdateDialog(v, url, self).exec())
        checker.start()
        return checker

    def _on_update_found(self, version: str, url: str):
        """Авто-режим: тихо скачиваем установщик в фоне, не мешая работе."""
        if updater.load_pending() or (self._auto_downloader
                                      and self._auto_downloader.isRunning()):
            return                          # уже скачано или качается
        self._new_version = version
        self._auto_downloader = updater.InstallerDownloader(url, self)
        self._auto_downloader.done.connect(
            lambda path, v=version: self._on_installer_ready(v, path))
        # ошибки скачивания игнорируем тихо — повторим при следующей проверке
        self._auto_downloader.start()

    def _on_installer_ready(self, version: str, installer_path: str):
        """Установщик скачан и отложен. Применится при простое/выходе/запуске."""
        updater.save_pending(version, installer_path)
        if self.tray is not None:
            from PySide6.QtWidgets import QSystemTrayIcon
            self.tray.showMessage(
                "Обновление готово",
                f"Версия {version} загружена и установится сама — работе не помешает.",
                QSystemTrayIcon.Information, 6000)

    def _busy(self) -> bool:
        if any(w and w.isRunning() for w in (self.transcribe_page.worker,
                                             self.transcribe_page.diar_worker)):
            return True
        return any(row.worker and row.worker.isRunning()
                   for row in getattr(self.models_page, "rows", []))

    def _idle_tick(self):
        import time
        if self.isActiveWindow():
            self._last_active = time.monotonic()
            return
        if self._installing or self._busy() or not updater.load_pending():
            return
        if time.monotonic() - self._last_active < 600:   # 10 минут простоя
            return
        # Простой: тихо ставим обновление. Программа перезапустится СВЁРНУТОЙ
        # (маркер), чтобы не выскочить поверх работы пользователя.
        self._installing = True
        updater.mark_restart_minimized()
        if updater.install_pending(relaunch=True):
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, QApplication.quit)
        else:
            self._installing = False

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
        # Идёт тяжёлая обработка? — спросим подтверждение
        busy = [w for w in (self.transcribe_page.worker, self.transcribe_page.diar_worker)
                if w and w.isRunning()]
        if busy:
            if QMessageBox.question(self, APP_TITLE,
                                    "Идёт обработка. Прервать и выйти?") != QMessageBox.Yes:
                event.ignore()
                return

        # Завершаем ВСЕ фоновые потоки и процессы — чтобы не осталось сирот
        for w in busy:
            w.cancel()
            w.wait(4000)
        if self._update_checker and self._update_checker.isRunning():
            self._update_checker.wait(1000)
        if self._auto_downloader and self._auto_downloader.isRunning():
            self._auto_downloader.cancel()
            self._auto_downloader.wait(1000)
        # потоки скачивания моделей
        for row in getattr(self.models_page, "rows", []):
            if row.worker and row.worker.isRunning():
                row.worker.cancel_event.set()
                row.worker.wait(2000)
        self.transcribe_page._cleanup_wav()

        # СТРАХОВКА ОТ СИРОТ: принудительно валим все дочерние процессы
        # (ffmpeg, разделение собеседников) — чтобы после закрытия ничего не висело.
        from ..core import jobkill
        jobkill.kill_all()

        # Тихо ставим отложенное обновление — на выходе, БЕЗ перезапуска
        # (пользователь закрыл программу — не открываем её заново).
        if not self._installing and updater.load_pending():
            self._installing = True
            updater.install_pending(relaunch=False)
        event.accept()
