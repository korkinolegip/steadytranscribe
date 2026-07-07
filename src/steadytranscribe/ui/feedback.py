"""Отправка отчёта о проблеме: собирает лог и открывает готовый GitHub Issue.

Без сервера и без вшитых токенов (публичное приложение) — пользователь жмёт
одну кнопку «Отправить», отчёт с логом уходит в github.com/.../issues,
где разработчик его видит.
"""
import os
import platform
import urllib.parse
import webbrowser

from ..core.resources import resource  # noqa: F401 (для единообразия)
from ..storage.settings import app_data_dir

REPO = "korkinolegip/steadytranscribe"


def _tail(path: str, limit: int = 3000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()[-limit:]
    except OSError:
        return "(нет файла)"


def collect_report(extra: str = "") -> str:
    from .updater import CURRENT_VERSION
    log = _tail(os.path.join(app_data_dir(), "log.txt"))
    crash = _tail(os.path.join(app_data_dir(), "crash.txt"), 1500)
    return (
        f"**Версия:** {CURRENT_VERSION}\n"
        f"**ОС:** {platform.platform()}\n"
        f"**Процессор:** {platform.processor()}\n\n"
        f"**Что делал(а):**\n{extra or '(опишите, что происходило)'}\n\n"
        f"**Лог:**\n```\n{log}\n```\n"
        f"**Аварийный дамп:**\n```\n{crash}\n```\n")


def send_report(parent=None, extra: str = "", title: str = "Отчёт о проблеме") -> None:
    """Открывает предзаполненный GitHub Issue с логом."""
    body = collect_report(extra)
    # GitHub ограничивает длину URL — режем тело под ~7000 символов
    body = body[:7000]
    url = (f"https://github.com/{REPO}/issues/new?"
           + urllib.parse.urlencode({"title": title, "body": body, "labels": "bug"}))
    webbrowser.open(url)
