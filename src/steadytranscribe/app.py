"""Точка входа SteadyTranscribe."""
# ВАЖНО: до любых тяжёлых импортов (ctranslate2/onnxruntime) — обход конфликта
# OpenMP-библиотек, из-за которого приложение падало при загрузке модели на Windows.
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", str(max(os.cpu_count() or 4, 1)))

import faulthandler  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import traceback  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from .storage.settings import app_data_dir  # noqa: E402


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


def main():
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
        send = box.addButton("Отправить отчёт разработчику", QMessageBox.AcceptRole)
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
