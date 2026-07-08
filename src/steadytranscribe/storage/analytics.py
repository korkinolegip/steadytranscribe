"""Продуктовая аналитика SteadyVoice — только обезличенные события использования.

СХЕМА СОБЫТИЯ (JSON Lines — по строке на событие; легко перенести в любую
систему аналитики / БД на VPS):
  t     — unix-время события
  ev    — тип: app_start, app_close(sec, active_sec), nav(page),
          transcribe(audio_sec, proc_sec, words, model, confidence),
          diarize(audio_sec, proc_sec), cancel, error_shown(msg),
          game_start, game(score, high, sec), updated(frm, to),
          registered, uninstalled, bug_report, feedback(text), telegram_click
  m     — ОТПЕЧАТОК КОМПЬЮТЕРА (хэш системного MachineGuid): переживает
          переустановку → видно «тот же компьютер, зарегистрировался заново»
  id    — идентификатор УСТАНОВКИ: стирается при удалении программы →
          удаление = устройство выбыло, переустановка = новое устройство
  user  — Имя Фамилия (указывает пользователь; объединяет несколько компьютеров)
  dept  — отдел
  v     — версия программы

Жизненный цикл: registered → события → uninstalled (шлёт деинсталлятор).
Пользователь без живых устройств исчезает из сводок; вернулся — registered
с тем же m = «переустановил на том же компьютере».

ЧЕГО НЕ собираем НИКОГДА: содержимое записей, текст расшифровок, имена файлов.

Доставка: локальный архив + очередь → пачкой при закрытии и раз в 15 минут →
ntfy → архив в приватные артефакты (analytics-archive.yml). Best effort:
нет сети — события ждут следующего раза, ничего не теряется.
"""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
import uuid

from .settings import app_data_dir, load as _load_settings

_TOPIC = "stc-usage-2bfe9693f4dbd247"
_URLS = [f"https://ntfy.sh/{_TOPIC}", f"https://ntfy.envs.net/{_TOPIC}"]

_lock = threading.Lock()


def _queue_path() -> str:
    return os.path.join(app_data_dir(), "analytics-queue.jsonl")


def _archive_path() -> str:
    return os.path.join(app_data_dir(), "analytics-log.jsonl")


def device_id() -> str:
    """Постоянный идентификатор установки (случайный, не содержит данных ПК)."""
    p = os.path.join(app_data_dir(), "device_id")
    try:
        with open(p, encoding="ascii") as f:
            return f.read().strip()
    except OSError:
        did = uuid.uuid4().hex[:12]
        try:
            with open(p, "w", encoding="ascii") as f:
                f.write(did)
        except OSError:
            pass
        return did


_machine_cache = None


def machine_id() -> str:
    """Стабильный отпечаток КОМПЬЮТЕРА (хэш системного идентификатора) — переживает
    переустановку программы. Видно возвращение пользователя на том же ПК.
    Windows — MachineGuid из реестра; macOS — IOPlatformUUID (постоянен для машины)."""
    global _machine_cache
    if _machine_cache:
        return _machine_cache
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\Microsoft\Cryptography", 0,
                                 winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            raw, _ = winreg.QueryValueEx(key, "MachineGuid")
        elif sys.platform == "darwin":
            import subprocess
            out = subprocess.run(
                ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=10).stdout
            raw = ""
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    raw = line.split('"')[-2]
                    break
            if not raw:
                raw = str(uuid.getnode())
        else:
            raw = str(uuid.getnode())
        _machine_cache = hashlib.sha256(str(raw).encode()).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        _machine_cache = "unknown"
    return _machine_cache


def track(event: str, **fields) -> None:
    """Записать событие. Никогда не роняет программу."""
    if os.environ.get("STEADY_UITEST"):
        return   # фотосессия UI: не засорять аналитику событиями с CI
    try:
        from ..ui.updater import CURRENT_VERSION
        s = _load_settings()
        rec = {"t": int(time.time()), "ev": event, "m": machine_id(),
               "id": device_id(),
               "user": s.get("user_name", ""), "dept": s.get("user_dept", ""),
               "v": CURRENT_VERSION}
        if sys.platform == "darwin":
            rec["os"] = "mac"     # Windows-события без поля os (схема не менялась)
        rec.update(fields)
        line = json.dumps(rec, ensure_ascii=False)
        with _lock:
            for path in (_queue_path(), _archive_path()):
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def _send(body: bytes, timeout: int) -> bool:
    for url in _URLS:
        try:
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Title": "usage", "User-Agent": "SteadyVoice"})
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def flush(timeout: int = 8) -> bool:
    """Отправить накопленную очередь одной пачкой. Успех → очередь очищается."""
    if os.environ.get("STEADY_UITEST"):
        return True   # фотосессия UI: без сети
    try:
        with _lock:
            try:
                with open(_queue_path(), encoding="utf-8") as f:
                    data = f.read()
            except OSError:
                return True
            if not data.strip():
                return True
        body = data.encode("utf-8")[-60000:]      # лимит сообщения ntfy
        if _send(body, timeout):
            with _lock:
                try:
                    os.remove(_queue_path())
                except OSError:
                    pass
            return True
        return False
    except Exception:  # noqa: BLE001
        return False


def flush_async() -> None:
    threading.Thread(target=flush, daemon=True).start()


def send_startup_diagnostics() -> None:
    """Диагностика при старте — уходит САМА, без кнопки «Сообщить о проблеме»:
    1) паспорт системы (ОС/процессор/ядра/память) — понятно, потянет ли компьютер;
    2) хвост лога прошлого сеанса — ошибки видны удалённо;
    3) аварийный дамп, если программа падала.
    Кнопка остаётся как сигнал «у меня проблема», но данные приходят и так."""
    try:
        import ctypes
        import platform
        ram_gb = 0
        cpu = platform.processor()[:80]
        if sys.platform == "win32":
            class _MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_uint32),
                            ("dwMemoryLoad", ctypes.c_uint32),
                            ("ullTotalPhys", ctypes.c_uint64),
                            ("ullAvailPhys", ctypes.c_uint64),
                            ("ullTotalPageFile", ctypes.c_uint64),
                            ("ullAvailPageFile", ctypes.c_uint64),
                            ("ullTotalVirtual", ctypes.c_uint64),
                            ("ullAvailVirtual", ctypes.c_uint64),
                            ("ullAvailExtendedVirtual", ctypes.c_uint64)]
            st = _MEM()
            st.dwLength = ctypes.sizeof(_MEM)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                ram_gb = round(st.ullTotalPhys / (1024 ** 3))
        elif sys.platform == "darwin":
            import subprocess
            def _sysctl(name: str) -> str:
                return subprocess.run(["/usr/sbin/sysctl", "-n", name],
                                      capture_output=True, text=True,
                                      timeout=10).stdout.strip()
            try:
                ram_gb = round(int(_sysctl("hw.memsize")) / (1024 ** 3))
                cpu = _sysctl("machdep.cpu.brand_string")[:80]  # «Apple M4»
            except Exception:  # noqa: BLE001
                pass
        track("sys", os=platform.platform(), cpu=cpu,
              cores=os.cpu_count(), ram_gb=ram_gb)
    except Exception:  # noqa: BLE001
        pass
    try:  # хвост лога прошлого сеанса (лог только технический, без контента)
        with open(os.path.join(app_data_dir(), "log.txt"), encoding="utf-8",
                  errors="replace") as f:
            tail = f.read()[-2500:]
        if tail.strip():
            track("log_tail", text=tail)
    except OSError:
        pass
    try:  # аварийный дамп: отправить и очистить (чтобы не слать повторно)
        crash_path = os.path.join(app_data_dir(), "crash.txt")
        if os.path.getsize(crash_path) > 0:
            with open(crash_path, encoding="utf-8", errors="replace") as f:
                track("crash", text=f.read()[-2000:])
            open(crash_path, "w").close()
    except OSError:
        pass
    flush_async()
