"""Первый запуск: скачивание базовой модели (кратко и по делу).

Инструкция «как пользоваться» здесь НЕ дублируется — при первом запуске за
спиной этого окна уже открыт раздел «Как пользоваться». Окно объясняет одно:
зачем нужна модель. После нажатия «Скачать» оно НЕ блокирует программу —
уезжает в левый нижний угол и качает в фоне.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ..core import models
from ..storage import settings as settings_store
from .pages.models import DownloadWorker

# отделы SteadyControl (из внутренних проектов) + свой вариант
DEPARTMENTS = ["PR", "Внедрение", "Сопровождение", "Продажи", "Маркетинг",
               "Руководство", "Другое…"]

INTRO = """
<h3>Один шаг до начала работы</h3>
<p style='line-height:1.5'>
Для распознавания речи программе нужна <b>модель</b> — «мозг», который превращает
голос в текст. Она скачивается <b>один раз</b>, после этого программа работает
полностью без интернета: записи не покидают ваш компьютер.
</p>
"""


class OnboardingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добро пожаловать в SteadyVoice")
        self.setMinimumWidth(520)
        self.worker: DownloadWorker | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        self.intro = QLabel(INTRO)
        self.intro.setWordWrap(True)
        self.intro.setTextFormat(Qt.RichText)
        lay.addWidget(self.intro)

        self.model_block = QVBoxLayout()
        # без технических деталей (имя/вес модели) — просто и понятно
        self.model_label = QLabel("Базовая версия — максимальное качество. "
                                  "Скачивается один раз.")
        self.model_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.model_block.addWidget(self.model_label)
        self.model_block.addWidget(self.progress)
        self.model_block.addWidget(self.status)
        lay.addLayout(self.model_block)

        btns = QHBoxLayout()
        self.download_btn = QPushButton("⬇ Скачать модель и начать")
        self.download_btn.setObjectName("primary")
        self.download_btn.clicked.connect(self._download)
        self.skip_btn = QPushButton("Позже (скачаю на странице «Модели»)")
        btns.addWidget(self.download_btn)
        btns.addWidget(self.skip_btn)
        self.skip_btn.clicked.connect(self._finish)
        lay.addLayout(btns)

        if models.is_downloaded(models.DEFAULT_MODEL):
            self.model_label.setText("Базовая модель уже скачана — можно работать. ✅")
            self.download_btn.hide()
            self.skip_btn.setText("Начать работу")

    def _download(self):
        self.download_btn.setEnabled(False)
        self.progress.show()
        self.status.setText("Скачивание…")
        self.worker = DownloadWorker(models.DEFAULT_MODEL, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        # сворачиваемся в КОМПАКТНУЮ плашку загрузки внизу слева
        # (ширина бокового меню, минимум текста, никаких лишних кнопок)
        self._compact_dock()
        # следом — знакомство (имя/отдел), пока модель качается
        QTimer.singleShot(400, lambda: ensure_identity(self.parent()))

    def _compact_dock(self):
        self.setWindowTitle("Загрузка модели")
        self.intro.hide()
        self.download_btn.hide()
        self.skip_btn.hide()
        self.model_label.setText("Модель распознавания речи")
        self.setMinimumWidth(0)
        self.setFixedWidth(230)              # ширина бокового меню
        self.adjustSize()
        parent = self.parent()
        if parent is None:
            return
        g = parent.geometry()
        self.move(g.x() + 8, g.y() + g.height() - self.height() - 10)

    def _on_progress(self, done: int, total: int):
        mb_done, mb_total = done // 1048576, max(total // 1048576, 1)
        self.progress.setValue(int(done / max(total, 1) * 100))
        self.status.setText(f"Скачивание: {mb_done} / {mb_total} МБ")

    def _on_done(self):
        s = settings_store.load()
        s["model"] = models.DEFAULT_MODEL
        settings_store.save(s)
        self.status.setText("Готово! Модель активирована. ✅")
        self.progress.setValue(100)
        self._finish()

    def _on_failed(self, msg: str):
        self.download_btn.setEnabled(True)
        self.status.setText(f"⚠️ {msg}")

    def _finish(self):
        s = settings_store.load()
        s["onboarded"] = True
        settings_store.save(s)
        ensure_identity(self.parent())
        if self.worker and self.worker.isRunning():
            self.hide()          # скачивание ПРОДОЛЖАЕТСЯ в фоне, не отменяем
            return
        self.accept()

    def stop_worker(self):
        """Вызывается при закрытии программы — корректно гасим скачивание."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel_event.set()
            self.worker.wait(2000)


class IdentityDialog(QDialog):
    """«Давайте познакомимся»: имя и фамилия (обязательно) + отдел из списка
    (или свой). Закрыть без заполнения нельзя — только «Готово». Данные
    закрепляются за компьютером и переживают все обновления; поменять можно
    в Настройках."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Давайте познакомимся")
        # без кнопки закрытия: заполнение обязательно
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setMinimumWidth(440)
        self._overlay = None
        if parent is not None:               # затемняем программу позади
            self._overlay = QWidget(parent)
            self._overlay.setStyleSheet("background: rgba(0, 0, 0, 140);")
            self._overlay.setGeometry(parent.rect())
            self._overlay.show()

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        hello = QLabel("<h3>👋 Давайте познакомимся</h3>"
                       "<p>Это поможет нам понимать, кому программа полезна "
                       "и что улучшать в первую очередь.</p>")
        hello.setWordWrap(True)
        hello.setTextFormat(Qt.RichText)
        lay.addWidget(hello)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например: Иван Петров")
        self.dept_box = QComboBox()
        self.dept_box.addItems(DEPARTMENTS)
        self.other_edit = QLineEdit()
        self.other_edit.setPlaceholderText("Впишите ваше подразделение")
        self.other_edit.hide()
        self.dept_box.currentTextChanged.connect(
            lambda t: self.other_edit.setVisible(t == "Другое…"))
        form.addRow("Имя и фамилия:", self.name_edit)
        form.addRow("Отдел:", self.dept_box)
        form.addRow("", self.other_edit)
        lay.addLayout(form)
        self.warn = QLabel()
        self.warn.setObjectName("warn")
        lay.addWidget(self.warn)
        done = QPushButton("Готово")
        done.setObjectName("primary")
        done.clicked.connect(self._done)
        lay.addWidget(done)

    def _done(self):
        name = self.name_edit.text().strip()
        if len(name) < 3:
            self.warn.setText("Пожалуйста, укажите имя и фамилию.")
            return
        dept = self.dept_box.currentText()
        if dept == "Другое…":
            dept = self.other_edit.text().strip() or "Другое"
        s = settings_store.load()
        s["user_name"] = name
        s["user_dept"] = dept
        settings_store.save(s)
        from ..storage import analytics
        analytics.track("registered")
        analytics.flush_async()
        self.accept()

    def closeEvent(self, event):
        # аварийный клапан: если имя уже сохранено (например, в другом окне) —
        # закрываемся свободно; неубиваемых окон быть не должно
        if settings_store.load().get("user_name"):
            self.accept()
            event.accept()
            return
        event.ignore()   # только через «Готово»

    def reject(self):
        if settings_store.load().get("user_name"):
            self.accept()

    def accept(self):
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None
        super().accept()


def ensure_identity(parent) -> None:
    """Показать знакомство, если имя ещё не указано. ЗАМОК от двойного открытия:
    окно вызывается из двух мест (кнопка «Скачать» и конец загрузки модели) —
    без замка они накладывались (баг: второе окно нельзя было закрыть)."""
    import os
    if os.environ.get("STEADY_UITEST"):
        return
    if settings_store.load().get("user_name"):
        return
    if parent is not None and getattr(parent, "_identity_dlg", None) is not None:
        return                                   # уже открыто — второго не будет
    dlg = IdentityDialog(parent)
    if parent is not None:
        parent._identity_dlg = dlg
    try:
        dlg.exec()
    finally:
        if parent is not None:
            parent._identity_dlg = None


def maybe_show(parent) -> None:
    import os
    if os.environ.get("STEADY_UITEST"):
        return   # режим фотосессии UI: модальное окно заблокировало бы съёмку
    s = settings_store.load()
    if not s.get("onboarded") or not models.is_downloaded(s.get("model", models.DEFAULT_MODEL)):
        dlg = OnboardingDialog(parent)
        parent._onboarding = dlg   # держим ссылку (не модально)
        dlg.show()                 # программа доступна: за окном — «Как пользоваться»
