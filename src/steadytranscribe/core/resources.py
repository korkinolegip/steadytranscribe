"""Единый поиск ресурсов (ассеты, ffmpeg, модели) — работает и в dev, и в PyInstaller."""
import os
import sys


def resource(*parts: str) -> str:
    """Ищет ресурс в нескольких местах:
    - dev: корень репо
    - PyInstaller onedir: рядом с exe И в _internal/
    Возвращает первый существующий путь (или последний кандидат)."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, *parts))
        candidates.append(os.path.join(exe_dir, "_internal", *parts))
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, *parts))
    else:
        root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
        candidates.append(os.path.abspath(os.path.join(root, *parts)))
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]
