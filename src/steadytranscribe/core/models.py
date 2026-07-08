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
# Обязательные и опциональные файлы CTranslate2-модели (без запроса API — он нестабилен)
_REQUIRED = ["config.json", "model.bin", "tokenizer.json"]
_OPTIONAL = ["vocabulary.json", "vocabulary.txt", "preprocessor_config.json"]
# hf-mirror ПЕРВЫМ: в некоторых сетях huggingface.co блокируется/рвётся.
# ВАЖНО (2026-07): hf-mirror теперь ПЕРЕНАПРАВЛЯЕТ на CDN HuggingFace, поэтому
# добавлен независимый запасной источник — наши GitHub-релизы с моделями
# (releases/download/models-<ключ>/) + gh-proxy зеркала, как у автообновления.
_ENDPOINTS = ["https://hf-mirror.com", "https://huggingface.co"]
_GH_MODELS = "https://github.com/korkinolegip/steadytranscribe/releases/download"
_GH_MIRRORS = ["", "https://mirror.ghproxy.com/", "https://ghproxy.net/"]


def _bases(key: str, repo: str) -> list:
    """Все источники модели по порядку: HF-зеркало → HF → GitHub (+зеркала)."""
    bases = [f"{e}/{repo}/resolve/main" for e in _ENDPOINTS]
    bases += [f"{m}{_GH_MODELS}/models-{key}" for m in _GH_MIRRORS]
    return bases


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


def _bundled_dir(key: str) -> str:
    """Предустановленная модель (в сборке «с моделью»), рядом с приложением."""
    from .resources import resource
    return resource("models", key)


def _has_files(d: str) -> bool:
    return os.path.exists(os.path.join(d, "model.bin")) and os.path.exists(
        os.path.join(d, "config.json"))


def model_dir(key: str) -> str:
    """Где лежит модель: пользовательская папка приоритетнее, иначе встроенная."""
    user = os.path.join(models_root(), key)
    if _has_files(user):
        return user
    bundled = _bundled_dir(key)
    if _has_files(bundled):
        return bundled
    return user


def is_bundled(key: str) -> bool:
    return _has_files(_bundled_dir(key))


def is_downloaded(key: str) -> bool:
    return _has_files(model_dir(key))


def delete_model(key: str) -> None:
    # удаляем только пользовательскую копию; встроенную не трогаем
    shutil.rmtree(os.path.join(models_root(), key), ignore_errors=True)


def _remote_size(url: str) -> int:
    """Content-Length файла (0 если неизвестно)."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "SteadyTranscribe"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return int(resp.headers.get("Content-Length", 0))


def _download_file(url: str, dest: str, expected: int, done_base: int, total: int,
                   progress_cb, cancel_event: threading.Event, retries: int = 4) -> int:
    """Качает файл в .partial с ДОКАЧКОЙ по Range при обрыве; проверяет итоговый размер.

    Возвращает фактический размер. Кидает ошибку, если размер не совпал с expected.
    """
    partial = dest + ".partial"
    for attempt in range(retries):
        have = os.path.getsize(partial) if os.path.exists(partial) else 0
        if expected and have >= expected:
            break
        headers = {"User-Agent": "SteadyTranscribe"}
        if have:
            headers["Range"] = f"bytes={have}-"      # докачиваем с места обрыва
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                mode = "ab" if have else "wb"
                with open(partial, mode) as f:
                    got = have
                    while True:
                        if cancel_event.is_set():
                            raise InterruptedError("Отменено")
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        progress_cb(done_base + got, total)
        except InterruptedError:
            raise
        except Exception:  # noqa: BLE001 — обрыв: повторим с докачкой
            if attempt == retries - 1:
                raise
            continue
    final = os.path.getsize(partial) if os.path.exists(partial) else 0
    if expected and final != expected:
        raise RuntimeError(f"файл скачан не полностью ({final}/{expected} байт)")
    os.replace(partial, dest)
    return final


def download(key: str, progress_cb, cancel_event: threading.Event) -> None:
    """Скачивает модель надёжно: прямые ссылки, зеркало-first, докачка, проверка размера.

    progress_cb(done_bytes, total_bytes) вызывается каждые ~256 КБ.
    Телеметрия: старт/докачка, отказ каждого источника, скорость и итог —
    видно удалённо, где и почему буксует установка модели у пользователя.
    """
    import time as _time
    from ..storage import analytics
    repo = _REPOS[key]
    dest_dir = os.path.join(models_root(), key)
    os.makedirs(dest_dir, exist_ok=True)
    resume = any(n.endswith(".partial") for n in
                 (os.listdir(dest_dir) if os.path.exists(dest_dir) else []))
    analytics.track("model_dl_start", model=key, resume=resume)
    analytics.flush_async()
    t0 = _time.monotonic()
    errors = []
    for base in _bases(key, repo):
        host = base.split("//")[-1].split("/")[0]
        try:
            # 1) выясняем реальные размеры (обязательные + существующие опциональные)
            plan = []  # (имя, url, размер)
            for name in _REQUIRED:
                size = _remote_size(f"{base}/{name}")
                plan.append((name, f"{base}/{name}", size))
            for name in _OPTIONAL:
                try:
                    size = _remote_size(f"{base}/{name}")
                    if size:
                        plan.append((name, f"{base}/{name}", size))
                except Exception:  # noqa: BLE001 — опциональный файл может отсутствовать
                    pass
            total = sum(s for _, _, s in plan) or 1
            # уже скачанные (целые) файлы засчитываем
            done = 0
            fresh = 0                     # реально скачано СЕЙЧАС (для скорости)
            for name, url, size in plan:
                path = os.path.join(dest_dir, name)
                if os.path.exists(path) and os.path.getsize(path) == size:
                    done += size
                    progress_cb(done, total)
                    continue
                got = _download_file(url, path, size, done, total, progress_cb, cancel_event)
                done += got
                fresh += got
            progress_cb(total, total)
            _write_marker(dest_dir, plan)
            sec = max(_time.monotonic() - t0, 0.1)
            analytics.track("model_dl_done", model=key, src=host,
                            mb=round(total / 1048576),
                            fresh_mb=round(fresh / 1048576), sec=int(sec),
                            mb_s=round(fresh / 1048576 / sec, 2),
                            fails=len(errors))
            analytics.flush_async()
            return
        except InterruptedError:
            analytics.track("model_dl_cancel", model=key)
            analytics.flush_async()
            raise
        except Exception as e:  # noqa: BLE001 — пробуем следующий источник
            analytics.track("model_dl_source_fail", model=key, src=host,
                            err=str(e)[:120])
            errors.append(f"{host}: {e}")
    analytics.track("model_dl_fail", model=key, err=errors[-1][:160] if errors else "?")
    analytics.flush_async()
    raise RuntimeError(
        "Не удалось скачать модель. Проверьте интернет и попробуйте снова "
        "(загрузка продолжится с места обрыва).\nДетали: " + errors[-1][:180])


def _marker_path(dest_dir: str) -> str:
    return os.path.join(dest_dir, ".complete")


def _write_marker(dest_dir: str, plan: list) -> None:
    """Метка целостности: имена и размеры файлов завершённой модели."""
    import json
    data = {name: size for name, _, size in plan}
    with open(_marker_path(dest_dir), "w") as f:
        json.dump(data, f)


def is_intact(key: str) -> bool:
    """Модель на месте И файлы совпадают по размеру с меткой (не битые/не оборванные)."""
    d = model_dir(key)
    if not _has_files(d):
        return False
    marker = _marker_path(d)
    if not os.path.exists(marker):
        # встроенная (bundled) модель без метки — считаем целой
        return d == _bundled_dir(key)
    try:
        import json
        with open(marker) as f:
            expected = json.load(f)
        return all(os.path.exists(os.path.join(d, n)) and os.path.getsize(os.path.join(d, n)) == s
                   for n, s in expected.items())
    except Exception:  # noqa: BLE001
        return False
