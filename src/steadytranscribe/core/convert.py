"""Конвертация любого аудио/видео в WAV 16 кГц mono через ffmpeg."""
import os
import subprocess
import sys
import tempfile

SUPPORTED_EXTENSIONS = {
    "wav", "mp3", "m4a", "aac", "ogg", "opus", "flac", "wma",
    "mp4", "mov", "mkv", "avi", "webm", "m4v", "3gp", "amr", "aiff", "caf",
}

FORMATS_DESCRIPTION = "Поддерживаются: WAV, MP3, M4A, OGG, MP4, MOV и другие"


class ConvertError(Exception):
    pass


def ffmpeg_path() -> str:
    """ffmpeg: рядом с приложением (PyInstaller) или из PATH."""
    if getattr(sys, "frozen", False):
        bundled = os.path.join(os.path.dirname(sys.executable), "ffmpeg", "ffmpeg.exe")
        if os.path.exists(bundled):
            return bundled
    return "ffmpeg"


def is_supported(path: str) -> bool:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext in SUPPORTED_EXTENSIONS


def probe_duration(path: str) -> float:
    """Длительность файла в секундах (0 при неудаче) — как fallback в оригинале."""
    exe = ffmpeg_path().replace("ffmpeg", "ffprobe", 1) if "ffmpeg" in ffmpeg_path() else "ffprobe"
    try:
        out = subprocess.run(
            [exe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def to_wav16k(path: str) -> str:
    """Конвертирует файл в 16 кГц mono WAV во временную папку. Возвращает путь."""
    if not os.path.exists(path):
        raise ConvertError("Файл не найден.")
    if not is_supported(path):
        raise ConvertError(FORMATS_DESCRIPTION)
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="steadytranscribe_")
    os.close(fd)
    cmd = [
        ffmpeg_path(), "-y", "-v", "error",
        "-i", path,
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        wav_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        raise ConvertError("ffmpeg не найден. Переустановите приложение.")
    except subprocess.TimeoutExpired:
        raise ConvertError("Конвертация заняла слишком много времени.")
    if result.returncode != 0 or not os.path.getsize(wav_path):
        err = (result.stderr or "").strip().splitlines()
        raise ConvertError("Не удалось обработать аудио: " + (err[-1] if err else "неизвестная ошибка"))
    return wav_path
