"""База времён обработки: учится на реальных запусках, чтобы точнее оценивать,
сколько займёт расшифровка/разделение.

Храним по каждой операции коэффициент «время обработки / длительность аудио».
Со временем берём медиану последних замеров вместо грубой теоретической оценки —
и прогноз становится точным именно для этого компьютера и этих файлов.

Файл: %APPDATA%/SteadyTranscribe/timings.json
"""
import json
import os

from .settings import app_data_dir

# сколько последних замеров храним на каждую операцию/модель
_MAX_SAMPLES = 40
# теоретические коэффициенты (доля от длительности аудио) — старт, пока нет истории
_DEFAULT_TRANSCRIBE = {"tiny": 0.06, "base": 0.12, "small": 0.25, "medium": 0.5,
                       "large-v3-turbo": 0.45}
_DEFAULT_DIARIZE = 0.35
# вес теоретической оценки в «псевдо-замерах»: чем больше реальных замеров,
# тем меньше влияет теория
_PRIOR_WEIGHT = 3


def _path() -> str:
    return os.path.join(app_data_dir(), "timings.json")


def _load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _save(data: dict) -> None:
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _record(key: str, audio_seconds: float, processing_seconds: float) -> None:
    if audio_seconds <= 0 or processing_seconds <= 0:
        return
    factor = processing_seconds / audio_seconds
    # отсекаем явные выбросы (например, зависший запуск)
    if not (0.001 < factor < 20):
        return
    data = _load()
    samples = data.get(key, [])
    samples.append(round(factor, 4))
    data[key] = samples[-_MAX_SAMPLES:]
    _save(data)


def _factor(key: str, default: float) -> float:
    """Смешиваем теоретическую оценку с КОНСЕРВАТИВНОЙ оценкой реальных замеров.
    Чем больше замеров — тем сильнее доверяем факту.

    Берём max(медиана, среднее) с запасом 10%: медиана показывает типичную
    скорость, но игнорирует «тяжёлый хвост» медленных прогонов (загруженная
    машина, тепловой троттлинг) — а среднее его учитывает. Цель — скорее
    ПЕРЕоценить, чем ПОДоценить (лучше «управился раньше», чем «обещал меньше»)."""
    samples = _load().get(key, [])
    if not samples:
        return default
    n = len(samples)
    base = max(_median(samples), sum(samples) / n) * 1.10
    return (default * _PRIOR_WEIGHT + base * n) / (_PRIOR_WEIGHT + n)


# ---------- расшифровка ----------

def record_transcription(model: str, audio_seconds: float, processing_seconds: float) -> None:
    _record(f"transcribe:{model}", audio_seconds, processing_seconds)


def estimate_transcription(model: str, audio_seconds: float) -> float:
    default = _DEFAULT_TRANSCRIBE.get(model, 0.45)
    return max(audio_seconds * _factor(f"transcribe:{model}", default), 1.0)


# ---------- разделение по собеседникам ----------

def record_diarization(audio_seconds: float, processing_seconds: float) -> None:
    _record("diarize", audio_seconds, processing_seconds)


def estimate_diarization(audio_seconds: float) -> float:
    return max(audio_seconds * _factor("diarize", _DEFAULT_DIARIZE), 1.0)
