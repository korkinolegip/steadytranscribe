"""Автообновление через GitHub Releases — полностью внутри программы.

При запуске проверяет последнюю версию. Если новее — по кнопке скачивает
установщик и запускает его в ТИХОМ режиме (/VERYSILENT): без мастера,
без прав администратора (установка в пользовательскую папку), с автоперезапуском.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout,
)

CURRENT_VERSION = "1.4.4"
REPO = "korkinolegip/steadytranscribe"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def _parse_version(tag: str) -> tuple:
    nums = tag.lstrip("vV").split(".")
    try:
        return tuple(int(n) for n in nums[:3])
    except ValueError:
        return (0, 0, 0)


class UpdateChecker(QThread):
    """Проверяет новую версию. Отдаёт версию и URL ЛЁГКОГО установщика (без модели)."""
    update_available = Signal(str, str)

    def run(self):
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "SteadyTranscribe"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
            tag = data.get("tag_name", "")
            if _parse_version(tag) > _parse_version(CURRENT_VERSION):
                exes = [a for a in data.get("assets", []) if a["name"].endswith(".exe")]
                light = [a for a in exes if "with-model" not in a["name"].lower()]
                pick = light or exes
                url = pick[0]["browser_download_url"] if pick else RELEASES_PAGE
                self.update_available.emit(tag.lstrip("vV"), url)
        except Exception:  # noqa: BLE001
            pass


class InstallerDownloader(QThread):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            dest = os.path.join(tempfile.gettempdir(), "SteadyTranscribe-Update.exe")
            req = urllib.request.Request(self.url, headers={"User-Agent": "SteadyTranscribe"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                got = 0
                with open(dest, "wb") as f:
                    while True:
                        if self._cancel:
                            raise InterruptedError
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        self.progress.emit(got, total)
            self.done.emit(dest)
        except InterruptedError:
            self.failed.emit("Обновление отменено.")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Не удалось скачать обновление: {e}")


class UpdateDialog(QDialog):
    """Скачивает и тихо устанавливает обновление — всё внутри программы."""

    def __init__(self, version: str, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.setWindowTitle("Обновление SteadyTranscribe")
        self.setMinimumWidth(460)
        self.downloader = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        self.label = QLabel(
            f"Доступна версия <b>{version}</b> (у вас {CURRENT_VERSION}).<br>"
            "Программа скачает и установит обновление сама, затем перезапустится.")
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.hide()
        self.status = QLabel()
        self.status.setObjectName("hint")
        lay.addWidget(self.progress)
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.update_btn = QPushButton("⬇ Обновить сейчас")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._start)
        self.later_btn = QPushButton("Позже")
        self.later_btn.clicked.connect(self.reject)
        btns.addWidget(self.update_btn)
        btns.addWidget(self.later_btn)
        lay.addLayout(btns)

    def _start(self):
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.progress.show()
        self.status.setText("Скачивание обновления…")
        self.downloader = InstallerDownloader(self.url, self)
        self.downloader.progress.connect(self._on_progress)
        self.downloader.done.connect(self._on_done)
        self.downloader.failed.connect(self._on_failed)
        self.downloader.start()

    def _on_progress(self, done: int, total: int):
        if total:
            self.progress.setMaximum(100)
            self.progress.setValue(int(done / total * 100))
            self.progress.setFormat(f"{done // 1048576} / {total // 1048576} МБ")
        else:
            self.progress.setMaximum(0)

    def _on_done(self, installer_path: str):
        self.status.setText("Установка обновления… Программа перезапустится.")
        try:
            # /VERYSILENT — тихая установка без мастера; per-user → без UAC;
            # установщик сам закроет приложение, поставит новую версию и запустит её.
            subprocess.Popen([installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES",
                              "/NORESTART"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:  # noqa: BLE001
            self._on_failed(f"Не удалось запустить установку: {e}")
            return
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_failed(self, msg: str):
        self.update_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        self.progress.hide()
        self.status.setText(f"⚠️ {msg}")


def check_async(parent) -> UpdateChecker:
    checker = UpdateChecker(parent)
    checker.update_available.connect(
        lambda version, url: UpdateDialog(version, url, parent).exec())
    checker.start()
    return checker
