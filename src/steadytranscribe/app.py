"""Точка входа SteadyTranscribe."""
import faulthandler
import logging
import os
import sys
import traceback

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
    print("SELFTEST: start", flush=True)
    from .core import convert
    from .core.transcriber import Transcriber
    print("SELFTEST: imports ok", flush=True)
    wav = convert.to_wav16k(audio_path)
    print("SELFTEST: ffmpeg convert ok", flush=True)
    t = Transcriber()
    r = t.transcribe(wav, model="tiny", language="ru", device="auto",
                     initial_prompt="",
                     status_cb=lambda s, p: print(f"SELFTEST: progress {p*100:.0f}%", flush=True),
                     cancel_check=lambda: False, word_timestamps=True)
    print(f"SELFTEST: DONE chars={len(r.text)} words={len(r.words or [])}", flush=True)
    return 0


def main():
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        sys.exit(_selftest(sys.argv[idx + 1]))

    from PySide6.QtWidgets import QApplication, QMessageBox
    log_path = _setup_logging()
    logging.info("=== SteadyTranscribe запуск ===")

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
