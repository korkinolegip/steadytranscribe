"""Каталог моделей и их скачивание с прогрессом (как Voice Engine в FluidVoice)."""
import os
import shutil
import threading
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


@dataclass
class ModelInfo:
    key: str
    title: str
    size_mb: int
    speed_pct: int      # относительная скорость (как Speed % в FluidVoice)
    accuracy_pct: int   # относительное качество (как Accuracy % в FluidVoice)
    note: str = ""


CATALOG = [
    ModelInfo("tiny", "Tiny", 75, 100, 55, "Черновик, максимум скорости"),
    ModelInfo("base", "Base", 145, 90, 65, "Быстрая"),
    ModelInfo("small", "Small", 480, 70, 80, "Баланс — рекомендуется для начала"),
    ModelInfo("medium", "Medium", 1500, 40, 90, "Высокое качество"),
    ModelInfo("large-v3-turbo", "Large v3 Turbo", 1600, 35, 100, "Максимальное качество русского"),
]


def models_root() -> str:
    path = os.path.join(app_data_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path


def repo_dir(key: str) -> str:
    return os.path.join(models_root(), "models--" + _REPOS[key].replace("/", "--"))


def is_downloaded(key: str) -> bool:
    path = repo_dir(key)
    if not os.path.isdir(path):
        return False
    for root, _dirs, files in os.walk(path):
        if any(f.endswith(".bin") for f in files):
            return True
    return False


def delete_model(key: str) -> None:
    shutil.rmtree(repo_dir(key), ignore_errors=True)


def download(key: str, progress_cb, cancel_event: threading.Event) -> None:
    """Скачивает модель с прогрессом; huggingface.co → fallback hf-mirror.com.

    progress_cb(done_bytes, total_bytes).
    """
    from huggingface_hub import HfApi, hf_hub_download

    repo = _REPOS[key]
    errors = []
    for endpoint in (None, "https://hf-mirror.com"):
        try:
            api = HfApi(endpoint=endpoint)
            files = api.list_repo_files(repo)
            infos = api.get_paths_info(repo, files)
            total = sum(i.size or 0 for i in infos)
            done = 0
            for info in infos:
                if cancel_event.is_set():
                    raise InterruptedError("Отменено")
                hf_hub_download(repo, info.path, cache_dir=models_root(),
                                endpoint=endpoint)
                done += info.size or 0
                progress_cb(done, total)
            return
        except InterruptedError:
            delete_model(key)
            raise
        except Exception as e:  # noqa: BLE001 — пробуем зеркало
            errors.append(str(e))
    raise RuntimeError(
        "Не удалось скачать модель. Проверьте интернет.\nДетали: " + errors[-1][:200])
