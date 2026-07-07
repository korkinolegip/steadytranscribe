"""Фоновый поток транскрипции: конвертация → распознавание → результат."""
import os

from PySide6.QtCore import QThread, Signal

from . import convert
from .transcriber import TranscribeError, Transcriber, TranscriptionResult


class TranscriptionWorker(QThread):
    progress = Signal(str, float)          # статус, 0..1
    finished_ok = Signal(object)           # TranscriptionResult
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
            self.progress.emit("Подготовка модели…", 0.1)
            self.progress.emit("Анализ файла…", 0.2)
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
            )
            self.finished_ok.emit(result)
        except (convert.ConvertError, TranscribeError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001 — как .transcriptionFailed в оригинале
            self.failed.emit(f"Ошибка распознавания: {e}")
        finally:
            if wav and os.path.exists(wav):
                try:
                    os.remove(wav)
                except OSError:
                    pass
