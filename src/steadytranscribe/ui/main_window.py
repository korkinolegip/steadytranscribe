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
from .pages.feedback_page import FeedbackPage
from .pages.help_page import HelpPage
from .pages.history_page import HistoryPage
from .pages.models import ModelsPage
from .pages.settings_page import SettingsPage
from .pages.stats_page import StatsPage
from .pages.transcribe import TranscribePage

APP_TITLE = "SteadyVoice · SteadyControl"

# (секция | None, заголовок, индекс страницы)
# UX-порядок: главное действие — первым и без секции; рабочие материалы (история/
# статистика) — следом; настройка нужна реже — ниже; справка — традиционно в самом низу.
SIDEBAR = [
    (None, "📄  Расшифровка файлов", 0),
    ("АКТИВНОСТЬ", None, None),
    (None, "🕘  История", 3),
    (None, "📊  Статистика", 4),
    ("НАСТРОЙКА", None, None),
    (None, "⚙️  Настройки", 2),
    (None, "🧠  Модели", 1),
    ("ПОМОЩЬ", None, None),
    (None, "❓  Как пользоваться", 5),
    (None, "💬  Обратная связь", 6),
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
            self.tray.setToolTip("SteadyVoice")
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
        self.feedback_page = FeedbackPage()
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
            # крупнее: 214px + узкие поля = вся ширина сайдбара (230)
            logo.setPixmap(QPixmap(logo_path).scaledToWidth(214, Qt.SmoothTransformation))
            logo.setContentsMargins(8, 12, 8, 8)
        else:
            logo.setText("🎙 SteadyVoice")
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
                     self.history_page, self.stats_page, self.help_page,
                     self.feedback_page):
            self.stack.addWidget(page)
        lay.addWidget(self.stack, stretch=1)
        self.setCentralWidget(root)

        # стартовая страница: при САМОМ ПЕРВОМ запуске после установки — красиво
        # открываем «Как пользоваться» (с анимацией); дальше всегда «Расшифровка».
        from ..storage import settings as _settings
        first_run = not _settings.load().get("onboarded")
        start_page = 5 if first_run else 0
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == start_page:
                self.nav.setCurrentRow(i)
                break

        # первый запуск: подсказка «начните здесь» у пункта «Расшифровка файлов».
        # Появляется ТОЛЬКО когда человек долистал «Как пользоваться» до конца,
        # мигает и исчезает НАВСЕГДА после первого клика по пункту.
        self._start_hint = None
        if first_run:
            from PySide6.QtCore import QTimer as _QT
            self._start_hint = QLabel("👈  начните здесь", self)
            self._start_hint.setObjectName("startHint")
            self._start_hint.adjustSize()
            self._start_hint.hide()
            self._hint_blink = _QT(self)
            self._hint_blink.setInterval(650)
            self._hint_blink.timeout.connect(
                lambda: self._start_hint and self._start_hint.setVisible(
                    not self._start_hint.isVisible()))
            self.help_page.scrolled_to_bottom.connect(self._activate_start_hint)

    def _activate_start_hint(self):
        """Гид дочитан до конца — показываем мигающий бейдж «начните здесь»."""
        if not self._start_hint:
            return
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == 0:
                r = self.nav.visualItemRect(self.nav.item(i))
                pos = self.nav.mapTo(self, r.topRight())
                self._start_hint.move(pos.x() + 6,
                                      pos.y() + (r.height() - self._start_hint.height()) // 2)
                self._start_hint.raise_()
                self._start_hint.show()
                self._hint_blink.start()
                break

    def _dismiss_start_hint(self):
        # getattr: _on_nav может сработать при старте раньше создания подсказки
        if getattr(self, "_start_hint", None) is not None:
            self._hint_blink.stop()
            self._start_hint.hide()
            self._start_hint.deleteLater()
            self._start_hint = None

        # обновления по схеме Chrome: тихо скачать → отложить → применить
        # при простое / при выходе / при следующем запуске (см. updater.py).
        self._installing = False            # установка уже запущена (не дублировать)
        self._auto_downloader = None
        self._update_checker = self._start_update_flow(startup=True)
        # подтверждение после обновления: «программа обновлена до vX»
        self._notify_if_updated()
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
        self._startup_dialog_shown = False
        # мини-обучение и базовая модель при первом запуске
        QTimer.singleShot(300, lambda: onboarding.maybe_show(self))

        # ---- продуктовая аналитика (только события использования, без контента) ----
        from ..storage import analytics
        analytics.track("app_start")
        self._session_t0 = time.monotonic()
        self._active_sec = 0                 # АКТИВНОЕ время (окно в фокусе), как в Wizr
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(5000)
        self._activity_timer.timeout.connect(
            lambda: setattr(self, "_active_sec",
                            self._active_sec + (5 if self.isActiveWindow() else 0)))
        self._activity_timer.start()
        # живая аналитика: отправка накопленного раз в 15 минут
        self._analytics_timer = QTimer(self)
        self._analytics_timer.setInterval(15 * 60 * 1000)
        self._analytics_timer.timeout.connect(analytics.flush_async)
        self._analytics_timer.start()

    def _start_update_flow(self, startup: bool = False):
        if os.environ.get("STEADY_UITEST"):
            return None   # фотосессия UI: без сети и модальных диалогов
        from ..storage import settings as settings_store
        checker = updater.UpdateChecker(self)
        auto = settings_store.load().get("auto_update", True)
        # тихое обновление дважды сорвалось? — переходим на ВИДИМЫЙ диалог:
        # пользователь увидит ошибку и сможет обновиться кнопкой (внутри программы)
        if updater.consume_update_failed():
            auto = False
        if startup or not auto:
            # ПРИ ЗАПУСКЕ — честно спрашиваем: «Обновить сейчас / Позже».
            # «Позже» → тихо скачаем в фоне и поставим при закрытии.
            checker.update_available.connect(self._on_update_found_startup)
        else:
            # проверка в середине работы — молча качаем, поставим при закрытии
            checker.update_available.connect(self._on_update_found)
        checker.start()
        return checker

    def _on_update_found_startup(self, version: str, url: str, sha: str = ""):
        if self._startup_dialog_shown:
            return
        self._startup_dialog_shown = True
        dlg = updater.UpdateDialog(version, url, sha, self)
        if not dlg.exec():
            # «Позже»: скачиваем в фоне, установится при закрытии/простое
            self._on_update_found(version, url, sha)

    def _notify_if_updated(self):
        """Первый запуск новой версии — подтверждаем: «обновлено до vX»."""
        from ..storage import settings as settings_store
        s = settings_store.load()
        prev = s.get("last_version", "")
        if prev == updater.CURRENT_VERSION:
            return
        s["last_version"] = updater.CURRENT_VERSION
        settings_store.save(s)
        if prev:
            from ..storage import analytics
            analytics.track("updated", frm=prev, to=updater.CURRENT_VERSION)
        if prev and self.tray is not None:   # prev пуст = самая первая установка
            from PySide6.QtWidgets import QSystemTrayIcon
            from .changelog import whats_new
            note = whats_new(updater.CURRENT_VERSION)
            body = f"Установлена версия {updater.CURRENT_VERSION}."
            if note:
                body += f"\n✨ {note}"       # по-человечески, без технических деталей
            self.tray.showMessage("Программа обновлена", body,
                                  QSystemTrayIcon.Information, 7000)

    def _on_update_found(self, version: str, url: str, sha: str = ""):
        """Авто-режим: тихо скачиваем установщик в фоне, не мешая работе."""
        if updater.load_pending() or (self._auto_downloader
                                      and self._auto_downloader.isRunning()):
            return                          # уже скачано или качается
        self._new_version = version
        self._auto_downloader = updater.InstallerDownloader(url, sha, self)
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
        if (self._installing or updater.install_in_progress() or self._busy()
                or not updater.load_pending()):
            return
        if time.monotonic() - self._last_active < 600:   # 10 минут простоя
            return
        # Простой: ставим обновление, ПРЕДУПРЕДИВ уведомлением (иначе «программа
        # сама закрылась» пугает). Перезапуск — свёрнутой, фокус не крадём.
        import logging
        logging.info("update: простой ≥10 мин — устанавливаю отложенное обновление")
        self._installing = True
        if self.tray is not None:
            from PySide6.QtWidgets import QSystemTrayIcon
            self.tray.showMessage(
                "Обновление SteadyVoice",
                "Программа простаивает — устанавливаю обновление и вернусь через минуту.",
                QSystemTrayIcon.Information, 5000)
        updater.mark_restart_minimized()
        if updater.install_pending(relaunch=True):
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QTimer
            QTimer.singleShot(4000, QApplication.quit)   # дать уведомлению показаться
        else:
            self._installing = False

    def _on_nav(self, current: QListWidgetItem, _prev):
        if current is None:
            return
        idx = current.data(Qt.UserRole)
        if idx is None:
            return
        if idx == 0:
            self._dismiss_start_hint()   # человек нашёл, откуда начинать
        from ..storage import analytics
        pages = {0: "transcribe", 1: "models", 2: "settings", 3: "history",
                 4: "stats", 5: "help", 6: "feedback"}
        analytics.track("nav", page=pages.get(idx, str(idx)))
        self.stack.setCurrentIndex(idx)
        if idx == 3:
            self.history_page.refresh()
        elif idx == 4:
            self.stats_page.refresh()
        elif idx == 1:
            self.models_page.refresh_rows()

    def closeEvent(self, event):
        import logging
        logging.info("closeEvent: окно закрывается (spontaneous=%s)", event.spontaneous())
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
        # фоновое скачивание модели из окна первого запуска
        ob = getattr(self, "_onboarding", None)
        if ob is not None:
            ob.stop_worker()
        self.transcribe_page._cleanup_wav()

        # СТРАХОВКА ОТ СИРОТ: принудительно валим все дочерние процессы
        # (ffmpeg, разделение собеседников) — чтобы после закрытия ничего не висело.
        from ..core import jobkill
        jobkill.kill_all()

        # Тихо ставим отложенное обновление — на выходе, БЕЗ перезапуска
        # (пользователь закрыл программу — не открываем её заново).
        # install_in_progress: если установщик УЖЕ запущен (кнопка «Обновить
        # сейчас») — второй не запускаем, два установщика срывают обновление.
        if (not self._installing and not updater.install_in_progress()
                and updater.load_pending()):
            self._installing = True
            updater.install_pending(relaunch=False)

        # аналитика: длительность сеанса (общая и АКТИВНАЯ) + отправка пачки
        import time as _t
        from ..storage import analytics
        analytics.track("app_close",
                        sec=int(_t.monotonic() - self._session_t0),
                        active_sec=int(self._active_sec))
        analytics.flush(timeout=6)   # синхронно, коротко — и выходим
        event.accept()
