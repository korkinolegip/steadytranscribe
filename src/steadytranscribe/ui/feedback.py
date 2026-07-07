"""Отправка отчёта о проблеме разработчику.

Автоматически (при ошибке) и по кнопке — лог уходит через публичный сервис
ntfy.sh на секретный канал, который знает только разработчик. Без файлов,
GitHub и авторизации. В отчёте только техданные (ОС, процессор, версия, ошибки),
без содержимого записей и текста расшифровок.
"""
import logging
import os
import platform
import urllib.request

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox

from ..storage.settings import app_data_dir

# Секретный канал (как пароль) — логи видит только разработчик, кто знает имя канала.
_NTFY_URL = "https://ntfy.sh/stc-logs-2bfe9693f4dbd247"


def _tail(path: str, limit: int = 6000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()[-limit:]
    except OSError:
        return "(нет файла)"


def collect_report(extra: str = "") -> str:
    from .updater import CURRENT_VERSION
    log = _tail(os.path.join(app_data_dir(), "log.txt"))
    crash = _tail(os.path.join(app_data_dir(), "crash.txt"), 2500)
    return (
        f"Версия: {CURRENT_VERSION}\n"
        f"ОС: {platform.platform()}\n"
        f"Процессор: {platform.processor()}\n"
        f"Событие: {extra or '(ручная отправка)'}\n"
        f"\n=== ЛОГ ===\n{log}\n"
        f"\n=== АВАРИЙНЫЙ ДАМП ===\n{crash}\n")


class _Sender(QThread):
    """Отправка в фоне, чтобы не морозить интерфейс."""

    def __init__(self, body: str, title: str, parent=None):
        super().__init__(parent)
        self.body = body
        self.title = title
        self.ok = False

    def run(self):
        try:
            data = self.body.encode("utf-8")[:60000]
            req = urllib.request.Request(
                _NTFY_URL, data=data, method="POST",
                headers={"Title": self.title.encode("ascii", "replace").decode(),
                         "Tags": "sos", "User-Agent": "SteadyTranscribe"})
            urllib.request.urlopen(req, timeout=15)
            self.ok = True
        except Exception as e:  # noqa: BLE001
            logging.error("Не удалось отправить отчёт: %s", e)


def send_auto(extra: str = "") -> None:
    """Тихая автоотправка при ошибке (без диалогов)."""
    try:
        sender = _Sender(collect_report(extra), "Авто-отчёт об ошибке")
        sender.run()  # синхронно в текущем контексте обработки ошибки
    except Exception:  # noqa: BLE001
        pass


def send_report(parent=None, extra: str = "", title: str = "Отчёт о проблеме") -> None:
    """Отправка по кнопке — с подтверждением результата."""
    report = collect_report(extra)
    QApplication.clipboard().setText(report)  # заодно в буфер, на всякий случай
    sender = _Sender(report, title, parent)
    sender.start()
    sender.wait(20000)
    if sender.ok:
        QMessageBox.information(
            parent, "Отчёт отправлен",
            "Спасибо! Отчёт с логом отправлен разработчику — он увидит проблему "
            "и починит. Ничего пересылать вручную не нужно.")
    else:
        QMessageBox.warning(
            parent, "Не удалось отправить",
            "Отчёт скопирован в буфер обмена — при возможности пришлите его "
            "разработчику. (Не удалось отправить автоматически: нет интернета?)")
