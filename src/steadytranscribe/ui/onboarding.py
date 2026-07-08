"""Первый запуск: скачивание базовой модели (кратко и по делу).

Инструкция «как пользоваться» здесь НЕ дублируется — при первом запуске за
спиной этого окна уже открыт раздел «Как пользоваться». Окно объясняет одно:
зачем нужна модель. После нажатия «Скачать» оно НЕ блокирует программу —
уезжает в левый нижний угол и качает в фоне.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from ..core import models
from ..storage import settings as settings_store
from .pages.models import DownloadWorker

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
        text = QLabel(INTRO)
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        lay.addWidget(text)

        self.model_block = QVBoxLayout()
        info = next(m for m in models.CATALOG if m.key == models.DEFAULT_MODEL)
        self.model_label = QLabel(
            f"Базовая модель: <b>{info.title}</b> (~{info.size_mb} МБ) — {info.note.lower()}.")
        self.model_label.setTextFormat(Qt.RichText)
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
        # не мешаем знакомиться с программой: уезжаем в левый нижний угол
        self.skip_btn.setText("Свернуть (качается в фоне)")
        self._dock_bottom_left()

    def _dock_bottom_left(self):
        parent = self.parent()
        if parent is None:
            return
        self.adjustSize()
        g = parent.geometry()
        self.move(g.x() + 12, g.y() + g.height() - self.height() - 12)

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
        if self.worker and self.worker.isRunning():
            self.hide()          # скачивание ПРОДОЛЖАЕТСЯ в фоне, не отменяем
            return
        self.accept()

    def stop_worker(self):
        """Вызывается при закрытии программы — корректно гасим скачивание."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel_event.set()
            self.worker.wait(2000)


def maybe_show(parent) -> None:
    import os
    if os.environ.get("STEADY_UITEST"):
        return   # режим фотосессии UI: модальное окно заблокировало бы съёмку
    s = settings_store.load()
    if not s.get("onboarded") or not models.is_downloaded(s.get("model", models.DEFAULT_MODEL)):
        dlg = OnboardingDialog(parent)
        parent._onboarding = dlg   # держим ссылку (не модально)
        dlg.show()                 # программа доступна: за окном — «Как пользоваться»
