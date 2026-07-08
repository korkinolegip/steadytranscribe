"""Управление приоритетом процесса — чтобы расшифровка не мешала работе пользователя.

Понижение приоритета отдаёт процессор активным программам пользователя:
ОС сама решает, кому сейчас нужнее CPU. Расшифровка использует «свободные»
циклы — компьютер остаётся отзывчивым, можно спокойно работать параллельно.

Windows — SetPriorityClass; macOS — taskpolicy -b/-B (фоновый QoS: планировщик
уводит процесс на энергоэффективные ядра и обратно). os.nice() на macOS не
подходит: сдвиг относительный и обратно поднять приоритет без прав нельзя.
"""
import sys

# Windows priority classes
_BELOW_NORMAL = 0x00004000
_NORMAL = 0x00000020
_IDLE = 0x00000040


def _mac_taskpolicy(pid: int, background: bool) -> None:
    import subprocess
    subprocess.run(["/usr/sbin/taskpolicy", "-b" if background else "-B",
                    "-p", str(pid)], capture_output=True, timeout=5)


def set_background(on: bool) -> None:
    """on=True — понизить приоритет (фоновый режим); False — вернуть обычный."""
    if sys.platform == "darwin":
        try:
            import os
            _mac_taskpolicy(os.getpid(), on)
        except Exception:  # noqa: BLE001
            pass
        return
    if sys.platform != "win32":
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
    if not pid:
        return
    if sys.platform == "darwin":
        try:
            _mac_taskpolicy(pid, on)
        except Exception:  # noqa: BLE001
            pass
        return
    if sys.platform != "win32":
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
