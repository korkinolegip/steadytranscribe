"""Страница «Модели» — выбор/скачивание/активация с явными статусами.

Статусы строки: не скачана · скачивается · повреждена · скачана · активна.
"""
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
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
        self.status_label = QLabel()
        self.status_label.setObjectName("hint")
        left.addWidget(name)
        left.addWidget(note)
        left.addLayout(metrics)
        left.addWidget(self.status_label)
        lay.addLayout(left, stretch=1)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self._cancel)
        self.download_btn = QPushButton("Скачать")
        self.download_btn.setObjectName("download")
        self.download_btn.clicked.connect(self._download)
        self.activate_btn = QPushButton("Активировать")
        self.activate_btn.setObjectName("activate")
        self.activate_btn.clicked.connect(self._activate)
        self.redownload_btn = QPushButton("Скачать заново")
        self.redownload_btn.setObjectName("download")
        self.redownload_btn.clicked.connect(self._redownload)
        self.badge = QLabel("✓ Активна")
        self.badge.setObjectName("activeBadge")
        self.delete_btn = QPushButton("🗑 Удалить")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self._delete)

        row = QHBoxLayout()
        for w in (self.progress, self.cancel_btn, self.redownload_btn,
                  self.badge, self.delete_btn, self.activate_btn, self.download_btn):
            row.addWidget(w)
        wrap = QVBoxLayout()
        wrap.setAlignment(Qt.AlignVCenter)
        wrap.addLayout(row)
        lay.addLayout(wrap)
        self.refresh()

    def _state(self) -> str:
        if self.worker and self.worker.isRunning():
            return "downloading"
        if not models.is_downloaded(self.info.key):
            return "absent"
        if not models.is_intact(self.info.key):
            return "corrupt"
        s = settings_store.load()
        return "active" if s["model"] == self.info.key else "ready"

    def refresh(self):
        st = self._state()
        bundled = models.is_bundled(self.info.key)
        self.progress.setVisible(st == "downloading")
        self.cancel_btn.setVisible(st == "downloading")
        self.download_btn.setVisible(st == "absent")
        self.activate_btn.setVisible(st == "ready")
        self.redownload_btn.setVisible(st == "corrupt")
        self.badge.setVisible(st == "active")
        self.delete_btn.setVisible(st in ("ready", "active", "corrupt") and not bundled)
        self.status_label.setVisible(st in ("corrupt", "ready"))
        self.status_label.setText({
            "corrupt": "⚠️ Файл повреждён — скачайте заново",
            "ready": "Скачана, не активна",
        }.get(st, ""))
        self.setProperty("active", st == "active")
        self.style().unpolish(self)
        self.style().polish(self)

    def _download(self):
        self.worker = DownloadWorker(self.info.key, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self.refresh()

    def _redownload(self):
        models.delete_model(self.info.key)
        self._download()

    def _activate(self):
        s = settings_store.load()
        s["model"] = self.info.key
        settings_store.save(s)
        self.page.refresh_rows()

    def _cancel(self):
        if self.worker:
            self.worker.cancel_event.set()

    def _delete(self):
        if QMessageBox.question(self, "Удалить модель",
                                f"Удалить модель «{self.info.title}» с диска?") == QMessageBox.Yes:
            models.delete_model(self.info.key)
            self.page.refresh_rows()

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(100)
        self.progress.setValue(int(done / max(total, 1) * 100))
        self.progress.setFormat(f"{done // 1048576} / {max(total // 1048576, 1)} МБ")
        self.progress.setTextVisible(True)

    def _on_done(self):
        self.worker = None
        self.page.refresh_rows()

    def _on_failed(self, msg: str):
        self.worker = None
        self.page.show_error(msg)
        self.refresh()


class ModelsPage(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(14)

        title = QLabel("Модели распознавания")
        title.setObjectName("h1")
        sub = QLabel("Скачайте модель и нажмите «Активировать». Активная используется для расшифровки. "
                     "Если связь прервётся — загрузка продолжится с места обрыва.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
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
