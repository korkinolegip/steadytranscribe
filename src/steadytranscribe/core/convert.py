"""Конвертация любого аудио/видео в WAV 16 кГц mono через ffmpeg."""
import os
import subprocess
import sys
import tempfile
import time

SUPPORTED_EXTENSIONS = {
    "wav", "mp3", "m4a", "aac", "ogg", "opus", "flac", "wma",
    "mp4", "mov", "mkv", "avi", "webm", "m4v", "3gp", "amr", "aiff", "caf",
}

FORMATS_DESCRIPTION = "Поддерживаются: WAV, MP3, M4A, OGG, MP4, MOV и другие"


class ConvertError(Exception):
    pass


def _exe(name: str) -> str:
    return name + ".exe" if sys.platform == "win32" else name


def _find_tool(name: str) -> str:
    """Ищет ffmpeg/ffprobe: вшитый в сборку → PATH → типовые пути Homebrew.
    Важно для macOS: у GUI-приложения, запущенного из Finder, PATH не содержит
    /opt/homebrew/bin — без явных кандидатов dev-сборка не нашла бы ffmpeg."""
    if getattr(sys, "frozen", False):
        from .resources import resource
        bundled = resource("ffmpeg", _exe(name))
        if os.path.exists(bundled):
            return bundled
    if sys.platform == "darwin":
        import shutil
        found = shutil.which(name)
        if found:
            return found
        for cand in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
            if os.path.exists(cand):
                return cand
    return name


def ffmpeg_path() -> str:
    """ffmpeg: вшитый в сборку или из PATH."""
    return _find_tool("ffmpeg")


def ffprobe_path() -> str:
    """ffprobe рядом со вшитым ffmpeg (замена только ИМЕНИ файла — не папки)."""
    return _find_tool("ffprobe")


def is_supported(path: str) -> bool:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext in SUPPORTED_EXTENSIONS


def _duration_via_ffmpeg(path: str) -> float:
    """Запасной способ: строка «Duration: HH:MM:SS.xx» из stderr ffmpeg
    (работает, даже если ffprobe не вшит в сборку)."""
    try:
        out = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-i", path],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        import re
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out.stderr or "")
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def probe_duration(path: str) -> float:
    """Длительность файла в секундах (0 при неудаче) — как fallback в оригинале."""
    try:
        out = subprocess.run(
            [ffprobe_path(), "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return float(out.stdout.strip())
    except Exception:
        return _duration_via_ffmpeg(path)


def to_wav16k(path: str, cancel_check=None) -> str:
    """Конвертирует файл в 16 кГц mono WAV во временную папку. Возвращает путь.

    cancel_check() -> bool: если возвращает True — процесс ffmpeg немедленно
    завершается (чтобы «Отмена» работала мгновенно даже на больших файлах).
    """
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
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        raise ConvertError("ffmpeg не найден. Переустановите приложение.")
    from . import jobkill
    jobkill.assign(proc.pid)   # умрёт вместе с приложением — без сирот
    deadline = time.monotonic() + 1800
    while True:
        try:
            proc.wait(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            if cancel_check and cancel_check():
                proc.kill()
                proc.wait(timeout=5)
                raise ConvertError("Отменено пользователем.")
            if time.monotonic() > deadline:
                proc.kill()
                proc.wait(timeout=5)
                raise ConvertError("Конвертация заняла слишком много времени.")
    stderr = (proc.stderr.read() if proc.stderr else "") or ""
    if proc.returncode != 0 or not os.path.getsize(wav_path):
        err = stderr.strip().splitlines()
        raise ConvertError("Не удалось обработать аудио: " + (err[-1] if err else "неизвестная ошибка"))
    return wav_path
