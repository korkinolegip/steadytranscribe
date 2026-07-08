"""Страница «Настройки»: строки «заголовок + подпись + контрол справа» (как в FluidVoice)."""
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
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
        # прокрутка — чтобы кнопки внизу не обрезались на невысоком окне
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(14)
        scroll.setWidget(content)
        root.addWidget(scroll)

        title = QLabel("Настройки")
        title.setObjectName("h1")
        outer.addWidget(title)

        # --- Пользователь ---
        from PySide6.QtWidgets import QLineEdit
        from ..onboarding import DEPARTMENTS
        boxu, layu = card("Пользователь")
        self.user_edit = QLineEdit(s.get("user_name", ""))
        self.user_edit.setPlaceholderText("Имя и фамилия")
        self.user_edit.editingFinished.connect(self._save)
        _row(layu, "Имя и фамилия", "Закрепляется за этим компьютером.", self.user_edit)
        self.dept_box = QComboBox()
        self.dept_box.addItems(DEPARTMENTS[:-1])
        cur_dept = s.get("user_dept", "")
        if cur_dept and cur_dept not in DEPARTMENTS:
            self.dept_box.addItem(cur_dept)
        if cur_dept:
            self.dept_box.setCurrentText(cur_dept)
        self.dept_box.currentIndexChanged.connect(self._save)
        _row(layu, "Отдел", "Подразделение SteadyControl.", self.dept_box)
        outer.addWidget(boxu)

        # --- Распознавание ---
        box, lay = card("Распознавание")
        self.lang_box = QComboBox()
        for code, label in store.LANGUAGE_CHOICES:
            self.lang_box.addItem(label, code)
        codes = [c for c, _ in store.LANGUAGE_CHOICES]
        self.lang_box.setCurrentIndex(codes.index(s["language"]) if s["language"] in codes else 0)
        self.lang_box.currentIndexChanged.connect(self._save)
        _row(lay, "Язык речи", "Автоопределение работает хорошо; явный выбор чуть точнее.", self.lang_box)

        auto = QLabel("⚙ Нагрузка регулируется автоматически: пока вы работаете в других "
                      "программах, расшифровка уступает им ресурсы; когда окно активно — "
                      "ускоряется. Компьютер не тормозит, ничего настраивать не нужно.")
        auto.setObjectName("hint")
        auto.setWordWrap(True)
        lay.addWidget(auto)

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
        self.prompt_edit.setPlaceholderText(
            "Например:\nSteadyControl\nаудиобейдж\nИван Петров\nконверсия")
        self.prompt_edit.setFixedHeight(110)
        lay2.addWidget(self.prompt_edit)
        example = QLabel("Программа запомнит эти слова и будет писать их правильно, "
                         "а не «на слух». Помогает с именами, названиями компаний и терминами.")
        example.setObjectName("hint")
        example.setWordWrap(True)
        lay2.addWidget(example)
        save_dict = QPushButton("💾 Сохранить словарь")
        save_dict.setObjectName("primary")
        save_dict.clicked.connect(self._save_dict)
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
        # видимый статус: что уже скачано и ждёт установки
        pend = updater.load_pending()
        if pend:
            status_txt = (f"Текущая версия: {updater.CURRENT_VERSION}. "
                          f"✓ Обновление {pend['version']} скачано — установится само.")
        else:
            status_txt = f"Текущая версия: {updater.CURRENT_VERSION}"
        self.update_status = QLabel(status_txt)
        self.update_status.setObjectName("hint")
        # «Что нового» — по-человечески, только польза (см. changelog.py)
        from ..changelog import whats_new
        note = whats_new(updater.CURRENT_VERSION)
        if note:
            news = QLabel(f"✨ В этой версии: {note}")
            news.setObjectName("hint")
            news.setWordWrap(True)
            lay4.addWidget(news)
        check_btn = QPushButton("Проверить обновления")
        check_btn.clicked.connect(self._check_updates)
        # ссылки на страницу релизов НЕТ намеренно: пользователям не нужно видеть
        # техническую историю версий на GitHub (решение Олега)
        urow = QHBoxLayout()
        urow.addWidget(self.update_status, stretch=1)
        urow.addWidget(check_btn)
        lay4.addLayout(urow)
        self.auto_update_chk = QCheckBox("Обновлять автоматически")
        self.auto_update_chk.setChecked(bool(s.get("auto_update", True)))
        self.auto_update_chk.toggled.connect(self._save)
        lay4.addWidget(self.auto_update_chk)
        hint4 = QLabel("Как в современных программах: новая версия тихо скачивается в фоне "
                       "и устанавливается сама — когда программа простаивает, при закрытии "
                       "или при следующем запуске. Расшифровку никогда не прерывает, "
                       "кликать ничего не нужно.")
        hint4.setObjectName("hint")
        hint4.setWordWrap(True)
        lay4.addWidget(hint4)
        outer.addWidget(box4)

        # --- Служебное (помощь/репорты переехали на страницу «Обратная связь») ---
        box5, lay5 = card("Служебное")
        reset_btn = QPushButton("↺ Сбросить настройки")
        reset_btn.setObjectName("danger")
        reset_btn.clicked.connect(self._reset_settings)
        lay5.addWidget(reset_btn)
        hint6 = QLabel("Вернуть настройки к исходным (если программа ведёт себя странно). "
                       "Модели и история сохранятся.")
        hint6.setObjectName("hint")
        hint6.setWordWrap(True)
        lay5.addWidget(hint6)
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
            "auto_update": self.auto_update_chk.isChecked(),
            "user_name": self.user_edit.text().strip(),
            "user_dept": self.dept_box.currentText(),
        })
        store.save(s)
        from ...storage import analytics
        analytics.track("settings_changed", lang=s["language"],
                        auto_update=s["auto_update"],
                        dict_words=len([w for w in s["initial_prompt"].replace("\n", ",").split(",") if w.strip()]))

    def _save_dict(self):
        from PySide6.QtWidgets import QMessageBox
        self._save()
        QMessageBox.information(self, "Словарь сохранён",
                               "Слова сохранены. Они применятся к следующим расшифровкам.")

    def _reset_settings(self):
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self, "Сброс настроек",
                                "Вернуть все настройки к исходным? Модели и история сохранятся.") == QMessageBox.Yes:
            store.reset()
            QMessageBox.information(self, "Готово",
                                    "Настройки сброшены. Перезапустите программу.")

    def _report(self):
        from .. import feedback
        feedback.send_report(self, title="Проблема в SteadyVoice")

    def _check_updates(self):
        self.update_status.setText("Проверяю…")
        self._checker = updater.UpdateChecker(self)
        self._checker.update_available.connect(self._on_update)
        self._checker.finished.connect(self._on_check_done)
        self._checker.start()

    def _on_update(self, version: str, url: str, sha: str = ""):
        # обновление ВНУТРИ программы (никаких скачиваний через браузер):
        # тот же диалог, что и при запуске — скачает и тихо установит сам
        self.update_status.setText(f"Доступна версия {version}!")
        updater.UpdateDialog(version, url, sha, self).exec()

    def _on_check_done(self):
        if self.update_status.text() == "Проверяю…":
            self.update_status.setText(f"У вас последняя версия ({updater.CURRENT_VERSION}) ✅")
