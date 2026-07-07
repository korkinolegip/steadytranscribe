"""Точка входа SteadyTranscribe."""
import faulthandler
import logging
import os
import platform
import sys
import traceback

os.environ.setdefault("CT2_USE_MKL", "0")


def _detect_cpu() -> str:
    """Определяет ускорение процессора через системный вызов Windows
    (без подпроцессов!). Мощный CPU (AVX2) → быстрый режим; иначе → совместимый.
    ВАЖНО: не использовать py-cpuinfo — в собранном exe он рекурсивно
    запускает копии приложения (плодятся окна)."""
    try:
        import ctypes
        if sys.platform == "win32":
            # PF_AVX2_INSTRUCTIONS_AVAILABLE = 40 (Windows API IsProcessorFeaturePresent)
            if ctypes.windll.kernel32.IsProcessorFeaturePresent(40):
                return "avx2"          # быстрый режим — ISA не форсируем
            # PF_AVX_INSTRUCTIONS_AVAILABLE = 39
            if ctypes.windll.kernel32.IsProcessorFeaturePresent(39):
                os.environ["CT2_FORCE_CPU_ISA"] = "AVX"
                return "avx"
    except Exception:  # noqa: BLE001
        pass
    os.environ["CT2_FORCE_CPU_ISA"] = "GENERIC"
    return "generic"


CPU_MODE = _detect_cpu()

from .storage.settings import app_data_dir


def _setup_logging() -> str:
    log_path = os.path.join(app_data_dir(), "log.txt")
    logging.basicConfig(
        filename=log_path, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        faulthandler.enable(open(os.path.join(app_data_dir(), "crash.txt"), "w"))
    except Exception:  # noqa: BLE001
        pass
    return log_path


def _selftest(audio_path: str) -> int:
    """Прогон транскрипции без GUI — для проверки собранного exe в CI.
    Только ASCII в выводе (консоль Windows = cp1252)."""
    faulthandler.enable()
    print(f"SELFTEST: start CPU_MODE={CPU_MODE} ISA={os.environ.get('CT2_FORCE_CPU_ISA','fast')}",
          flush=True)
    from .core import convert
    from .core.transcriber import Transcriber
    print("SELFTEST: imports ok", flush=True)
    wav = convert.to_wav16k(audio_path)
    print("SELFTEST: ffmpeg convert ok", flush=True)
    t = Transcriber()
    # device="cuda" — воспроизводим случай пользователя (раньше падало на CUDA)
    r = t.transcribe(wav, model="tiny", language="ru", device="cuda",
                     initial_prompt="",
                     status_cb=lambda s, p: print(f"SELFTEST: progress {p*100:.0f}%", flush=True),
                     cancel_check=lambda: False, word_timestamps=True)
    print(f"SELFTEST: transcribe DONE chars={len(r.text)} words={len(r.words or [])}", flush=True)
    # проверяем и диаризацию (у неё свои onnx-модели)
    from .core import diarize
    if diarize.is_available():
        turns = diarize.diarize(wav, 2, status_cb=lambda s, p: None, cancel_check=lambda: False)
        print(f"SELFTEST: diarize DONE turns={len(turns)}", flush=True)
    else:
        print("SELFTEST: diarize models missing", flush=True)
    print("SELFTEST: ALL OK", flush=True)
    return 0


def main():
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        sys.exit(_selftest(sys.argv[idx + 1]))

    from PySide6.QtWidgets import QApplication, QMessageBox
    log_path = _setup_logging()
    logging.info("=== SteadyTranscribe запуск ===")
    try:
        logging.info("CPU=%s cores=%s режим=%s ISA=%s OS=%s",
                     platform.processor(), os.cpu_count(), CPU_MODE,
                     os.environ.get("CT2_FORCE_CPU_ISA", "быстрый"), platform.platform())
        # на слабом CPU (без AVX2) по умолчанию — лёгкая модель, если пользователь ещё не выбирал
        from .storage import settings as _s
        conf = _s.load()
        if CPU_MODE == "generic" and not conf.get("onboarded"):
            conf["model"] = "small"
            _s.save(conf)
            logging.info("Слабый CPU: модель по умолчанию понижена до small")
    except Exception:  # noqa: BLE001
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("SteadyTranscribe")
    app.setStyle("Fusion")

    from .ui.theme import QSS
    app.setStyleSheet(QSS)

    def excepthook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.error("Необработанная ошибка:\n%s", text)
        from .ui import feedback
        box = QMessageBox(QMessageBox.Critical, "Ошибка SteadyTranscribe",
                          f"Произошла ошибка. Приложение продолжит работу.\n\n{exc_value}")
        send = box.addButton("Сохранить отчёт", QMessageBox.AcceptRole)
        box.addButton("Закрыть", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is send:
            feedback.send_report(extra=f"Автоматический отчёт об ошибке:\n{exc_value}")
    sys.excepthook = excepthook

    from .ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
