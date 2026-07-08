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
    """Стабильный отпечаток КОМПЬЮТЕРА (хэш системного MachineGuid) — переживает
    переустановку программы. Видно возвращение пользователя на том же ПК."""
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
        else:
            raw = str(uuid.getnode())
        _machine_cache = hashlib.sha256(str(raw).encode()).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        _machine_cache = "unknown"
    return _machine_cache


def track(event: str, **fields) -> None:
    """Записать событие. Никогда не роняет программу."""
    try:
        from ..ui.updater import CURRENT_VERSION
        s = _load_settings()
        rec = {"t": int(time.time()), "ev": event, "m": machine_id(),
               "id": device_id(),
               "user": s.get("user_name", ""), "dept": s.get("user_dept", ""),
               "v": CURRENT_VERSION}
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
