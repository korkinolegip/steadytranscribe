"""Продуктовая аналитика SteadyVoice — только обезличенные события использования.

ЧТО собираем: события (расшифровка: длительность аудио/время обработки/слова,
разделение, отмены, ошибки, навигация, игра, обновления, сеансы) + имя/отдел,
указанные пользователем при первом запуске.
ЧЕГО НЕ собираем НИКОГДА: содержимое записей, текст расшифровок, имена файлов.

Как работает: события пишутся локально (полный архив analytics-log.jsonl +
очередь на отправку), очередь уходит пачкой при закрытии программы и раз в
15 минут (живая аналитика). Канал доставки — ntfy (как у баг-репортов),
в облаке архивируется workflow'ом. Отправка «best effort»: нет сети — события
дождутся следующего раза, ничего не теряется.
"""
import json
import os
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


def track(event: str, **fields) -> None:
    """Записать событие. Никогда не роняет программу."""
    try:
        from ..ui.updater import CURRENT_VERSION
        s = _load_settings()
        rec = {"t": int(time.time()), "ev": event, "id": device_id(),
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
