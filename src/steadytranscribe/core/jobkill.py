"""Гарантия «нет процессов-сирот»: все дочерние процессы (ffmpeg, разделение
собеседников) привязываются к Windows Job Object с флагом KILL_ON_JOB_CLOSE.

Когда главный процесс завершается — по закрытию окна ИЛИ при аварийном крахе —
ОС автоматически убивает весь job вместе со всеми дочерними процессами.
Ничего не остаётся висеть в системе, даже если приложение упало.

На macOS/Linux — заглушки (там дочерние процессы завершаются штатной отменой).
"""
import ctypes
import sys

_job = None
_tried = False


def _kernel32():
    """kernel32 с корректными типами: на 64-битной Windows HANDLE — это указатель,
    а дефолтный restype (c_int, 32 бита) обрезал бы его и всё ломал."""
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                          wintypes.LPVOID, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k

# JOBOBJECT_EXTENDED_LIMIT_INFORMATION.BasicLimitInformation.LimitFlags
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JobObjectExtendedLimitInformation = 9
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _ensure_job():
    global _job, _tried
    if _job is not None or _tried:
        return _job
    _tried = True
    if sys.platform != "win32":
        return None
    try:
        k = _kernel32()
        job = k.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = k.SetInformationJobObject(
            job, _JobObjectExtendedLimitInformation,
            ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            k.CloseHandle(job)
            return None
        _job = job
    except Exception:  # noqa: BLE001
        _job = None
    return _job


def assign(pid: int) -> None:
    """Привязать дочерний процесс к job — он умрёт вместе с приложением."""
    if sys.platform != "win32" or not pid:
        return
    job = _ensure_job()
    if not job:
        return
    try:
        k = _kernel32()
        h = k.OpenProcess(_PROCESS_TERMINATE | _PROCESS_SET_QUOTA, False, pid)
        if h:
            k.AssignProcessToJobObject(job, h)
            k.CloseHandle(h)
    except Exception:  # noqa: BLE001
        pass


def kill_all() -> None:
    """Принудительно завершить все дочерние процессы прямо сейчас
    (страховка при закрытии — не ждём выхода из процесса)."""
    if sys.platform != "win32" or _job is None:
        return
    try:
        _kernel32().TerminateJobObject(_job, 1)
    except Exception:  # noqa: BLE001
        pass
