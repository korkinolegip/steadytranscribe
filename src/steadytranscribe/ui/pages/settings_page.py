"""Страница «Настройки»: строки «заголовок + подпись + контрол справа» (как в FluidVoice)."""
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from ...storage import settings as store
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

        box, lay = card("Распознавание")
        self.lang_box = QComboBox()
        for code, label in store.LANGUAGE_CHOICES:
            self.lang_box.addItem(label, code)
        codes = [c for c, _ in store.LANGUAGE_CHOICES]
        self.lang_box.setCurrentIndex(codes.index(s["language"]) if s["language"] in codes else 0)
        self.lang_box.currentIndexChanged.connect(self._save)
        _row(lay, "Язык речи", "Автоопределение работает хорошо; явный выбор чуть точнее и быстрее.", self.lang_box)

        self.device_box = QComboBox()
        for code, label in (("auto", "Автоматически"), ("cpu", "Процессор (CPU)"),
                            ("cuda", "Видеокарта NVIDIA")):
            self.device_box.addItem(label, code)
        self.device_box.setCurrentIndex({"auto": 0, "cpu": 1, "cuda": 2}.get(s["device"], 0))
        self.device_box.currentIndexChanged.connect(self._save)
        _row(lay, "Устройство", "Видеокарта NVIDIA ускоряет распознавание в разы (если есть).", self.device_box)
        outer.addWidget(box)

        box2, lay2 = card("Словарь")
        self.prompt_edit = QLineEdit(s["initial_prompt"])
        self.prompt_edit.setPlaceholderText("SteadyControl, аудиобейдж, ХоРеКа")
        self.prompt_edit.setMinimumWidth(280)
        self.prompt_edit.editingFinished.connect(self._save)
        _row(lay2, "Слова-подсказки", "Имена и термины через запятую — модель будет писать их правильно.", self.prompt_edit)
        outer.addWidget(box2)

        box3, lay3 = card("История")
        self.history_spin = QSpinBox()
        self.history_spin.setRange(10, 1000)
        self.history_spin.setValue(int(s["history_limit"]))
        self.history_spin.valueChanged.connect(self._save)
        _row(lay3, "Хранить записей", "Старые записи удаляются автоматически при превышении.", self.history_spin)
        outer.addWidget(box3)

        note = QLabel("Модель распознавания выбирается на странице «Модели». "
                      "Всё локально: файлы и текст не покидают компьютер.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        outer.addWidget(note)
        outer.addStretch()

    def _save(self, *_):
        s = store.load()
        s.update({
            "language": self.lang_box.currentData(),
            "device": self.device_box.currentData(),
            "initial_prompt": self.prompt_edit.text().strip(),
            "history_limit": self.history_spin.value(),
        })
        store.save(s)
