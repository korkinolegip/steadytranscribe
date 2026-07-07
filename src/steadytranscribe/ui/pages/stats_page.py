"""Страница «Статистика»: плитки в стиле StatsView FluidVoice."""
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from ...storage import history
from ..widgets import stat_tile


class StatsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 20, 24, 24)
        self.lay.setSpacing(14)
        self.refresh()

    def refresh(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    s = sub.takeAt(0)
                    if s.widget():
                        s.widget().deleteLater()

        title = QLabel("Статистика")
        title.setObjectName("h1")
        self.lay.addWidget(title)

        entries = history.list_entries()
        total = len(entries)
        minutes = sum(e.duration for e in entries) / 60
        words = sum(len(e.text.split()) for e in entries)
        saved_min = max(minutes - sum(e.processing_time for e in entries) / 60, 0)
        avg_conf = (sum(e.confidence for e in entries) / total * 100) if total else 0

        grid = QGridLayout()
        grid.setSpacing(14)
        grid.addWidget(stat_tile("Расшифровок", str(total)), 0, 0)
        grid.addWidget(stat_tile("Минут аудио", f"{minutes:.0f}"), 0, 1)
        grid.addWidget(stat_tile("Всего слов", f"{words:,}".replace(",", " ")), 1, 0)
        grid.addWidget(stat_tile("Сэкономлено времени",
                                 f"{saved_min:.0f} мин",
                                 "против ручного набора и прослушивания"), 1, 1)
        grid.addWidget(stat_tile("Средняя уверенность", f"{avg_conf:.0f}%"), 2, 0)
        if entries:
            longest = max(entries, key=lambda e: e.duration)
            grid.addWidget(stat_tile("Самая длинная запись",
                                     f"{longest.duration / 60:.0f} мин",
                                     longest.file_name), 2, 1)
        self.lay.addLayout(grid)
        self.lay.addStretch()
