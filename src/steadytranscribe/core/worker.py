"""Фоновый поток: конвертация → (диаризация) → распознавание → результат."""
import os

from PySide6.QtCore import QThread, Signal

from . import convert, diarize
from .transcriber import TranscribeError, Transcriber, TranscriptionResult


class TranscriptionWorker(QThread):
    progress = Signal(str, float)          # статус, 0..1
    finished_ok = Signal(object)           # TranscriptionResult (text может быть диалогом)
    failed = Signal(str)

    def __init__(self, transcriber: Transcriber, file_path: str, settings: dict,
                 split_speakers: bool = False, num_speakers: int = 0, parent=None):
        super().__init__(parent)
        self._transcriber = transcriber
        self._file_path = file_path
        self._settings = settings
        self._split = split_speakers and diarize.is_available()
        self._num_speakers = num_speakers
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

            turns = None
            if self._split:
                # диаризация — первые 45% шкалы, распознавание — 45–100%
                turns = diarize.diarize(
                    wav, self._num_speakers,
                    status_cb=lambda s, p: self.progress.emit(s, p),
                    cancel_check=lambda: self._cancelled)
                trans_range = (0.45, 1.0)
            else:
                trans_range = (0.3, 1.0)

            result: TranscriptionResult = self._transcriber.transcribe(
                wav,
                model=self._settings["model"],
                language=self._settings["language"],
                device=self._settings["device"],
                initial_prompt=self._settings["initial_prompt"],
                status_cb=lambda s, p: self.progress.emit(s, p),
                cancel_check=lambda: self._cancelled,
                word_timestamps=self._split,
                progress_range=trans_range,
            )

            if self._split and turns and result.words:
                dialogue = diarize.build_dialogue(result.words, turns)
                if dialogue.strip():
                    result.text = dialogue
            self.finished_ok.emit(result)
        except (convert.ConvertError, TranscribeError) as e:
            self.failed.emit(str(e))
        except InterruptedError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка распознавания: {e}")
        finally:
            if wav and os.path.exists(wav):
                try:
                    os.remove(wav)
                except OSError:
                    pass
