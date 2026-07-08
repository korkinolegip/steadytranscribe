"""Проигрывание короткого фрагмента WAV (для «прослушать голос собеседника»).

Системный проигрыватель (afplay на macOS, PowerShell SoundPlayer на Windows)
через временный WAV. Надёжнее QAudioSink/QMediaPlayer: не зависит от
Qt-аудиоплагина, который капризен в собранном приложении. WAV пишем средствами
стандартной библиотеки — новых зависимостей нет.
"""
import os
import subprocess
import sys
import tempfile
import wave


class ClipPlayer:
    """Один активный фрагмент за раз (эксклюзивно, как в Plaud)."""

    def __init__(self):
        self._on_stop = None
        self._proc = None
        self._tmp = None
        self._poll = None

    def play(self, pcm_bytes: bytes, sample_rate: int = 16000, on_stop=None) -> None:
        self.stop()
        self._on_stop = on_stop
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="steadyvoice_clip_")
        os.close(fd)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm_bytes)
        self._tmp = path
        if sys.platform == "darwin":
            self._proc = subprocess.Popen(["/usr/bin/afplay", path])
        elif sys.platform == "win32":
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command",
                 f"(New-Object Media.SoundPlayer '{path}').PlaySync()"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            self._proc = subprocess.Popen(["aplay", "-q", path])
        # опрос завершения — вернуть кнопку в ▶
        from PySide6.QtCore import QTimer
        self._poll = QTimer()
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._check)
        self._poll.start()

    def _check(self):
        if self._proc is not None and self._proc.poll() is not None:
            cb, self._on_stop = self._on_stop, None
            self.stop()
            if cb:
                cb()

    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._poll is not None:
            self._poll.stop()
            self._poll = None
        if self._proc is not None:
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._proc = None
        if self._tmp is not None:
            try:
                os.remove(self._tmp)
            except OSError:
                pass
            self._tmp = None


def extract_pcm(wav_path: str, start: float, end: float) -> bytes:
    """Вырезает [start, end] из WAV как PCM int16 mono 16 кГц."""
    import numpy as np
    import soundfile as sf
    audio, sr = sf.read(wav_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    a = int(max(start, 0) * sr)
    b = int(min(end, len(audio) / sr) * sr)
    clip = audio[a:b]
    pcm = np.clip(clip * 32767.0, -32768, 32767).astype("<i2")
    return pcm.tobytes(), sr
