"""Раздел «Как пользоваться» — подробный визуальный гид по всем функциям.

Оформлен «под ключ»: hero-заголовок, три шага работы со стрелками, сетка
карточек функций, советы и решение проблем. При открытии секции плавно
проявляются (fade-in) — лёгкий «вау»-эффект без перегруза.
"""
import webbrowser

from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

# (эмодзи, заголовок, описание) — три шага основного сценария
STEPS = [
    ("📥", "Перетащите файл",
     "Бросьте запись (Zoom, диктофон, видео) в окно «Расшифровка». "
     "Форматы любые — MP3, MP4, M4A, MOV и другие."),
    ("🧠", "Программа распознаёт",
     "Всё локально, без интернета. Видно прогресс и сколько осталось. "
     "Можно параллельно работать — нагрузка регулируется сама."),
    ("👥", "Разделите по людям",
     "На готовом тексте — «Разделить по собеседникам». Реплики подпишутся, "
     "а «Имена» заменят «Собеседник 1» на настоящие имена."),
]

# (иконка, заголовок, описание) — карточки функций
FEATURES = [
    ("🎙", "Расшифровка речи",
     "Точное распознавание русской речи с пунктуацией. Модель Large v3 Turbo — "
     "максимальное качество прямо на вашем компьютере."),
    ("👥", "Разделение по собеседникам",
     "Программа узнаёт голоса по тембру и подписывает, кто что сказал. "
     "Укажите число участников — так точнее."),
    ("📖", "Умный словарь",
     "Впишите имена, названия и термины (SteadyControl, аудиобейдж) — и они будут "
     "писаться правильно. Ваши правки в тексте тоже пополняют словарь сами."),
    ("✏️", "Правки и переименование",
     "Текст правится прямо в окне. Расшифровке можно дать понятное имя — "
     "например «Планёрка отдела 8 июля»."),
    ("🕘", "История и поиск",
     "Все расшифровки сохраняются локально, с поиском по тексту. "
     "Ничего не теряется и не уходит в облако."),
    ("⚙️", "Умная нагрузка",
     "Пока вы работаете в других программах — расшифровка уступает им ресурсы, "
     "компьютер не тормозит. Настраивать ничего не нужно."),
    ("🔄", "Авто-обновление",
     "Новые версии скачиваются тихо в фоне и ставятся сами при закрытии — "
     "без мастеров и лишних кликов."),
    ("🔒", "Полная приватность",
     "Аудио и текст никогда не покидают компьютер. Никаких серверов, "
     "подходит для конфиденциальных встреч."),
    ("🎁", "Сюрприз на время ожидания",
     "Запустите расшифровку длинной записи — и пока ИИ работает, вас ждёт "
     "небольшой приятный бонус. Какой — не скажем, попробуйте 😉"),
]

# (иконка, проблема, решение) — предупреждение системы безопасности своё
# на каждой платформе: Windows SmartScreen против macOS Gatekeeper
import sys as _sys

_PUBLISHER_TROUBLE = (
    ("⚠️", "«Не удалось проверить разработчика» при первом открытии",
     "Это нормально для программ без платного сертификата. Один раз откройте "
     "через правый клик по приложению → «Открыть» → «Открыть». Дальше будет "
     "открываться как обычно.")
    if _sys.platform == "darwin" else
    ("⚠️", "«Неизвестный издатель» при установке",
     "Это нормально для программ без платного сертификата. Нажмите «Подробнее» → "
     "«Выполнить в любом случае». Файлы полностью безопасны."))

TROUBLES = [
    ("🐢", "Расшифровка идёт медленно",
     "На странице «Модели» можно выбрать модель полегче — Small примерно втрое быстрее "
     "при небольшой потере качества."),
    _PUBLISHER_TROUBLE,
    ("🐞", "Что-то пошло не так",
     "«Обратная связь» → «Сообщить о проблеме»: одной кнопкой лог уходит разработчику "
     "(без текста ваших записей). Или напишите Олегу в Telegram."),
]


def _step_card(num: int, emoji: str, title: str, desc: str) -> QFrame:
    card = QFrame()
    card.setObjectName("stepCard")
    card.setMinimumWidth(10)     # разрешаем сжатие на узких окнах (тексты переносятся)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(8)
    top = QHBoxLayout()
    badge = QLabel(str(num))
    badge.setObjectName("stepBadge")
    em = QLabel(emoji)
    em.setObjectName("stepEmoji")
    top.addWidget(badge)
    top.addStretch()
    top.addWidget(em)
    lay.addLayout(top)
    t = QLabel(title)
    t.setObjectName("stepTitle")
    t.setWordWrap(True)
    d = QLabel(desc)
    d.setObjectName("hint")
    d.setWordWrap(True)
    lay.addWidget(t)
    lay.addWidget(d)
    lay.addStretch()
    return card


def _feature_card(icon: str, title: str, desc: str) -> QFrame:
    card = QFrame()
    card.setObjectName("feature")
    lay = QHBoxLayout(card)
    lay.setContentsMargins(14, 14, 14, 14)
    lay.setSpacing(12)
    ic = QLabel(icon)
    ic.setObjectName("featIcon")
    ic.setAlignment(Qt.AlignTop)
    ic.setFixedWidth(34)
    lay.addWidget(ic)
    col = QVBoxLayout()
    col.setSpacing(3)
    t = QLabel(title)
    t.setObjectName("featTitle")
    d = QLabel(desc)
    d.setObjectName("hint")
    d.setWordWrap(True)
    col.addWidget(t)
    col.addWidget(d)
    lay.addLayout(col, stretch=1)
    return card


def _trouble_row(icon: str, problem: str, solution: str) -> QFrame:
    return _feature_card(icon, problem, solution)


class HelpPage(QWidget):
    scrolled_to_bottom = Signal()   # человек дочитал гид до конца (один раз)

    def __init__(self):
        super().__init__()
        self._animated = False
        self._bottom_emitted = False
        self._sections: list[QWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # без горизонтальной прокрутки: на узком окне карточки сжимаются,
        # а не уезжают за край (найдено фотосессией UI на 800×500)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(24, 20, 24, 28)
        col.setSpacing(22)
        scroll.setWidget(content)
        root.addWidget(scroll)
        scroll.verticalScrollBar().valueChanged.connect(self._check_bottom)

        # --- Hero ---
        hero = QFrame()
        hero.setObjectName("hero")
        hlay = QVBoxLayout(hero)
        hlay.setSpacing(8)
        htitle = QLabel("SteadyVoice")
        htitle.setObjectName("heroTitle")
        hsub = QLabel("Превращает записи встреч в текст — точно, локально и приватно. "
                      "Ниже — как пользоваться и что программа умеет.")
        hsub.setObjectName("heroSub")
        hsub.setWordWrap(True)
        from ..widgets import FlowLayout
        chips_host = QWidget()
        chips = FlowLayout(chips_host, hspacing=8, vspacing=8)
        for c in ("🔒 Всё локально", "🇷🇺 Русская речь", "👥 По собеседникам", "⚡ Быстро"):
            chip = QLabel(c)
            chip.setObjectName("chip")
            chips.addWidget(chip)
        hlay.addWidget(htitle)
        hlay.addWidget(hsub)
        hlay.addWidget(chips_host)
        self._add_section(col, hero)

        # --- 3 шага ---
        col.addWidget(self._section_title("Как это работает — 3 шага"))
        steps_row = QFrame()
        srow = QHBoxLayout(steps_row)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(10)
        for i, (emoji, title, desc) in enumerate(STEPS, start=1):
            srow.addWidget(_step_card(i, emoji, title, desc), stretch=1)
            if i < len(STEPS):
                arrow = QLabel("→")
                arrow.setObjectName("arrow")
                arrow.setAlignment(Qt.AlignCenter)
                srow.addWidget(arrow)
        self._add_section(col, steps_row)

        # --- Функции ---
        col.addWidget(self._section_title("Что умеет программа"))
        grid_host = QFrame()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self._gift_icon = None
        for idx, (icon, title, desc) in enumerate(FEATURES):
            card = _feature_card(icon, title, desc)
            if idx == len(FEATURES) - 1 and len(FEATURES) % 2 == 1:
                # нечётная последняя (сюрприз) — на всю ширину, столбцы ровные
                grid.addWidget(card, idx // 2, 0, 1, 2)
            else:
                grid.addWidget(card, idx // 2, idx % 2)
            if icon == "🎁":
                self._gift_icon = card.findChild(QLabel, "featIcon")
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self._add_section(col, grid_host)
        # подарочек слегка покачивается — видно, что это что-то особенное
        self._gift_phase = 0.0
        self._gift_timer = QTimer(self)
        self._gift_timer.setInterval(50)
        self._gift_timer.timeout.connect(self._bob_gift)

        # --- Если что-то не так ---
        col.addWidget(self._section_title("Если что-то не так"))
        tr_host = QFrame()
        trlay = QVBoxLayout(tr_host)
        trlay.setContentsMargins(0, 0, 0, 0)
        trlay.setSpacing(10)
        for icon, problem, solution in TROUBLES:
            trlay.addWidget(_trouble_row(icon, problem, solution))
        self._add_section(col, tr_host)

        # --- Связь ---
        contact = QFrame()
        clay = QHBoxLayout(contact)
        clay.setContentsMargins(0, 0, 0, 0)
        tg = QPushButton("✈ Написать разработчику в Telegram")
        tg.setObjectName("primary")
        tg.clicked.connect(lambda: webbrowser.open("https://t.me/oleg_broke"))
        clay.addWidget(tg)
        clay.addStretch()
        self._add_section(col, contact)

        col.addStretch()

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _add_section(self, layout, widget: QWidget):
        layout.addWidget(widget)
        self._sections.append(widget)

    def _check_bottom(self, value):
        sb = self.sender()
        if (not self._bottom_emitted and sb.maximum() > 0
                and value >= sb.maximum() - 8):
            self._bottom_emitted = True
            self.scrolled_to_bottom.emit()

    def _bob_gift(self):
        import math
        if self._gift_icon is None:
            return
        self._gift_phase += 0.18
        off = int(round(3 * math.sin(self._gift_phase)))
        self._gift_icon.setContentsMargins(0, 3 + off, 0, 3 - off)

    def hideEvent(self, event):
        self._gift_timer.stop()
        super().hideEvent(event)

    # ---- плавное проявление секций при первом показе ----

    def showEvent(self, event):
        super().showEvent(event)
        self._gift_timer.start()
        if self._animated:
            return
        self._animated = True
        self._anims = []
        for i, w in enumerate(self._sections):
            eff = QGraphicsOpacityEffect(w)
            eff.setOpacity(0.0)
            w.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(560)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anims.append(anim)
            QTimer.singleShot(130 * i, anim.start)
