"""Фоновые потоки: транскрипция и (отдельно, по кнопке) диаризация."""
import os

from PySide6.QtCore import QThread, Signal

from . import convert, diarize
from .transcriber import TranscribeError, Transcriber, TranscriptionResult


class TranscriptionWorker(QThread):
    """Файл → текст. Служебный WAV сохраняется для последующей диаризации
    (удаляет его владелец-страница)."""
    progress = Signal(str, float)          # статус, 0..1
    finished_ok = Signal(object, str)      # TranscriptionResult, wav_path
    failed = Signal(str)

    def __init__(self, transcriber: Transcriber, file_path: str, settings: dict, parent=None):
        super().__init__(parent)
        self._transcriber = transcriber
        self._file_path = file_path
        self._settings = settings
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        wav = None
        try:
            self.progress.emit("Подготовка…", 0.05)
            wav = convert.to_wav16k(self._file_path)
            if self._cancelled:
                raise TranscribeError("Отменено пользователем.")
            result: TranscriptionResult = self._transcriber.transcribe(
                wav,
                model=self._settings["model"],
                language=self._settings["language"],
                device=self._settings["device"],
                initial_prompt=self._settings["initial_prompt"],
                status_cb=lambda s, p: self.progress.emit(s, p),
                cancel_check=lambda: self._cancelled,
                word_timestamps=True,     # всегда: нужно для «Разделить по собеседникам»
                progress_range=(0.25, 1.0),
            )
            self.finished_ok.emit(result, wav)
            return
        except (convert.ConvertError, TranscribeError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка распознавания: {e}")
        if wav and os.path.exists(wav):
            try:
                os.remove(wav)
            except OSError:
                pass


class DiarizationWorker(QThread):
    """Готовый результат + WAV → текст-диалог по собеседникам."""
    progress = Signal(str, float)
    finished_ok = Signal(str)              # текст-диалог
    failed = Signal(str)

    def __init__(self, wav_path: str, words: list, num_speakers: int, parent=None):
        super().__init__(parent)
        self._wav = wav_path
        self._words = words
        self._num = num_speakers
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        """Диаризация в ОТДЕЛЬНОМ ПРОЦЕССЕ — интерфейс не зависает (нативная
        библиотека иначе держит GIL и морозит окно)."""
        import json
        import subprocess
        import sys
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--diarize", self._wav, str(self._num)]
            else:
                cmd = [sys.executable, "-m", "steadytranscribe.app",
                       "--diarize", self._wav, str(self._num)]
            env = dict(os.environ, PYTHONPATH="src")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            turns_raw = None
            for line in proc.stdout:
                if self._cancelled:
                    proc.terminate()
                    self.failed.emit("Отменено пользователем.")
                    return
                line = line.strip()
                if line.startswith("PROGRESS "):
                    self.progress.emit("Определение собеседников…", float(line[9:]))
                elif line.startswith("RESULT "):
                    turns_raw = json.loads(line[7:])
            proc.wait()
            if turns_raw is None:
                raise RuntimeError("не удалось выполнить разделение")
            turns = [diarize.SpeakerTurn(sp, st, en) for sp, st, en in turns_raw]
            dialogue = diarize.build_dialogue(self._words, turns)
            if not dialogue.strip():
                raise RuntimeError("Не удалось разделить запись на собеседников.")
            self.finished_ok.emit(dialogue)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка разделения: {e}")
