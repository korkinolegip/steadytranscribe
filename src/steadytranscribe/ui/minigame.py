"""Мини-игра на время ожидания расшифровки — механика динозаврика Chrome.

Фирменный юмор SteadyControl: робот-ИИ 🤖 бежит по смене и перепрыгивает
классические помехи контроля — перекуры ☕, сон на рабочем месте 😴 и бумажные
отчёты 📄. Пробел или клик — прыжок. Когда расшифровка готова — финал
«GAME OVER — пора работать!» и игра сама убирается. Рекорд сохраняется.
"""
import json
import os
import random

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..storage.settings import app_data_dir

ACCENT = QColor("#3AC8C6")
GROUND = QColor("#2A2A2A")
TEXT_DIM = QColor("#9A9A9A")

_H = 150           # высота поля
_GROUND_Y = _H - 26
_PLAYER_X = 46
_GRAVITY = 0.55
_JUMP_V = -10.5


def _score_path() -> str:
    return os.path.join(app_data_dir(), "game.json")


def _load_scores() -> tuple[int, int]:
    """(рекорд, счёт прошлой игры)."""
    try:
        with open(_score_path(), encoding="utf-8") as f:
            d = json.load(f)
        return int(d.get("high", 0)), int(d.get("last", 0))
    except (OSError, ValueError):
        return 0, 0


def _save_scores(high: int, last: int) -> None:
    try:
        with open(_score_path(), "w", encoding="utf-8") as f:
            json.dump({"high": high, "last": last}, f)
    except OSError:
        pass


class MiniGame(QWidget):
    """Состояния: invite (компактный призыв «сыграть?») → ready (ждём первый
    прыжок) → run → dead (повторные попытки). finish() — расшифровка готова:
    анимация «GAME OVER — пора работать!» ~2 с, затем сам скрывается."""

    _H_INVITE = 46                           # компактный призыв, игра не навязывается

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_H)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setCursor(Qt.PointingHandCursor)
        self._timer = QTimer(self)
        self._timer.setInterval(16)          # ~60 кадров/с
        self._timer.timeout.connect(self._tick)
        self._high, self._last = _load_scores()
        self._reset()
        self._finish_phase = -1.0            # >=0 → идёт финальная анимация
        self._finish_text = ""

    # ---------- управление из страницы ----------

    def begin(self):
        """Показать ПРИЗЫВ сыграть (сама игра не запускается — только по клику)."""
        self._reset()
        self._finish_phase = -1.0
        self._state = "invite"
        self.setFixedHeight(self._H_INVITE)
        self.show()
        self.update()

    def _expand(self):
        """Пользователь согласился сыграть — разворачиваем поле."""
        self.setFixedHeight(_H)
        self._state = "ready"
        self.setFocus()
        self._timer.start()
        self.update()

    def finish(self, text: str = "Пора работать!"):
        """Расшифровка готова: если играли — «Game over, пора работать» с анимацией
        ~2 секунды, иначе просто убрать поле."""
        if not self.isVisible():
            return
        if self._state in ("invite", "ready"):   # не играли — уходим тихо
            self.hide_now()
            return
        self._save_record()
        self._finish_text = text
        self._finish_phase = 0.0
        self._state = "finish"
        self._timer.start()
        QTimer.singleShot(2000, self.hide_now)

    def hide_now(self):
        self._timer.stop()
        self.hide()

    # ---------- игровая логика ----------

    def _reset(self):
        self._state = "ready"                # ready | run | dead | finish
        self._y = 0.0                        # смещение игрока над землёй (вверх)
        self._vy = 0.0
        self._obstacles: list[dict] = []     # {x, w, h, emoji}
        self._speed = 4.0
        self._score = 0
        self._frames = 0
        self._spawn_in = 60

    def _jump(self):
        if self._state == "ready":
            self._state = "run"
            return
        if self._state == "run" and self._y == 0:
            self._vy = _JUMP_V
        elif self._state == "dead":
            self._reset()
            self._state = "run"

    def _save_record(self):
        self._last = self._score
        self._high = max(self._high, self._score)
        _save_scores(self._high, self._last)

    def _tick(self):
        if self._state == "finish":
            self._finish_phase = min(self._finish_phase + 0.035, 1.0)
            self.update()
            return
        if self._state == "run":
            win = self.window()
            if win and not win.isActiveWindow():
                self.update()                # авто-пауза, когда окно неактивно
                return
            self._frames += 1
            if self._frames % 6 == 0:
                self._score += 1
            self._speed = 4.0 + min(self._score / 60.0, 5.0)
            # физика прыжка
            if self._y < 0 or self._vy < 0:
                self._vy += _GRAVITY
                self._y = min(self._y + self._vy, 0.0)
                if self._y == 0:
                    self._vy = 0.0
            # препятствия
            self._spawn_in -= 1
            if self._spawn_in <= 0:
                h = random.choice((22, 30, 38))
                # помехи контроля: перекур, сон на смене, бумажные отчёты, телефон
                self._obstacles.append(
                    {"x": float(self.width() + 20), "w": 20, "h": h,
                     "emoji": random.choice("☕😴📄📱")})
                self._spawn_in = random.randint(55, 110) - int(self._speed * 3)
            for ob in self._obstacles:
                ob["x"] -= self._speed
            self._obstacles = [o for o in self._obstacles if o["x"] > -40]
            # столкновение (с щадящими отступами)
            pr = QRectF(_PLAYER_X + 5, _GROUND_Y - 26 + self._y + 4, 16, 22)
            for ob in self._obstacles:
                orect = QRectF(ob["x"] + 3, _GROUND_Y - ob["h"] + 3,
                               ob["w"] - 6, ob["h"] - 3)
                if pr.intersects(orect):
                    self._state = "dead"
                    self._save_record()
                    break
        self.update()

    # ---------- ввод ----------

    def mousePressEvent(self, event):
        self.setFocus()
        if self._state == "invite":
            self._expand()
        else:
            self._jump()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Up):
            if self._state == "invite":
                self._expand()
            else:
                self._jump()
        else:
            super().keyPressEvent(event)

    # ---------- отрисовка ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()

        if self._state == "invite":
            # компактный призыв — игра не навязывается
            f = QFont()
            f.setPointSize(11)
            p.setFont(f)
            p.setPen(ACCENT)
            rec = f"  ·  ваш рекорд: {self._high}" if self._high else ""
            p.drawText(self.rect(), Qt.AlignCenter,
                       f"🎮 Ожидание веселее с игрой — нажмите, чтобы сыграть{rec}")
            return

        # земля
        p.setPen(QPen(GROUND, 2))
        p.drawLine(8, _GROUND_Y, w - 8, _GROUND_Y)

        if self._state == "finish":
            self._paint_finish(p, w)
            return

        # игрок (робот)
        f = QFont()
        f.setPointSize(20)
        p.setFont(f)
        emoji = "🤖" if self._state != "dead" else "💥"
        p.drawText(QRectF(_PLAYER_X - 6, _GROUND_Y - 30 + self._y, 36, 32),
                   Qt.AlignCenter, emoji)

        # препятствия
        for ob in self._obstacles:
            fo = QFont()
            fo.setPointSize(max(int(ob["h"] * 0.55), 11))
            p.setFont(fo)
            p.drawText(QRectF(ob["x"], _GROUND_Y - ob["h"], ob["w"] + 8, ob["h"] + 2),
                       Qt.AlignBottom | Qt.AlignHCenter, ob["emoji"])

        # счёт
        p.setPen(TEXT_DIM)
        sf = QFont()
        sf.setPointSize(10)
        p.setFont(sf)
        p.drawText(QRectF(0, 6, w - 14, 16), Qt.AlignRight,
                   f"очки {self._score}   рекорд {self._high}")

        # подсказки
        hint = None
        if self._state == "ready":
            last = f"  ·  прошлый раз: {self._last}" if self._last else ""
            hint = ("🎮 Проведите робота через смену!  "
                    f"Пробел или клик — прыжок{last}")
        elif self._state == "dead":
            hint = f"💥 Контроль потерян! {self._score} очков.  Пробел — вернуть контроль"
        elif self._state == "run":
            win = self.window()
            if win and not win.isActiveWindow():
                hint = "⏸ Пауза (окно неактивно)"
        if hint:
            p.setPen(TEXT_DIM if self._state != "dead" else ACCENT)
            hf = QFont()
            hf.setPointSize(11)
            p.setFont(hf)
            p.drawText(QRectF(0, 6, w, 22), Qt.AlignHCenter, hint)

    def _paint_finish(self, p: QPainter, w: int):
        """«Вау»-финал: надпись плавно вырастает и проявляется."""
        t = max(self._finish_phase, 0.0)
        ease = 1 - (1 - t) ** 3              # easeOutCubic
        p.setOpacity(min(ease * 1.4, 1.0))
        f = QFont()
        f.setPointSizeF(10 + 16 * ease)
        f.setBold(True)
        p.setFont(f)
        p.setPen(ACCENT)
        p.drawText(QRectF(0, 8, w, _H - 52), Qt.AlignCenter,
                   f"🏁 GAME OVER — {self._finish_text}")
        p.setOpacity(max(ease * 1.2 - 0.4, 0.0))
        sf = QFont()
        sf.setPointSize(11)
        sf.setBold(False)
        p.setFont(sf)
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(0, _H - 46, w, 20), Qt.AlignHCenter,
                   f"очки {self._score}   рекорд {self._high}")
