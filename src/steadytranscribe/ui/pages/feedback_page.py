"""Страница «Обратная связь»: сообщить о проблеме, написать разработчику,
предложить идею/сообщить о неудобстве (уходит во внутреннюю аналитику).
Блоки перенесены из «Настроек» — по решению Олега помощь живёт отдельно.
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ...storage import analytics
from ..widgets import card


class FeedbackPage(QWidget):
    def __init__(self):
        super().__init__()
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

        title = QLabel("Обратная связь")
        title.setObjectName("h1")
        outer.addWidget(title)
        sub = QLabel("Нашли проблему, чего-то не хватает или есть идея? "
                     "Нам правда важно — программа развивается по вашим отзывам.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        # --- Проблема ---
        box, lay = card("Что-то не работает")
        report_btn = QPushButton("🐞 Сообщить о проблеме")
        report_btn.setObjectName("primary")
        report_btn.clicked.connect(self._report)
        lay.addWidget(report_btn)
        hint = QLabel("Одна кнопка — технический отчёт (версия, система, ошибки) "
                      "уходит разработчику автоматически. Текст ваших записей и "
                      "аудио НЕ отправляются.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        outer.addWidget(box)

        # --- Идея / пожелание ---
        box2, lay2 = card("Идея или пожелание")
        self.idea_edit = QPlainTextEdit()
        self.idea_edit.setPlaceholderText(
            "Например: «хочу экспорт сразу в Word» или «неудобно, что …»")
        self.idea_edit.setFixedHeight(110)
        lay2.addWidget(self.idea_edit)
        send_btn = QPushButton("✉ Отправить")
        send_btn.clicked.connect(self._send_idea)
        self.idea_status = QLabel()
        self.idea_status.setObjectName("hint")
        row = QHBoxLayout()
        row.addWidget(self.idea_status, stretch=1)
        row.addWidget(send_btn)
        lay2.addLayout(row)
        outer.addWidget(box2)

        # --- Прямой контакт ---
        box3, lay3 = card("Напрямую")
        tg_btn = QPushButton("✈ Написать разработчику в Telegram")
        tg_btn.clicked.connect(self._telegram)
        lay3.addWidget(tg_btn)
        hint3 = QLabel("По любым вопросам — Олегу напрямую, отвечает быстро.")
        hint3.setObjectName("hint")
        hint3.setWordWrap(True)
        lay3.addWidget(hint3)
        outer.addWidget(box3)
        outer.addStretch()

    def _report(self):
        from .. import feedback
        analytics.track("bug_report")
        analytics.flush_async()
        feedback.send_report(self, title="Проблема в SteadyVoice")

    def _telegram(self):
        import webbrowser
        analytics.track("telegram_click")
        webbrowser.open("https://t.me/oleg_broke")

    def _send_idea(self):
        text = self.idea_edit.toPlainText().strip()
        if not text:
            self.idea_status.setText("Напишите пару слов — и отправим.")
            return
        analytics.track("feedback", text=text[:1000])
        analytics.flush_async()
        self.idea_edit.clear()
        self.idea_status.setText("✅ Спасибо! Ваше сообщение отправлено.")
        QTimer.singleShot(4000, lambda: self.idea_status.setText(""))
