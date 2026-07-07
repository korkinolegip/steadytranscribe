"""Отчёт о проблеме без привязки к GitHub: сохраняет лог в файл на Рабочий стол
и копирует в буфер обмена — пользователь пересылает его любым удобным способом.
"""
import os
import platform

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ..storage.settings import app_data_dir


def _tail(path: str, limit: int = 8000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()[-limit:]
    except OSError:
        return "(файл отсутствует)"


def collect_report(extra: str = "") -> str:
    from .updater import CURRENT_VERSION
    log = _tail(os.path.join(app_data_dir(), "log.txt"))
    crash = _tail(os.path.join(app_data_dir(), "crash.txt"), 4000)
    return (
        f"Версия: {CURRENT_VERSION}\n"
        f"ОС: {platform.platform()}\n"
        f"Процессор: {platform.processor()}\n"
        f"Что делал(а): {extra or '(не указано)'}\n"
        f"\n===== ЛОГ =====\n{log}\n"
        f"\n===== АВАРИЙНЫЙ ДАМП =====\n{crash}\n")


def _desktop() -> str:
    home = os.path.expanduser("~")
    for name in ("Desktop", "Рабочий стол"):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            return p
    return home


def send_report(parent=None, extra: str = "", title: str = "Отчёт о проблеме") -> None:
    """Сохраняет отчёт в файл (диалог сохранения, по умолчанию — Рабочий стол)
    и копирует его в буфер обмена."""
    report = collect_report(extra)
    QApplication.clipboard().setText(report)

    default = os.path.join(_desktop(), "SteadyTranscribe-отчёт.txt")
    path, _ = QFileDialog.getSaveFileName(
        parent, "Сохранить отчёт о проблеме", default, "Текст (*.txt)")
    if path:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
        except OSError:
            path = None

    msg = ("Отчёт скопирован в буфер обмена"
           + (f"\nи сохранён в файл:\n{path}" if path else "")
           + "\n\nПришлите его разработчику любым удобным способом "
             "(мессенджер, почта).")
    QMessageBox.information(parent, "Отчёт готов", msg)
