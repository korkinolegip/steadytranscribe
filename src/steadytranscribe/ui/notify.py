"""Системные уведомления «файл готов / программа обновлена».

Windows — баллон у иконки в трее (QSystemTrayIcon.showMessage).
macOS — Центр уведомлений через osascript: работает из любого процесса без
разрешений, в отличие от QSystemTrayIcon, которому нужен подписанный бандл.
"""
import sys


def send(tray, title: str, text: str, msecs: int = 6000) -> None:
    """Показать уведомление. tray может быть None (на macOS не используется)."""
    if sys.platform == "darwin":
        try:
            import subprocess
            def esc(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(
                ["/usr/bin/osascript", "-e",
                 f'display notification "{esc(text)}" with title "{esc(title)}"'])
            return
        except Exception:  # noqa: BLE001
            pass
    if tray is not None:
        from PySide6.QtWidgets import QSystemTrayIcon
        tray.showMessage(title, text, QSystemTrayIcon.Information, msecs)
