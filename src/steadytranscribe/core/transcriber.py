"""Локальное распознавание через faster-whisper (CTranslate2).

Модель скачивается при первом использовании в %APPDATA%/SteadyTranscribe/models.
При недоступности huggingface.co автоматически пробуем зеркало hf-mirror.com.
"""
import math
import os
import time
from dataclasses import dataclass

from ..storage.settings import app_data_dir


class TranscribeError(Exception):
    pass


@dataclass
class TranscriptionResult:
    text: str
    confidence: float       # 0..1, среднее по сегментам (как в оригинале — среднее по кускам)
    duration: float         # длительность аудио, сек
    processing_time: float  # сколько заняло распознавание, сек
    language: str = ""


def models_dir() -> str:
    path = os.path.join(app_data_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path


def is_model_downloaded(model: str) -> bool:
    root = models_dir()
    marker = f"models--Systran--faster-whisper-{model}"
    alt = f"models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
    for name in os.listdir(root) if os.path.exists(root) else []:
        if name in (marker, alt) and model in name.replace("large-v3-turbo", "large-v3-turbo"):
            return True
    # достаточно наличия каталога с именем модели
    return any(model in name for name in (os.listdir(root) if os.path.exists(root) else []))


class Transcriber:
    """Держит загруженную модель между запусками (как ASRService в оригинале)."""

    def __init__(self):
        self._model = None
        self._model_key = None

    def _load_model(self, model_name: str, device: str, status_cb):
        key = (model_name, device)
        if self._model is not None and self._model_key == key:
            return self._model
        status_cb("Подготовка модели…", 0.1)
        from faster_whisper import WhisperModel

        kwargs = dict(
            download_root=models_dir(),
            compute_type="int8",
        )
        dev = "auto" if device == "auto" else device
        errors = []
        for endpoint in (None, "https://hf-mirror.com"):
            try:
                if endpoint:
                    os.environ["HF_ENDPOINT"] = endpoint
                    status_cb("Загрузка модели через зеркало…", 0.1)
                self._model = WhisperModel(model_name, device=dev, **kwargs)
                self._model_key = key
                return self._model
            except Exception as e:  # noqa: BLE001 — пробуем зеркало при любой сетевой ошибке
                errors.append(str(e))
            finally:
                os.environ.pop("HF_ENDPOINT", None)
        raise TranscribeError(
            "Не удалось загрузить модель распознавания.\n"
            "Проверьте интернет (модель скачивается один раз) или смените зеркало в настройках.\n"
            f"Детали: {errors[-1][:200]}"
        )

    def transcribe(self, wav_path: str, *, model: str, language: str, device: str,
                   initial_prompt: str, status_cb, cancel_check) -> TranscriptionResult:
        """status_cb(text, progress 0..1); cancel_check() -> bool."""
        whisper = self._load_model(model, device, status_cb)
        status_cb("Анализ файла…", 0.2)

        lang = None if language == "auto" else language
        start = time.monotonic()
        segments, info = whisper.transcribe(
            wav_path,
            language=lang,
            initial_prompt=initial_prompt or None,
            vad_filter=True,
        )
        duration = float(info.duration or 0.0)

        parts: list[str] = []
        confidences: list[float] = []
        for seg in segments:  # генератор — распознавание идёт по мере итерации
            if cancel_check():
                raise TranscribeError("Отменено пользователем.")
            parts.append(seg.text.strip())
            if seg.avg_logprob is not None:
                confidences.append(math.exp(min(seg.avg_logprob, 0.0)))
            if duration > 0:
                # как в оригинале: диапазон 30–90%
                frac = min(seg.end / duration, 1.0)
                status_cb(f"Распознавание… {int(frac * 100)}%", 0.3 + frac * 0.6)

        processing = time.monotonic() - start
        text = " ".join(p for p in parts if p)
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        status_cb("Готово!", 1.0)
        return TranscriptionResult(text, confidence, duration, processing,
                                   info.language or (lang or ""))
