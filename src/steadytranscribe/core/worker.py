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
            wav = convert.to_wav16k(self._file_path, cancel_check=lambda: self._cancelled)
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
    # текст-диалог, {«Собеседник N»: (start, end)}, {«Собеседник N»: вектор-центроид}
    finished_ok = Signal(str, dict, dict)
    failed = Signal(str)

    def __init__(self, wav_path: str, words: list, num_speakers: int, parent=None):
        super().__init__(parent)
        self._wav = wav_path
        self._words = words
        self._num = num_speakers
        self._cancelled = False
        self._proc = None

    def cancel(self):
        self._cancelled = True
        self._kill_proc()

    def proc_pid(self) -> int:
        """PID подпроцесса разделения (0, если ещё не запущен) — для авто-приоритета."""
        p = self._proc
        return p.pid if p is not None and p.poll() is None else 0

    def _kill_proc(self):
        """Жёстко завершить дочерний процесс — чтобы не оставался сиротой."""
        p = self._proc
        if p is not None and p.poll() is None:
            try:
                p.kill()
                p.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass

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
            # абсолютный путь к src: работает из любого cwd (раньше был
            # относительный "src" — ломался при запуске не из корня репо)
            src_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            env = dict(os.environ, PYTHONPATH=src_root)
            from . import priority as _prio
            # разделение — долгая фоновая операция, всегда пониженный приоритет
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | _prio.creationflag(True)
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=flags)
            from . import jobkill
            jobkill.assign(self._proc.pid)   # умрёт вместе с приложением — без сирот
            turns_raw = None
            embed_raw = {}
            for line in self._proc.stdout:
                if self._cancelled:
                    self._kill_proc()
                    self.failed.emit("Отменено пользователем.")
                    return
                line = line.strip()
                if line.startswith("PROGRESS "):
                    self.progress.emit("Определение собеседников…", float(line[9:]))
                elif line.startswith("RESULT "):
                    turns_raw = json.loads(line[7:])
                elif line.startswith("EMBED "):
                    embed_raw = json.loads(line[6:])
            self._proc.wait()
            if self._cancelled:
                self.failed.emit("Отменено пользователем.")
                return
            if turns_raw is None:
                raise RuntimeError("не удалось выполнить разделение")
            turns = [diarize.SpeakerTurn(sp, st, en) for sp, st, en in turns_raw]
            dialogue = diarize.build_dialogue(self._words, turns)
            if not dialogue.strip():
                raise RuntimeError("Не удалось разделить запись на собеседников.")
            # интервалы образцовых фрагментов — для кнопки «прослушать голос»
            fragments = diarize.speaker_fragments(self._words, turns)
            # центроиды по подписи «Собеседник N» — для запоминания/узнавания
            voices = {f"Собеседник {int(k) + 1}": v for k, v in embed_raw.items()}
            self.finished_ok.emit(dialogue, fragments, voices)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка разделения: {e}")


class PolishWorker(QThread):
    """Локальная полировка текста через llama-server — в фоне, не морозя окно."""
    progress = Signal(int, int)            # готово кусков, всего
    finished_ok = Signal(str)              # причёсанный текст
    failed = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from . import polish
        try:
            out = polish.polish(
                self._text,
                progress_cb=lambda d, n: self.progress.emit(d, n),
                cancel_check=lambda: self._cancelled)
            if self._cancelled:
                self.failed.emit("Отменено пользователем.")
                return
            self.finished_ok.emit(out)
        except InterruptedError:
            self.failed.emit("Отменено пользователем.")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Не удалось причесать текст: {e}")
