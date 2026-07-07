"""Разделение по собеседникам (локально, sherpa-onnx).

Модели маленькие (~44 МБ суммарно) и поставляются вместе с приложением —
интернет для диаризации не нужен.
"""
import os
import sys
from dataclasses import dataclass

from .transcriber import Segment, Word


@dataclass
class SpeakerTurn:
    speaker: int   # 0-based
    start: float
    end: float


def _models_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "diarization")
    else:
        base = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "diarization")
    return os.path.abspath(base)


def is_available() -> bool:
    d = _models_dir()
    return (os.path.exists(os.path.join(d, "segmentation.onnx"))
            and os.path.exists(os.path.join(d, "embedding.onnx")))


def diarize(wav_path: str, num_speakers: int, status_cb, cancel_check) -> list[SpeakerTurn]:
    """num_speakers: 0 = авто. Возвращает реплики по времени."""
    import sherpa_onnx
    import soundfile as sf

    status_cb("Определение собеседников…", 0.25)
    audio, _sr = sf.read(wav_path, dtype="float32")
    d = _models_dir()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=os.path.join(d, "segmentation.onnx"))),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=os.path.join(d, "embedding.onnx")),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers if num_speakers > 0 else -1,
            threshold=0.8),
        min_duration_on=0.3, min_duration_off=0.5)
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)

    def progress(processed, total):  # noqa: ANN001
        if cancel_check():
            return 1  # ненулевое значение прерывает обработку
        frac = processed / max(total, 1)
        status_cb(f"Определение собеседников… {int(frac * 100)}%", 0.25 + frac * 0.2)
        return 0

    result = diarizer.process(audio, callback=progress).sort_by_start_time()
    if cancel_check():
        raise InterruptedError("Отменено пользователем.")
    return [SpeakerTurn(s.speaker, s.start, s.end) for s in result]


def _speaker_at(t: float, turns: list[SpeakerTurn]) -> int:
    """Кто говорит в момент t (по максимальному перекрытию точки со реплик)."""
    best, best_overlap = 0, -1.0
    for turn in turns:
        if turn.start <= t <= turn.end:
            return turn.speaker
        # ближайшая по расстоянию, если точка вне всех реплик
        dist = min(abs(t - turn.start), abs(t - turn.end))
        if -dist > best_overlap:
            best_overlap = -dist
            best = turn.speaker
    return best


def build_dialogue(words: list[Word], turns: list[SpeakerTurn]) -> str:
    """Собирает диалог по СЛОВАМ: каждое слово относим к говорящему в его момент.
    Так короткие реплики-вставки («да», «угу») попадают правильному собеседнику."""
    if not words:
        return ""
    lines: list[str] = []
    current, buf = None, []
    for w in words:
        mid = (w.start + w.end) / 2
        speaker = _speaker_at(mid, turns)
        if speaker != current:
            if buf:
                lines.append(f"Собеседник {current + 1}: " + "".join(buf).strip())
            current, buf = speaker, []
        buf.append(w.text)
    if buf:
        lines.append(f"Собеседник {current + 1}: " + "".join(buf).strip())
    return "\n\n".join(lines)
