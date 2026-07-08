"""Мини-игра на время ожидания расшифровки — механика динозаврика Chrome.

Персонаж-маскот SteadyControl (голова — фирменный знак SC: кольцо с разрывом
и точкой) бежит по смене и перепрыгивает помехи контроля: кофе-перекуры, сон,
бумажные отчёты и телефоны. Препятствия — ЦВЕТНЫЕ векторные эмодзи Twemoji
(Copyright Twitter/X, лицензия CC-BY 4.0, https://github.com/jdecked/twemoji).

Эффекты: бегущая земля, облака с параллаксом, пыль при приземлении.
Игра не навязывается: заметная кнопка-призыв «▶ Мини-игра…».
Финал «GAME OVER — пора работать!» ~3.5 с. Рекорд и прошлая попытка сохраняются.
"""
import json
import math
import os
import random

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

try:
    from PySide6.QtSvg import QSvgRenderer
except Exception:  # noqa: BLE001 — крайний случай: без QtSvg играем с эмодзи
    QSvgRenderer = None

from ..storage.settings import app_data_dir

ACCENT = QColor("#3AC8C6")
ACCENT_DIM = QColor(58, 200, 198, 60)
GROUND = QColor("#2A2A2A")
CLOUD = QColor(255, 255, 255, 14)
TEXT_DIM = QColor("#9A9A9A")

_H = 190             # высота игрового поля (повыше — просторнее)
_GROUND_Y = _H - 36  # земля; под ней — строка подсказок
_PLAYER_X = 54
_GRAVITY = 0.55
_JUMP_V = -10.5

# Цветные Twemoji (CC-BY 4.0). Ключ → готовый SVG.
_TWEMOJI = {
    "coffee": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><ellipse fill="#99AAB5" cx="18" cy="26" rx="18" ry="10"/><ellipse fill="#CCD6DD" cx="18" cy="24" rx="18" ry="10"/><path fill="#F5F8FA" d="M18 31C3.042 31 1 16 1 12h34c0 2-1.958 19-17 19z"/><path fill="#CCD6DD" d="M34.385 9.644c2.442-10.123-9.781-7.706-12.204-5.799-1.34-.148-2.736-.234-4.181-.234-9.389 0-17 3.229-17 8.444C1 17.271 8.611 21.5 18 21.5s17-4.229 17-9.444c0-.863-.226-1.664-.615-2.412zm-2.503-2.692c-1.357-.938-3.102-1.694-5.121-2.25 1.875-.576 4.551-.309 5.121 2.25z"/><ellipse fill="#8A4B38" cx="18" cy="13" rx="15" ry="7"/><path fill="#D99E82" d="M20 17c-.256 0-.512-.098-.707-.293-2.337-2.337-2.376-4.885-.125-8.262.739-1.109.9-2.246.478-3.377-.461-1.236-1.438-1.996-1.731-2.077-.553 0-.958-.443-.958-.996 0-.552.491-.995 1.043-.995.997 0 2.395 1.153 3.183 2.625 1.034 1.933.91 4.039-.351 5.929-1.961 2.942-1.531 4.332-.125 5.738.391.391.391 1.023 0 1.414-.195.196-.451.294-.707.294zm-6-2c-.256 0-.512-.098-.707-.293-2.337-2.337-2.376-4.885-.125-8.262.727-1.091.893-2.083.494-2.947-.444-.961-1.431-1.469-1.684-1.499-.552 0-.989-.447-.989-1 0-.552.458-1 1.011-1 .997 0 2.585.974 3.36 2.423.481.899 1.052 2.761-.528 5.131-1.961 2.942-1.531 4.332-.125 5.738.391.391.391 1.023 0 1.414-.195.197-.451.295-.707.295z"/></svg>',
    "file": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><path fill="#E1E8ED" d="M32.415 9.586l-9-9C23.054.225 22.553 0 22 0c-1.104 0-1.999.896-2 2 0 .552.224 1.053.586 1.415l-3.859 3.859 9 9 3.859-3.859c.362.361.862.585 1.414.585 1.104 0 2.001-.896 2-2 0-.552-.224-1.052-.585-1.414z"/><path fill="#CCD6DD" d="M22 0H7C4.791 0 3 1.791 3 4v28c0 2.209 1.791 4 4 4h22c2.209 0 4-1.791 4-4V11h-9c-1 0-2-1-2-2V0z"/><path fill="#99AAB5" d="M22 0h-2v9c0 2.209 1.791 4 4 4h9v-2h-9c-1 0-2-1-2-2V0zm-5 8c0 .552-.448 1-1 1H8c-.552 0-1-.448-1-1s.448-1 1-1h8c.552 0 1 .448 1 1zm0 4c0 .552-.448 1-1 1H8c-.552 0-1-.448-1-1s.448-1 1-1h8c.552 0 1 .448 1 1zm12 4c0 .552-.447 1-1 1H8c-.552 0-1-.448-1-1s.448-1 1-1h20c.553 0 1 .448 1 1zm0 4c0 .553-.447 1-1 1H8c-.552 0-1-.447-1-1 0-.553.448-1 1-1h20c.553 0 1 .447 1 1zm0 4c0 .553-.447 1-1 1H8c-.552 0-1-.447-1-1 0-.553.448-1 1-1h20c.553 0 1 .447 1 1zm0 4c0 .553-.447 1-1 1H8c-.552 0-1-.447-1-1 0-.553.448-1 1-1h20c.553 0 1 .447 1 1z"/></svg>',
    "phone": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><path fill="#31373D" d="M11 36s-4 0-4-4V4s0-4 4-4h14s4 0 4 4v28s0 4-4 4H11z"/><path fill="#55ACEE" d="M9 5h18v26H9z"/></svg>',
    "zzz": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><path fill="#4289C1" d="M33 19c1.187 0 2 .786 2 2 0 1.073-.983 2-2 2H22c-1.496 0-2-.813-2-2 0-.565.632-1.492 1-2l8-12h-7c-1.128 0-2-.843-2-2 0-1.073.929-2 2-2h11c1.639 0 2 1.012 2 2 0 .621-.635 1.519-1 2l-8 12h7zm-16 5c.633 0 1 .353 1 1 0 .573-.458 1-1 1h-6c-.798 0-1-.367-1-1 0-.301.337-.729.533-1L15 18h-4c-.602 0-1-.384-1-1 0-.573.428-1 1-1h6c.874 0 1 .473 1 1 0 .331-.338.877-.533 1.133L13 24h4zm-9 7c.633 0 1 .353 1 1 0 .573-.458 1-1 1H2c-.798 0-1-.367-1-1 0-.301.337-.729.533-1L6 25H2c-.602 0-1-.384-1-1 0-.572.428-1 1-1h6c.874 0 1 .473 1 1 0 .331-.338.877-.533 1.133L4 31h4z"/></svg>',
}
_EMOJI_FALLBACK = {"coffee": "☕", "file": "📄", "phone": "📱", "zzz": "😴"}
# помехи, которые рисуем сами (актуальный юмор): telegram, блокировки, VPN
_CUSTOM_KINDS = ["tg", "rkn", "vpn"]


def _score_path() -> str:
    return os.path.join(app_data_dir(), "game.json")


def _load_scores() -> tuple[int, int]:
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
    """invite (кнопка-призыв) → ready → run → dead (повторы) → finish (финал)."""

    _H_INVITE = 58

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_H)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setCursor(Qt.PointingHandCursor)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._high, self._last = _load_scores()
        self._renderers = {}
        if QSvgRenderer is not None:
            for k, svg in _TWEMOJI.items():
                self._renderers[k] = QSvgRenderer(QByteArray(svg.encode()))
        self._reset()
        self._finish_phase = -1.0
        self._finish_text = ""

    # ---------- управление из страницы ----------

    def begin(self):
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
        QTimer.singleShot(3500, self.hide_now)

    def hide_now(self):
        self._timer.stop()
        self.hide()

    # ---------- игровая логика ----------

    def _reset(self):
        self._state = "invite"
        self._y = 0.0
        self._vy = 0.0
        self._obstacles: list[dict] = []
        self._dust: list[dict] = []          # частицы пыли
        self._clouds = [{"x": 120.0, "y": 26, "w": 70},
                        {"x": 420.0, "y": 44, "w": 100},
                        {"x": 720.0, "y": 20, "w": 56}]
        self._dist = 0.0                     # пройденный путь (для бегущей земли)
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
            self._puff(6)
        elif self._state == "dead":
            score = self._score
            self._reset()
            self._state = "run"
            self._last = score
            self._timer.start()

    def _puff(self, n: int):
        """Облачко пыли у ног (прыжок/приземление)."""
        for _ in range(n):
            self._dust.append({
                "x": _PLAYER_X + random.uniform(-6, 6),
                "y": _GROUND_Y - random.uniform(0, 4),
                "vx": random.uniform(-1.8, 0.4), "vy": random.uniform(-1.2, -0.1),
                "life": 1.0})

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
                self.update()
                return
            self._frames += 1
            if self._frames % 6 == 0:
                self._score += 1
            self._speed = 4.0 + min(self._score / 60.0, 5.0)
            self._dist += self._speed
            for c in self._clouds:           # параллакс облаков
                c["x"] -= self._speed * 0.25
                if c["x"] < -c["w"]:
                    c["x"] = self.width() + random.randint(0, 120)
            was_air = self._y < 0
            if self._y < 0 or self._vy < 0:
                self._vy += _GRAVITY
                self._y = min(self._y + self._vy, 0.0)
                if self._y == 0:
                    self._vy = 0.0
                    if was_air:
                        self._puff(8)        # пыль при приземлении
            self._spawn_in -= 1
            if self._spawn_in <= 0:
                self._obstacles.append(
                    {"x": float(self.width() + 20),
                     "size": random.choice((30, 36, 42)),
                     "kind": random.choice(list(_TWEMOJI) + _CUSTOM_KINDS)})
                self._spawn_in = random.randint(55, 110) - int(self._speed * 3)
            for ob in self._obstacles:
                ob["x"] -= self._speed
            self._obstacles = [o for o in self._obstacles if o["x"] > -50]
            for d in self._dust:
                d["x"] += d["vx"]
                d["y"] += d["vy"]
                d["life"] -= 0.05
            self._dust = [d for d in self._dust if d["life"] > 0]
            pr = QRectF(_PLAYER_X - 7, _GROUND_Y - 38 + self._y + 3, 15, 35)
            for ob in self._obstacles:
                s = ob["size"]
                orect = QRectF(ob["x"] + 6, _GROUND_Y - s + 6, s - 12, s - 6)
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
            self._paint_invite(p, w)
            return

        # облака (лёгкий параллакс-фон)
        p.setBrush(CLOUD)
        p.setPen(Qt.NoPen)
        for c in self._clouds:
            p.drawEllipse(QRectF(c["x"], c["y"], c["w"], 16))
        p.setBrush(Qt.NoBrush)

        # земля + бегущие насечки (видно движение)
        p.setPen(QPen(GROUND, 2))
        p.drawLine(8, _GROUND_Y, w - 8, _GROUND_Y)
        offset = self._dist % 26
        p.setPen(QPen(GROUND, 2))
        x = 8 - offset
        while x < w - 8:
            p.drawLine(int(x), _GROUND_Y + 5, int(x) + 8, _GROUND_Y + 5)
            x += 26

        if self._state == "finish":
            self._paint_finish(p, w)
            return

        # пыль
        p.setPen(Qt.NoPen)
        for d in self._dust:
            p.setBrush(QColor(154, 154, 154, int(90 * d["life"])))
            r = 2 + 3 * (1 - d["life"])
            p.drawEllipse(QRectF(d["x"] - r, d["y"] - r, r * 2, r * 2))
        p.setBrush(Qt.NoBrush)

        self._paint_player(p)

        # препятствия — цветные Twemoji и «актуальные» помехи
        for ob in self._obstacles:
            s = ob["size"]
            rect = QRectF(ob["x"], _GROUND_Y - s, s, s)
            kind = ob["kind"]
            if kind in _CUSTOM_KINDS:
                self._paint_custom_obstacle(p, rect, kind)
                continue
            r = self._renderers.get(kind)
            if r is not None:
                r.render(p, rect)
            else:
                f = QFont()
                f.setPointSize(max(int(s * 0.55), 11))
                p.setFont(f)
                p.drawText(rect, Qt.AlignCenter, _EMOJI_FALLBACK[kind])

        # счёт — справа сверху; подсказки — в отдельной зоне под землёй
        p.setPen(TEXT_DIM)
        sf = QFont()
        sf.setPointSize(10)
        p.setFont(sf)
        p.drawText(QRectF(0, 6, w - 14, 16), Qt.AlignRight,
                   f"очки {self._score}   рекорд {self._high}")

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
            p.drawText(QRectF(0, _GROUND_Y + 10, w, _H - _GROUND_Y - 12),
                       Qt.AlignHCenter | Qt.AlignVCenter, hint)

    def _paint_invite(self, p: QPainter, w: int):
        """ЯВНЫЙ призыв-кнопка: видно, что это игра и что по ней нужно кликнуть."""
        rect = QRectF(6, 5, w - 12, self._H_INVITE - 10)
        p.setPen(QPen(ACCENT, 1.5))
        p.setBrush(QColor(58, 200, 198, 22))
        p.drawRoundedRect(rect, 12, 12)
        # кнопка ▶ слева
        cx, cy = 34, self._H_INVITE / 2
        p.setBrush(ACCENT)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - 14, cy - 14, 28, 28))
        p.setBrush(QColor("#06282a"))
        p.drawPolygon(QPolygonF([QPointF(cx - 4, cy - 7), QPointF(cx - 4, cy + 7),
                                 QPointF(cx + 8, cy)]))
        p.setBrush(Qt.NoBrush)
        # тексты
        tf = QFont()
        tf.setPointSize(12)
        tf.setBold(True)
        p.setFont(tf)
        p.setPen(ACCENT)
        p.drawText(QRectF(58, 8, w - 70, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   "🎮 Мини-игра на время ожидания")
        sf = QFont()
        sf.setPointSize(10)
        p.setFont(sf)
        p.setPen(TEXT_DIM)
        rec = f"  ·  ваш рекорд: {self._high}" if self._high else ""
        p.drawText(QRectF(58, 29, w - 70, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   f"Нажмите сюда и перепрыгивайте помехи пробелом{rec}")

    def _paint_custom_obstacle(self, p: QPainter, rect: QRectF, kind: str):
        """Актуальный юмор, нарисовано векторно (без картинок и фонов):
        tg — телеграм-кружок с самолётиком; rkn — красный запрещающий знак;
        vpn — щиток с буквами VPN."""
        x, y, s = rect.x(), rect.y(), rect.width()
        p.save()
        if kind == "tg":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#29A9EB"))
            p.drawEllipse(rect)
            # бумажный самолётик
            p.setBrush(QColor("#FFFFFF"))
            pts = [(0.78, 0.24), (0.30, 0.48), (0.44, 0.56), (0.68, 0.38),
                   (0.50, 0.60), (0.50, 0.72), (0.58, 0.62), (0.78, 0.24)]
            p.drawPolygon(QPolygonF([QPointF(x + a * s, y + b * s) for a, b in pts]))
        elif kind == "rkn":
            red = QColor("#E0483E")
            p.setPen(QPen(red, max(s * 0.09, 2.5)))
            m = s * 0.08
            p.drawEllipse(rect.adjusted(m, m, -m, -m))
            k = s * 0.26
            p.drawLine(x + k, y + k, x + s - k, y + s - k)   # диагональ «запрещено»
            f = QFont()
            f.setPointSizeF(max(s * 0.22, 7.0))
            f.setBold(True)
            p.setFont(f)
            p.setPen(red)
            p.drawText(rect, Qt.AlignCenter, "РКН")
        elif kind == "vpn":
            # щиток
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#4A6FA5"))
            pts = [(0.5, 0.02), (0.95, 0.18), (0.95, 0.55), (0.5, 0.98),
                   (0.05, 0.55), (0.05, 0.18)]
            p.drawPolygon(QPolygonF([QPointF(x + a * s, y + b * s) for a, b in pts]))
            f = QFont()
            f.setPointSizeF(max(s * 0.26, 8.0))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(rect.adjusted(0, -s * 0.08, 0, -s * 0.08), Qt.AlignCenter, "VPN")
        p.restore()

    def _paint_player(self, p: QPainter):
        """Маскот SteadyControl: голова — фирменный знак (кольцо с разрывом
        и точкой), бегущие руки/ноги, при беге слегка наклонён вперёд."""
        x = _PLAYER_X
        foot = _GROUND_Y + self._y
        dead = self._state == "dead"
        col = QColor("#E05B5B") if dead else ACCENT
        pen = QPen(col, 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)

        # голова — мини-логотип SC: кольцо с разрывом справа + фирменная точка
        hc = (x + 1, foot - 33)
        r = 8
        p.drawArc(QRectF(hc[0] - r, hc[1] - r, r * 2, r * 2), 60 * 16, 280 * 16)
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(hc[0] + r - 3, hc[1] - 2.5, 5, 5))   # точка в разрыве
        p.setBrush(QColor("#ECECEC"))
        p.drawEllipse(QRectF(hc[0] + 1.5, hc[1] - 3, 3.4, 3.4))   # глаз — смотрит вперёд
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)

        # туловище с лёгким наклоном вперёд при беге
        lean = 2 if self._state == "run" else 0
        hip = (x - lean, foot - 12)
        p.drawLine(x + lean, foot - 24, hip[0], hip[1])

        in_air = self._y < 0
        if self._state == "run" and not in_air:
            ph = math.sin(self._frames * 0.35) * 0.8
        elif in_air:
            ph = 0.9
        else:
            ph = 0.35
        for s in (1, -1):                    # ноги в противофазе
            ang = ph * s
            p.drawLine(hip[0], hip[1],
                       hip[0] + 11 * math.sin(ang), foot - max(2 - abs(ang), 0))
        sh = (x + lean, foot - 22)           # руки в противофазе к ногам
        for s in (1, -1):
            ang = -ph * s
            p.drawLine(sh[0], sh[1], sh[0] + 10 * math.sin(ang), sh[1] + 8)

        if dead:                             # искры столкновения
            p.setPen(QPen(QColor("#E05B5B"), 2))
            for ang in (0.6, 1.6, 2.6, 3.8, 5.0):
                p.drawLine(hc[0] + 13 * math.cos(ang), hc[1] + 13 * math.sin(ang),
                           hc[0] + 19 * math.cos(ang), hc[1] + 19 * math.sin(ang))

    @staticmethod
    def _clamp01(v: float) -> float:
        return max(0.0, min(v, 1.0))

    def _paint_finish(self, p: QPainter, w: int):
        """«Вау»-финал в три акта (3.5 с): GAME OVER с отскоком →
        «пора работать!» снизу → конфетти → плавное растворение."""
        t = max(self._finish_phase, 0.0)
        fade_out = 1.0 if t < 0.85 else max(1.0 - (t - 0.85) / 0.15, 0.0)

        t1 = self._clamp01(t / 0.28)
        c1, c3 = 1.70158, 2.70158
        back = 1 + c3 * (t1 - 1) ** 3 + c1 * (t1 - 1) ** 2
        p.setOpacity(min(t1 * 1.6, 1.0) * fade_out)
        f = QFont()
        f.setPointSizeF(max(6.0, 28 * back))
        f.setBold(True)
        p.setFont(f)
        p.setPen(ACCENT)
        # без эмодзи-флажка: на Windows он рисуется чёрно-белой «шахматкой»
        p.drawText(QRectF(0, 10, w, 66), Qt.AlignCenter, "GAME OVER")

        t2 = self._clamp01((t - 0.22) / 0.30)
        rise = (1 - t2) ** 2 * 20
        p.setOpacity(t2 * fade_out)
        sf = QFont()
        sf.setPointSize(15)
        sf.setBold(True)
        p.setFont(sf)
        p.setPen(QColor("#ECECEC"))
        p.drawText(QRectF(0, 72 + rise, w, 30), Qt.AlignCenter, self._finish_text)
        p.setOpacity(t2 * 0.8 * fade_out)
        mf = QFont()
        mf.setPointSize(10)
        p.setFont(mf)
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(0, 104 + rise, w, 20), Qt.AlignHCenter,
                   f"очки {self._score}   ·   рекорд {self._high}")

        t3 = self._clamp01((t - 0.10) / 0.55)
        if 0.0 < t3 < 1.0:
            cx, cy = w / 2, 52
            p.setOpacity((1 - t3) * fade_out)
            for i, ang in enumerate(x * 0.485 for x in range(15)):
                r = 30 + t3 * (84 + (i % 4) * 26)
                size = 4 if i % 3 else 7
                col = ACCENT if i % 2 else QColor("#ECECEC")
                p.setBrush(col)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(cx + r * math.cos(ang) - size / 2,
                                     cy + r * math.sin(ang) * 0.6 - size / 2,
                                     size, size))
            p.setBrush(Qt.NoBrush)
