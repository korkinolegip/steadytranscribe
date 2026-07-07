"""Точка входа SteadyTranscribe."""
import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import QSS


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SteadyTranscribe")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
