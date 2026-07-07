"""Общие виджеты: карточка, плитка статистики."""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        lay.addWidget(lbl)
    return frame, lay


def stat_tile(title: str, value: str, sub: str = "") -> QFrame:
    frame, lay = card()
    t = QLabel(title.upper())
    t.setObjectName("tileTitle")
    v = QLabel(value)
    v.setObjectName("bigValue")
    lay.addWidget(t)
    lay.addWidget(v)
    if sub:
        s = QLabel(sub)
        s.setObjectName("hint")
        lay.addWidget(s)
    return frame
