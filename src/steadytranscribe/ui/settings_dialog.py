"""Диалог настроек: модель, язык, устройство, словарь-подсказка, история."""
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QSpinBox, QVBoxLayout,
)

from ..storage import settings as store
from ..core.transcriber import is_model_downloaded


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(520)
        s = store.load()

        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.model_box = QComboBox()
        for m in store.MODEL_CHOICES:
            downloaded = " ✓ скачана" if is_model_downloaded(m) else ""
            self.model_box.addItem(store.MODEL_LABELS[m] + downloaded, m)
        self.model_box.setCurrentIndex(store.MODEL_CHOICES.index(s["model"]))
        form.addRow("Модель распознавания:", self.model_box)

        self.lang_box = QComboBox()
        for code, label in store.LANGUAGE_CHOICES:
            self.lang_box.addItem(label, code)
        codes = [c for c, _ in store.LANGUAGE_CHOICES]
        self.lang_box.setCurrentIndex(codes.index(s["language"]) if s["language"] in codes else 0)
        form.addRow("Язык речи:", self.lang_box)

        self.device_box = QComboBox()
        for code, label in (("auto", "Автоматически"), ("cpu", "Процессор (CPU)"),
                            ("cuda", "Видеокарта NVIDIA (CUDA)")):
            self.device_box.addItem(label, code)
        self.device_box.setCurrentIndex({"auto": 0, "cpu": 1, "cuda": 2}.get(s["device"], 0))
        form.addRow("Устройство:", self.device_box)

        self.prompt_edit = QLineEdit(s["initial_prompt"])
        self.prompt_edit.setPlaceholderText("Например: SteadyControl, аудиобейдж, ХоРеКа")
        form.addRow("Словарь-подсказка:", self.prompt_edit)
        hint = QLabel("Имена и термины через запятую — повышают точность их распознавания.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow("", hint)

        self.history_spin = QSpinBox()
        self.history_spin.setRange(10, 1000)
        self.history_spin.setValue(int(s["history_limit"]))
        form.addRow("Хранить записей истории:", self.history_spin)

        lay.addLayout(form)
        note = QLabel("Модель скачивается один раз при первом использовании. "
                      "Всё распознавание — локально, файлы не покидают компьютер.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        lay.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self):
        store.save({
            "model": self.model_box.currentData(),
            "language": self.lang_box.currentData(),
            "device": self.device_box.currentData(),
            "initial_prompt": self.prompt_edit.text().strip(),
            "history_limit": self.history_spin.value(),
            "hf_mirror": "auto",
        })
        self.accept()
