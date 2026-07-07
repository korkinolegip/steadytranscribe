"""Страница «Модели» — аналог «Голосового движка» FluidVoice:
строки моделей со Speed/Accuracy, скачивание с прогрессом, активация."""
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ...core import models
from ...storage import settings as settings_store
from ..widgets import card


class DownloadWorker(QThread):
    progress = Signal(int, int)   # done, total
    done = Signal()
    failed = Signal(str)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.cancel_event = threading.Event()

    def run(self):
        try:
            models.download(self.key, lambda d, t: self.progress.emit(d, t),
                            self.cancel_event)
            self.done.emit()
        except InterruptedError:
            self.failed.emit("Загрузка отменена.")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ModelRow(QFrame):
    def __init__(self, info: models.ModelInfo, page: "ModelsPage"):
        super().__init__()
        self.info = info
        self.page = page
        self.setObjectName("modelRow")
        self.worker: DownloadWorker | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)

        left = QVBoxLayout()
        name = QLabel(info.title)
        name.setObjectName("modelName")
        note = QLabel(f"{info.note} · {info.size_mb} МБ")
        note.setObjectName("hint")
        metrics = QHBoxLayout()
        sp = QLabel(f"⚡ Скорость {info.speed_pct}%")
        sp.setObjectName("speedLabel")
        ac = QLabel(f"🎯 Точность {info.accuracy_pct}%")
        ac.setObjectName("accLabel")
        metrics.addWidget(sp)
        metrics.addWidget(ac)
        metrics.addStretch()
        left.addWidget(name)
        left.addWidget(note)
        left.addLayout(metrics)
        lay.addLayout(left, stretch=1)

        # правая зона действий
        self.right = QVBoxLayout()
        self.right.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(110)
        self.progress.hide()
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self._cancel)
        self.action_btn = QPushButton()
        self.action_btn.clicked.connect(self._action)
        self.badge = QLabel("Активна")
        self.badge.setObjectName("activeBadge")
        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setFixedWidth(34)
        self.delete_btn.clicked.connect(self._delete)
        row = QHBoxLayout()
        for w in (self.progress, self.cancel_btn, self.delete_btn, self.action_btn):
            row.addWidget(w)
        row.addWidget(self.badge)
        self.right.addLayout(row)
        lay.addLayout(self.right)
        self.refresh()

    def refresh(self):
        s = settings_store.load()
        downloading = self.worker is not None and self.worker.isRunning()
        downloaded = models.is_downloaded(self.info.key)
        active = downloaded and s["model"] == self.info.key
        self.progress.setVisible(downloading)
        self.cancel_btn.setVisible(downloading)
        self.badge.setVisible(active and not downloading)
        self.delete_btn.setVisible(downloaded and not active and not downloading)
        self.action_btn.setVisible(not downloading and not active)
        if not downloaded:
            self.action_btn.setText("Скачать")
            self.action_btn.setObjectName("download")
        else:
            self.action_btn.setText("Активировать")
            self.action_btn.setObjectName("activate")
        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)
        self.setProperty("active", bool(active))
        self.style().unpolish(self)
        self.style().polish(self)

    def _action(self):
        if models.is_downloaded(self.info.key):
            s = settings_store.load()
            s["model"] = self.info.key
            settings_store.save(s)
            self.page.refresh_rows()
        else:
            self.worker = DownloadWorker(self.info.key, self)
            self.worker.progress.connect(self._on_progress)
            self.worker.done.connect(self._on_done)
            self.worker.failed.connect(self._on_failed)
            self.worker.start()
            self.refresh()

    def _cancel(self):
        if self.worker:
            self.worker.cancel_event.set()

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_done(self):
        self.worker = None
        self.page.refresh_rows()

    def _on_failed(self, msg: str):
        self.worker = None
        self.page.show_error(msg)
        self.page.refresh_rows()

    def _delete(self):
        models.delete_model(self.info.key)
        self.page.refresh_rows()


class ModelsPage(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(14)

        title = QLabel("Модели распознавания")
        title.setObjectName("h1")
        sub = QLabel("Скачайте модель и нажмите «Активировать». Активная модель используется для расшифровки.")
        sub.setObjectName("subtitle")
        outer.addWidget(title)
        outer.addWidget(sub)

        self.error = QLabel()
        self.error.setObjectName("errorText")
        self.error.setWordWrap(True)
        self.error.hide()
        outer.addWidget(self.error)

        box, box_lay = card()
        self.rows: list[ModelRow] = []
        for info in models.CATALOG:
            row = ModelRow(info, self)
            self.rows.append(row)
            box_lay.addWidget(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(box)
        outer.addWidget(scroll, stretch=1)

    def refresh_rows(self):
        self.error.hide()
        for row in self.rows:
            row.refresh()

    def show_error(self, msg: str):
        self.error.setText(f"⚠️  {msg}")
        self.error.show()
