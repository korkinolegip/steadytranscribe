"""Автообновление через GitHub Releases.

Вместо SSH-доступа: приложение при запуске проверяет последний релиз в репозитории
и предлагает скачать новый установщик. Обновление выкатывается через `git push` +
тег версии — GitHub Actions собирает установщик и публикует в Releases.
"""
import json
import sys
import urllib.request
import webbrowser

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox

CURRENT_VERSION = "1.1.0"
REPO = "korkinolegip/steadytranscribe"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def _parse_version(tag: str) -> tuple:
    nums = tag.lstrip("vV").split(".")
    try:
        return tuple(int(n) for n in nums[:3])
    except ValueError:
        return (0, 0, 0)


class UpdateChecker(QThread):
    update_available = Signal(str, str)   # версия, url установщика

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
                url = RELEASES_PAGE
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".exe"):
                        url = asset["browser_download_url"]
                        break
                self.update_available.emit(tag.lstrip("vV"), url)
        except Exception:  # noqa: BLE001 — тихо игнорируем (нет сети/приватный репо)
            pass


def check_async(parent) -> UpdateChecker:
    checker = UpdateChecker(parent)

    def on_update(version: str, url: str):
        if QMessageBox.information(
                parent, "Доступно обновление",
                f"Вышла новая версия {version} (у вас {CURRENT_VERSION}).\n"
                "Скачать установщик?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            webbrowser.open(url)

    checker.update_available.connect(on_update)
    checker.start()
    return checker
