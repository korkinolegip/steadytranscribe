"""Мини-игра на время ожидания расшифровки — механика динозаврика Chrome.

Фирменный стиль SteadyControl: микро-персонаж с головой-логотипом SC (кружок
с фирменной точкой) бежит по смене, размахивая руками и ногами, и перепрыгивает
помехи контроля — кофе-перекуры, сон, бумажные отчёты и телефоны. Препятствия —
векторные иконки Feather (open source, MIT): чистые контуры, никаких фонов.

Пробел или клик — прыжок. Игра не навязывается: компактный призыв «сыграть?».
Когда расшифровка готова — финал «GAME OVER — пора работать!» ~2 секунды.
Рекорд и прошлая попытка сохраняются.
"""
import json
import math
import os
import random

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

try:
    from PySide6.QtSvg import QSvgRenderer
except Exception:  # noqa: BLE001 — на всякий случай: без SVG играем с эмодзи
    QSvgRenderer = None

from ..storage.settings import app_data_dir

ACCENT = QColor("#3AC8C6")
GROUND = QColor("#2A2A2A")
TEXT_DIM = QColor("#9A9A9A")
OBSTACLE = "#93A5A5"                 # приглушённый контур помех

_H = 150            # высота поля
_GROUND_Y = _H - 32  # земля выше нижнего края — под ней строка подсказок
_PLAYER_X = 50
_GRAVITY = 0.55
_JUMP_V = -10.5

# Иконки Feather (feathericons.com, MIT) — контурные, без фонов
_FEATHER = {
    "coffee": ('<path d="M18 8h1a4 4 0 0 1 0 8h-1"/>'
               '<path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/>'
               '<line x1="6" y1="1" x2="6" y2="4"/>'
               '<line x1="10" y1="1" x2="10" y2="4"/>'
               '<line x1="14" y1="1" x2="14" y2="4"/>'),
    "file":   ('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 '
               '2-2V8z"/><polyline points="14 2 14 8 20 8"/>'
               '<line x1="16" y1="13" x2="8" y2="13"/>'
               '<line x1="16" y1="17" x2="8" y2="17"/>'),
    "phone":  ('<rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>'
               '<line x1="12" y1="18" x2="12.01" y2="18"/>'),
    "moon":   '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
}
_EMOJI_FALLBACK = {"coffee": "☕", "file": "📄", "phone": "📱", "moon": "😴"}


def _svg(body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{OBSTACLE}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


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
    """Состояния: invite (компактный призыв) → ready → run → dead (повторы).
    finish() — расшифровка готова: финал «пора работать» ~2 с и самоскрытие."""

    _H_INVITE = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_H)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setCursor(Qt.PointingHandCursor)
        self._timer = QTimer(self)
        self._timer.setInterval(16)          # ~60 кадров/с
        self._timer.timeout.connect(self._tick)
        self._high, self._last = _load_scores()
        self._renderers = {}
        if QSvgRenderer is not None:
            for k, body in _FEATHER.items():
                self._renderers[k] = QSvgRenderer(QByteArray(_svg(body).encode()))
        self._reset()
        self._finish_phase = -1.0
        self._finish_text = ""

    # ---------- управление из страницы ----------

    def begin(self):
        """Показать ПРИЗЫВ сыграть (игра стартует только по клику)."""
        self._reset()
        self._finish_phase = -1.0
        self._state = "invite"
        self.setFixedHeight(self._H_INVITE)
        self.show()
        self.update()

    def _expand(self):
        self.setFixedHeight(_H)
        self._state = "ready"
        self.setFocus()
        self._timer.start()
        self.update()

    def finish(self, text: str = "Пора работать!"):
        """Расшифровка готова: играли — финал ~2 с, нет — тихо убрать поле."""
        if not self.isVisible():
            return
        if self._state in ("invite", "ready"):
            self.hide_now()
            return
        self._save_record()
        self._finish_text = text
        self._finish_phase = 0.0
        self._state = "finish"
        self._timer.start()
        QTimer.singleShot(3500, self.hide_now)   # финал ~3.5 с, затем плавно уходим

    def hide_now(self):
        self._timer.stop()
        self.hide()

    # ---------- игровая логика ----------

    def _reset(self):
        self._state = "invite"               # invite | ready | run | dead | finish
        self._y = 0.0
        self._vy = 0.0
        self._obstacles: list[dict] = []     # {x, size, kind}
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
            score = self._score
            self._reset()
            self._state = "run"
            self._last = score
            self._timer.start()

    def _save_record(self):
        self._last = self._score
        self._high = max(self._high, self._score)
        _save_scores(self._high, self._last)

    def _tick(self):
        if self._state == "finish":
            self._finish_phase = min(self._finish_phase + 16 / 3500, 1.0)
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
            if self._y < 0 or self._vy < 0:
                self._vy += _GRAVITY
                self._y = min(self._y + self._vy, 0.0)
                if self._y == 0:
                    self._vy = 0.0
            self._spawn_in -= 1
            if self._spawn_in <= 0:
                self._obstacles.append(
                    {"x": float(self.width() + 20),
                     "size": random.choice((26, 32, 38)),
                     "kind": random.choice(list(_FEATHER))})
                self._spawn_in = random.randint(55, 110) - int(self._speed * 3)
            for ob in self._obstacles:
                ob["x"] -= self._speed
            self._obstacles = [o for o in self._obstacles if o["x"] > -50]
            pr = QRectF(_PLAYER_X - 7, _GROUND_Y - 36 + self._y + 3, 15, 33)
            for ob in self._obstacles:
                s = ob["size"]
                orect = QRectF(ob["x"] + 5, _GROUND_Y - s + 5, s - 10, s - 5)
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

        # персонаж и помехи
        self._paint_player(p)
        for ob in self._obstacles:
            s = ob["size"]
            rect = QRectF(ob["x"], _GROUND_Y - s, s, s)
            r = self._renderers.get(ob["kind"])
            if r is not None:
                r.render(p, rect)
            else:                            # запасной вариант без QtSvg
                f = QFont()
                f.setPointSize(max(int(s * 0.55), 11))
                p.setFont(f)
                p.drawText(rect, Qt.AlignCenter, _EMOJI_FALLBACK[ob["kind"]])

        # счёт — только справа сверху (подсказки живут ВНИЗУ, не пересекаются)
        p.setPen(TEXT_DIM)
        sf = QFont()
        sf.setPointSize(10)
        p.setFont(sf)
        p.drawText(QRectF(0, 6, w - 14, 16), Qt.AlignRight,
                   f"очки {self._score}   рекорд {self._high}")

        # строка подсказок — ПОД землёй, отдельная зона
        hint, color = None, TEXT_DIM
        if self._state == "ready":
            last = f"  ·  прошлый раз: {self._last}" if self._last else ""
            hint = f"Пробел или клик — прыжок{last}"
        elif self._state == "dead":
            hint, color = (f"💥 Контроль потерян! {self._score} очков.  "
                           "Пробел — вернуть контроль"), ACCENT
        elif self._state == "run":
            win = self.window()
            if win and not win.isActiveWindow():
                hint = "⏸ Пауза (окно неактивно)"
        if hint:
            p.setPen(color)
            hf = QFont()
            hf.setPointSize(10)
            p.setFont(hf)
            p.drawText(QRectF(0, _GROUND_Y + 6, w, _H - _GROUND_Y - 8),
                       Qt.AlignHCenter | Qt.AlignVCenter, hint)

    def _paint_player(self, p: QPainter):
        """Микро-персонаж: голова — мини-логотип SC (кружок с фирменной точкой),
        бегущие руки и ноги (машут в противофазе, как у спрайтовых бегунов)."""
        x = _PLAYER_X
        foot = _GROUND_Y + self._y           # уровень «ступней»
        dead = self._state == "dead"
        pen = QPen(QColor("#E05B5B") if dead else ACCENT, 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)

        head_c = (x, foot - 30)
        p.drawEllipse(QRectF(head_c[0] - 7, head_c[1] - 7, 14, 14))
        p.setBrush(QColor("#E05B5B") if dead else ACCENT)
        p.drawEllipse(QRectF(head_c[0] + 6, head_c[1] + 2, 5, 5))   # фирменная точка
        p.setBrush(Qt.NoBrush)

        # туловище
        hip = (x, foot - 11)
        p.drawLine(x, foot - 23, hip[0], hip[1])

        in_air = self._y < 0
        if self._state == "run" and not in_air:
            ph = math.sin(self._frames * 0.35) * 0.8       # фаза бега
        elif in_air:
            ph = 0.9                                        # прыжок: конечности вперёд
        else:
            ph = 0.35                                       # статичная поза
        # ноги (в противофазе)
        for s in (1, -1):
            ang = ph * s
            p.drawLine(hip[0], hip[1],
                       hip[0] + 10 * math.sin(ang), foot - max(2 - abs(ang), 0))
        # руки (в противофазе к ногам)
        sh = (x, foot - 21)                                 # плечи
        for s in (1, -1):
            ang = -ph * s
            p.drawLine(sh[0], sh[1],
                       sh[0] + 9 * math.sin(ang), sh[1] + 7)

        if dead:                                            # искры столкновения
            p.setPen(QPen(QColor("#E05B5B"), 2))
            for ang in (0.6, 1.6, 2.6, 3.8, 5.0):
                p.drawLine(head_c[0] + 12 * math.cos(ang), head_c[1] + 12 * math.sin(ang),
                           head_c[0] + 18 * math.cos(ang), head_c[1] + 18 * math.sin(ang))

    @staticmethod
    def _clamp01(v: float) -> float:
        return max(0.0, min(v, 1.0))

    def _paint_finish(self, p: QPainter, w: int):
        """«Вау»-финал в три акта (3.5 с): GAME OVER влетает с отскоком →
        «пора работать!» поднимается снизу → искры-конфетти, плавное растворение."""
        t = max(self._finish_phase, 0.0)
        # общий плавный уход в последние 15% времени
        fade_out = 1.0 if t < 0.85 else max(1.0 - (t - 0.85) / 0.15, 0.0)

        # акт 1: GAME OVER — easeOutBack (перелёт и мягкий отскок)
        t1 = self._clamp01(t / 0.28)
        c1, c3 = 1.70158, 2.70158
        back = 1 + c3 * (t1 - 1) ** 3 + c1 * (t1 - 1) ** 2
        p.setOpacity(min(t1 * 1.6, 1.0) * fade_out)
        f = QFont()
        f.setPointSizeF(max(6.0, 26 * back))
        f.setBold(True)
        p.setFont(f)
        p.setPen(ACCENT)
        p.drawText(QRectF(0, 4, w, 58), Qt.AlignCenter, "🏁 GAME OVER")

        # акт 2: «пора работать» приподнимается снизу и проявляется
        t2 = self._clamp01((t - 0.22) / 0.30)
        rise = (1 - t2) ** 2 * 18            # старт на 18px ниже
        p.setOpacity(t2 * fade_out)
        sf = QFont()
        sf.setPointSize(14)
        sf.setBold(True)
        p.setFont(sf)
        p.setPen(QColor("#ECECEC"))
        p.drawText(QRectF(0, 58 + rise, w, 30), Qt.AlignCenter, self._finish_text)
        p.setOpacity(t2 * 0.8 * fade_out)
        mf = QFont()
        mf.setPointSize(10)
        p.setFont(mf)
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(0, 88 + rise, w, 20), Qt.AlignHCenter,
                   f"очки {self._score}   ·   рекорд {self._high}")

        # акт 3: искры-конфетти разлетаются из центра
        t3 = self._clamp01((t - 0.10) / 0.55)
        if 0.0 < t3 < 1.0:
            cx, cy = w / 2, 44
            p.setOpacity((1 - t3) * fade_out)
            for i, ang in enumerate(x * 0.485 for x in range(13)):
                r = 26 + t3 * (70 + (i % 4) * 22)
                size = 4 if i % 3 else 6
                col = ACCENT if i % 2 else QColor("#ECECEC")
                p.setBrush(col)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(cx + r * math.cos(ang) - size / 2,
                                     cy + r * math.sin(ang) * 0.55 - size / 2,
                                     size, size))
            p.setBrush(Qt.NoBrush)
