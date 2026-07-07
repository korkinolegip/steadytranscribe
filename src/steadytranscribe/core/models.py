"""Каталог моделей и их скачивание с реальным прогрессом (потоково, по чанкам)."""
import os
import shutil
import threading
import urllib.request
from dataclasses import dataclass

from ..storage.settings import app_data_dir

# Репозитории faster-whisper (CTranslate2)
_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
_FILES = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt", "vocabulary.json",
          "preprocessor_config.json"]
_ENDPOINTS = ["https://huggingface.co", "https://hf-mirror.com"]

DEFAULT_MODEL = "large-v3-turbo"


@dataclass
class ModelInfo:
    key: str
    title: str
    size_mb: int
    speed_pct: int      # относительная скорость (как Speed % в FluidVoice)
    accuracy_pct: int   # относительное качество (как Accuracy % в FluidVoice)
    note: str = ""


CATALOG = [
    ModelInfo("large-v3-turbo", "Large v3 Turbo", 1600, 35, 100, "Базовая — максимальное качество"),
    ModelInfo("medium", "Medium", 1500, 40, 90, "Высокое качество"),
    ModelInfo("small", "Small", 480, 70, 80, "Баланс скорости и качества"),
    ModelInfo("base", "Base", 145, 90, 65, "Быстрая"),
    ModelInfo("tiny", "Tiny", 75, 100, 55, "Черновик, максимум скорости"),
]


def models_root() -> str:
    path = os.path.join(app_data_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path


def model_dir(key: str) -> str:
    return os.path.join(models_root(), key)


def is_downloaded(key: str) -> bool:
    d = model_dir(key)
    return os.path.exists(os.path.join(d, "model.bin")) and os.path.exists(
        os.path.join(d, "config.json"))


def delete_model(key: str) -> None:
    shutil.rmtree(model_dir(key), ignore_errors=True)


def _stream_download(url: str, dest: str, done_base: int, total: int,
                     progress_cb, cancel_event: threading.Event) -> int:
    """Скачивает файл чанками, дёргая progress_cb((base+скачано), total). Возвращает размер."""
    req = urllib.request.Request(url, headers={"User-Agent": "SteadyTranscribe"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(dest + ".partial", "wb") as f:
            got = 0
            while True:
                if cancel_event.is_set():
                    raise InterruptedError("Отменено")
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                progress_cb(done_base + got, total)
    os.replace(dest + ".partial", dest)
    return got


def download(key: str, progress_cb, cancel_event: threading.Event) -> None:
    """Скачивает модель с реальным прогрессом; huggingface.co → fallback hf-mirror.com.

    progress_cb(done_bytes, total_bytes) вызывается каждые ~256 КБ.
    """
    repo = _REPOS[key]
    dest_dir = model_dir(key)
    os.makedirs(dest_dir, exist_ok=True)
    errors = []
    for endpoint in _ENDPOINTS:
        try:
            # список файлов и размеры
            import json
            req = urllib.request.Request(f"{endpoint}/api/models/{repo}",
                                         headers={"User-Agent": "SteadyTranscribe"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                meta = json.load(resp)
            available = {s["rfilename"] for s in meta.get("siblings", [])}
            files = [f for f in _FILES if f in available]
            if "model.bin" not in files:
                raise RuntimeError("model.bin не найден в репозитории")
            # общий размер через HEAD запросы неточен на HF — оцениваем по каталогу
            total = next((m.size_mb for m in CATALOG if m.key == key), 500) * 1024 * 1024
            done = 0
            for name in files:
                if is_file_ok(dest_dir, name):
                    continue
                url = f"{endpoint}/{repo}/resolve/main/{name}"
                done += _stream_download(url, os.path.join(dest_dir, name),
                                         done, total, progress_cb, cancel_event)
            progress_cb(total, total)
            return
        except InterruptedError:
            raise
        except Exception as e:  # noqa: BLE001 — пробуем зеркало
            errors.append(f"{endpoint}: {e}")
    raise RuntimeError(
        "Не удалось скачать модель. Проверьте интернет.\nДетали: " + errors[-1][:200])


def is_file_ok(dest_dir: str, name: str) -> bool:
    path = os.path.join(dest_dir, name)
    return os.path.exists(path) and os.path.getsize(path) > 0
