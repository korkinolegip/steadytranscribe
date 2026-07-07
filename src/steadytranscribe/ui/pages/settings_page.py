"""Страница «Настройки»: строки «заголовок + подпись + контрол справа» (как в FluidVoice)."""
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from ...storage import settings as store
from .. import updater
from ..widgets import card


def _row(lay, title: str, subtitle: str, control):
    row = QHBoxLayout()
    left = QVBoxLayout()
    t = QLabel(title)
    s = QLabel(subtitle)
    s.setObjectName("hint")
    s.setWordWrap(True)
    left.addWidget(t)
    left.addWidget(s)
    row.addLayout(left, stretch=1)
    row.addWidget(control)
    lay.addLayout(row)


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        s = store.load()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(14)

        title = QLabel("Настройки")
        title.setObjectName("h1")
        outer.addWidget(title)

        # --- Распознавание ---
        box, lay = card("Распознавание")
        self.lang_box = QComboBox()
        for code, label in store.LANGUAGE_CHOICES:
            self.lang_box.addItem(label, code)
        codes = [c for c, _ in store.LANGUAGE_CHOICES]
        self.lang_box.setCurrentIndex(codes.index(s["language"]) if s["language"] in codes else 0)
        self.lang_box.currentIndexChanged.connect(self._save)
        _row(lay, "Язык речи", "Автоопределение работает хорошо; явный выбор чуть точнее.", self.lang_box)

        outer.addWidget(box)

        # --- Словарь (многострочный) ---
        box2, lay2 = card("Словарь")
        desc = QLabel("Впишите имена, названия и термины, которые встречаются в записях — "
                      "по одному в строке или через запятую. Программа будет писать их правильно, "
                      "а не на слух.")
        desc.setObjectName("hint")
        desc.setWordWrap(True)
        lay2.addWidget(desc)
        self.prompt_edit = QPlainTextEdit(s["initial_prompt"])
        self.prompt_edit.setPlaceholderText("SteadyControl\nаудиобейдж\nХоРеКа\nимена коллег…")
        self.prompt_edit.setFixedHeight(96)
        lay2.addWidget(self.prompt_edit)
        save_dict = QPushButton("Сохранить словарь")
        save_dict.clicked.connect(self._save)
        drow = QHBoxLayout()
        drow.addStretch()
        drow.addWidget(save_dict)
        lay2.addLayout(drow)
        outer.addWidget(box2)

        # --- История ---
        box3, lay3 = card("История")
        self.history_spin = QSpinBox()
        self.history_spin.setRange(10, 1000)
        self.history_spin.setValue(int(s["history_limit"]))
        self.history_spin.valueChanged.connect(self._save)
        _row(lay3, "Хранить записей", "Старые записи удаляются автоматически при превышении.",
             self.history_spin)
        outer.addWidget(box3)

        # --- Обновления ---
        box4, lay4 = card("Обновления")
        self.update_status = QLabel(f"Текущая версия: {updater.CURRENT_VERSION}")
        self.update_status.setObjectName("hint")
        check_btn = QPushButton("Проверить обновления")
        check_btn.clicked.connect(self._check_updates)
        page_btn = QPushButton("Страница релизов")
        page_btn.setObjectName("link")
        page_btn.clicked.connect(lambda: webbrowser.open(updater.RELEASES_PAGE))
        urow = QHBoxLayout()
        urow.addWidget(self.update_status, stretch=1)
        urow.addWidget(check_btn)
        urow.addWidget(page_btn)
        lay4.addLayout(urow)
        hint4 = QLabel("Программа сама проверяет обновления при запуске. "
                       "Когда выйдет новая версия — предложит скачать и установит сама.")
        hint4.setObjectName("hint")
        hint4.setWordWrap(True)
        lay4.addWidget(hint4)
        outer.addWidget(box4)

        # --- Помощь / отчёт о проблеме ---
        box5, lay5 = card("Помощь")
        report_btn = QPushButton("🐞 Сообщить о проблеме")
        report_btn.clicked.connect(self._report)
        lay5.addWidget(report_btn)
        hint5 = QLabel("Одна кнопка — лог (версия, система, ошибки) уходит разработчику автоматически. Текст диктовок и аудио НЕ отправляются.")
        hint5.setObjectName("hint")
        hint5.setWordWrap(True)
        lay5.addWidget(hint5)
        outer.addWidget(box5)

        note = QLabel("Модель распознавания выбирается на странице «Модели». "
                      "Всё локально: файлы и текст не покидают компьютер.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        outer.addWidget(note)
        outer.addStretch()

        self._checker = None

    def _save(self, *_):
        s = store.load()
        s.update({
            "language": self.lang_box.currentData(),
            "initial_prompt": self.prompt_edit.toPlainText().strip(),
            "history_limit": self.history_spin.value(),
        })
        store.save(s)

    def _report(self):
        from .. import feedback
        feedback.send_report(self, title="Проблема в SteadyTranscribe")

    def _check_updates(self):
        self.update_status.setText("Проверяю…")
        self._checker = updater.UpdateChecker(self)
        self._checker.update_available.connect(self._on_update)
        self._checker.finished.connect(self._on_check_done)
        self._checker.start()

    def _on_update(self, version: str, url: str):
        self.update_status.setText(f"Доступна версия {version}!")
        if updater.QMessageBox.information(
                self, "Обновление",
                f"Вышла версия {version} (у вас {updater.CURRENT_VERSION}). Скачать?",
                updater.QMessageBox.Yes | updater.QMessageBox.No) == updater.QMessageBox.Yes:
            webbrowser.open(url)

    def _on_check_done(self):
        if self.update_status.text() == "Проверяю…":
            self.update_status.setText(f"У вас последняя версия ({updater.CURRENT_VERSION}) ✅")
