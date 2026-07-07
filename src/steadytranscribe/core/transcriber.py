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
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    confidence: float       # 0..1, среднее по сегментам (как в оригинале — среднее по кускам)
    duration: float         # длительность аудио, сек
    processing_time: float  # сколько заняло распознавание, сек
    language: str = ""
    segments: list = None   # list[Segment] — для диаризации
    words: list = None      # list[Word] — при word_timestamps


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

    def unload(self):
        """Освободить модель из памяти (перед диаризацией — чтобы хватило RAM)."""
        self._model = None
        self._model_key = None
        import gc
        gc.collect()

    def _load_model(self, model_name: str, device: str, status_cb):
        key = (model_name, device)
        if self._model is not None and self._model_key == key:
            return self._model
        from . import models as model_store
        if not model_store.is_downloaded(model_name):
            raise TranscribeError(
                f"Модель «{model_name}» не скачана.\n"
                "Откройте страницу «Модели» и нажмите «Скачать» у нужной модели.")
        if not model_store.is_intact(model_name):
            raise TranscribeError(
                f"Файл модели «{model_name}» повреждён (скачался не полностью).\n"
                "Откройте «Модели», удалите её и скачайте заново — "
                "загрузка теперь продолжается с места обрыва.")
        status_cb("Загрузка модели в память…", 0.1)
        from faster_whisper import WhisperModel

        # Всегда CPU: библиотеки CUDA в сборку не входят (огромные и не нужны),
        # а попытка использовать видеокарту вызывает мгновенный крах.
        # Ускорение обеспечивает AVX2 на процессоре.
        import logging
        # Умеренное число потоков; пониженный приоритет сам заставляет расшифровку
        # уступать процессор активным программам пользователя (регулирует ОС).
        cores = os.cpu_count() or 4
        threads = min(max(cores // 2, 4), 8)
        logging.info("transcribe: движок на CPU, потоков=%s (device игнорируется: %s)",
                     threads, device)
        try:
            self._model = WhisperModel(model_store.model_dir(model_name),
                                       device="cpu", compute_type="int8",
                                       cpu_threads=threads)
            self._model_key = key
            return self._model
        except Exception as e:  # noqa: BLE001
            raise TranscribeError(
                f"Не удалось загрузить модель. Попробуйте удалить её на странице «Модели» "
                f"и скачать заново.\nДетали: {str(e)[:200]}")

    def transcribe(self, wav_path: str, *, model: str, language: str, device: str,
                   initial_prompt: str, status_cb, cancel_check,
                   word_timestamps: bool = False,
                   progress_range: tuple = (0.3, 0.9)) -> TranscriptionResult:
        """status_cb(text, progress 0..1); cancel_check() -> bool.

        word_timestamps=True — вернуть также слова с таймкодами (для диаризации).
        progress_range — куда мапить прогресс распознавания на общей шкале.
        """
        import logging
        from . import priority
        # По умолчанию — пониженный приоритет (не мешаем пользователю). Дальше приоритет
        # автоматически регулируется в реальном времени по активности окна (см. страницу).
        priority.set_background(True)
        logging.info("transcribe: загрузка модели %s (%s)", model, device)
        whisper = self._load_model(model, device, status_cb)
        logging.info("transcribe: модель загружена, старт распознавания")
        status_cb("Анализ файла…", 0.2)

        lang = None if language == "auto" else language
        p_lo, p_hi = progress_range
        # ВАЖНО: словарь-подсказку оформляем как полное предложение с точкой.
        # Список слов через запятую без точки сбивает пунктуацию всего текста —
        # Whisper имитирует стиль подсказки и перестаёт ставить точки.
        prompt = None
        if initial_prompt and initial_prompt.strip():
            words = ", ".join(w.strip() for w in initial_prompt.replace("\n", ",").split(",")
                              if w.strip())
            if words:
                prompt = f"В записи упоминаются такие слова и названия: {words}."
        start = time.monotonic()
        segments, info = whisper.transcribe(
            wav_path,
            language=lang,
            initial_prompt=prompt,
            vad_filter=True,
            # защита от зацикливания на повторах (известная особенность Whisper)
            condition_on_previous_text=False,
            word_timestamps=word_timestamps,
        )
        logging.info("transcribe: VAD пройден, идёт распознавание сегментов")
        duration = float(info.duration or 0.0)

        parts: list[str] = []
        seg_list: list[Segment] = []
        word_list: list[Word] = []
        confidences: list[float] = []
        for seg in segments:  # генератор — распознавание идёт по мере итерации
            if cancel_check():
                raise TranscribeError("Отменено пользователем.")
            parts.append(seg.text.strip())
            seg_list.append(Segment(seg.start, seg.end, seg.text.strip()))
            if word_timestamps and seg.words:
                for w in seg.words:
                    word_list.append(Word(w.start, w.end, w.word))
            if seg.avg_logprob is not None:
                confidences.append(math.exp(min(seg.avg_logprob, 0.0)))
            if duration > 0:
                frac = min(seg.end / duration, 1.0)
                status_cb(f"Распознавание… {int(frac * 100)}%", p_lo + frac * (p_hi - p_lo))

        processing = time.monotonic() - start
        priority.set_background(False)  # вернуть обычный приоритет
        text = " ".join(p for p in parts if p)
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        status_cb("Готово!", 1.0)
        return TranscriptionResult(text, confidence, duration, processing,
                                   info.language or (lang or ""), seg_list, word_list)
