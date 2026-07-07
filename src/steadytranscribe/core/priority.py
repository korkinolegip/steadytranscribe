"""Управление приоритетом процесса — чтобы расшифровка не мешала работе пользователя.

Понижение приоритета отдаёт процессор активным программам пользователя:
Windows сама решает, кому сейчас нужнее CPU. Расшифровка использует «свободные»
циклы — компьютер остаётся отзывчивым, можно спокойно работать параллельно.
"""
import sys

# Windows priority classes
_BELOW_NORMAL = 0x00004000
_NORMAL = 0x00000020
_IDLE = 0x00000040


def set_background(on: bool) -> None:
    """on=True — понизить приоритет (фоновый режим); False — вернуть обычный."""
    if sys.platform != "win32":
        try:
            import os
            os.nice(10 if on else 0)  # noqa: сдвиг приоритета на *nix
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        import ctypes
        h = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(h, _BELOW_NORMAL if on else _NORMAL)
    except Exception:  # noqa: BLE001
        pass


def creationflag(background: bool) -> int:
    """Флаг приоритета для запуска дочернего процесса (диаризация)."""
    if sys.platform == "win32" and background:
        return _BELOW_NORMAL
    return 0


def set_pid_background(pid: int, on: bool) -> None:
    """Приоритет ДОЧЕРНЕГО процесса (разделение по собеседникам).

    Та же авто-регулировка, что у расшифровки: пользователь ждёт у окна →
    обычный приоритет (быстрее); ушёл работать в другое приложение →
    пониженный (уступаем ресурсы). Без этого разделение всегда сидело
    на пониженном приоритете и казалось непомерно долгим."""
    if sys.platform != "win32" or not pid:
        return
    try:
        import ctypes
        PROCESS_SET_INFORMATION = 0x0200
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
        if h:
            k.SetPriorityClass(h, _BELOW_NORMAL if on else _NORMAL)
            k.CloseHandle(h)
    except Exception:  # noqa: BLE001
        pass
