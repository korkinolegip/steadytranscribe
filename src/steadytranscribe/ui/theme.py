"""Тёмная тема по образцу FluidVoice: палитра, радиусы, типографика."""

ACCENT = "#3AC8C6"          # cyan — дефолтный акцент FluidVoice
WINDOW_BG = "#121212"       # rgb(0.07)
CONTENT_BG = "#171717"      # rgb(0.09)
SIDEBAR_BG = "#0F0F0F"      # rgb(0.06)
CARD_BG = "#141414"         # rgb(0.08)
CARD_BG_ELEVATED = "#1C1C1C"
BORDER = "rgba(255,255,255,0.10)"
SEPARATOR = "rgba(255,255,255,0.16)"
TEXT = "#ECECEC"
TEXT_SECONDARY = "#9A9A9A"
TEXT_TERTIARY = "#6E6E6E"
WARNING = "#F59E0B"
ERROR = "#EF4444"

QSS = f"""
* {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {WINDOW_BG}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

/* ---------- Sidebar ---------- */
#sidebar {{ background: {SIDEBAR_BG}; border: none; outline: none; padding-top: 6px; }}
#sidebar::item {{
    padding: 7px 10px; margin: 1px 8px; border-radius: 8px;
    color: {TEXT}; font-size: 14px;
}}
#sidebar::item:selected {{ background: {ACCENT}; color: #06282a; font-weight: 600; }}
#sidebar::item:hover:!selected {{ background: rgba(255,255,255,0.05); }}
#appName {{ font-size: 15px; font-weight: 700; padding: 12px; }}
#sidebarSection {{
    color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;
    padding: 10px 18px 2px 18px;
}}

/* ---------- Карточки ---------- */
#card {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
#cardTitle {{ font-size: 15px; font-weight: 600; }}
#h1 {{ font-size: 22px; font-weight: 700; }}
#h2 {{ font-size: 15px; font-weight: 600; }}
#subtitle, #hint {{ color: {TEXT_SECONDARY}; font-size: 12px; }}
#tertiary {{ color: {TEXT_TERTIARY}; font-size: 12px; }}
#stats {{ color: {TEXT_SECONDARY}; font-size: 12px; }}
#warn {{ color: {WARNING}; font-size: 12px; font-weight: 600; }}
#startHint {{ color: {ACCENT}; font-size: 13px; font-weight: 700; background: transparent; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {SEPARATOR}; background: {CARD_BG_ELEVATED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
#bigValue {{ font-size: 30px; font-weight: 700; }}
#tileTitle {{ color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600; }}

/* ---------- Кнопки ---------- */
QPushButton {{
    background: {CARD_BG_ELEVATED}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {SEPARATOR}; }}
QPushButton:disabled {{ color: {TEXT_TERTIARY}; }}
QPushButton#primary {{
    background: {ACCENT}; color: #06282a; font-weight: 600;
    border: none; padding: 9px 14px;
}}
QPushButton#primary:disabled {{ background: #1f4a49; color: #4d7a79; }}
QPushButton#download {{ background: #3B82F6; color: white; border: none; font-weight: 600; }}
QPushButton#activate {{ background: {ACCENT}; color: #06282a; border: none; font-weight: 600; }}
QPushButton#danger {{ color: {ERROR}; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; }}

#activeBadge {{
    background: rgba(58,200,198,0.25); color: {ACCENT};
    border-radius: 10px; padding: 3px 10px; font-weight: 600; font-size: 11px;
}}

/* ---------- Зона перетаскивания ---------- */
#dropZone {{
    border: 2px dashed {SEPARATOR}; border-radius: 12px;
    padding: 18px; background: transparent;
}}
#dropZone[hover="true"] {{ border-color: {ACCENT}; }}

/* ---------- История ---------- */
QPushButton#historyRow {{
    text-align: left; padding: 9px 12px;
    border: 1px solid {BORDER}; border-radius: 8px; background: {CARD_BG};
}}
QPushButton#historyRow[selected="true"] {{ background: {ACCENT}; color: #06282a; border: none; }}
QLineEdit {{
    background: {CARD_BG}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 7px 10px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

/* ---------- Строки моделей ---------- */
#modelRow {{ background: transparent; border: 1px solid transparent; border-radius: 10px; }}
#modelRow[selected="true"] {{ background: rgba(255,255,255,0.04); border-color: {BORDER}; }}
#modelRow[active="true"] {{ border: 2px solid {ACCENT}; }}
#modelName {{ font-size: 14px; font-weight: 600; }}
#speedLabel {{ color: {WARNING}; font-size: 11px; }}
#accLabel {{ color: {ACCENT}; font-size: 11px; }}

/* ---------- Прочее ---------- */
QTextEdit, QPlainTextEdit {{
    background: {CONTENT_BG}; border: 1px solid {BORDER};
    border-radius: 10px; padding: 8px; color: {TEXT};
}}
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}
QProgressBar {{
    background: {CARD_BG_ELEVATED}; border: none; border-radius: 5px;
    height: 14px; text-align: center; color: white; font-size: 10px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QComboBox, QSpinBox {{
    background: {CARD_BG_ELEVATED}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 5px 10px;
}}
QComboBox QAbstractItemView {{ background: {CARD_BG_ELEVATED}; border: 1px solid {BORDER}; }}
#errorCard {{ background: {CARD_BG}; border: 1px solid {ERROR}; border-radius: 16px; }}
#errorText {{ color: {ERROR}; }}
#toast {{
    background: {ACCENT}; color: #06282a; padding: 7px 14px;
    border-radius: 8px; font-weight: 600;
}}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}

/* ---------- Раздел «Как пользоваться» ---------- */
#hero {{
    border-radius: 20px; padding: 26px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(58,200,198,0.22), stop:1 rgba(59,130,246,0.14));
    border: 1px solid {BORDER};
}}
#heroTitle {{ font-size: 26px; font-weight: 800; }}
#heroSub {{ color: {TEXT}; font-size: 14px; }}
#sectionTitle {{ font-size: 18px; font-weight: 700; }}
#stepCard {{
    background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 16px; padding: 6px;
}}
#stepBadge {{
    background: {ACCENT}; color: #06282a; font-weight: 800; font-size: 15px;
    border-radius: 15px; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
    qproperty-alignment: AlignCenter;
}}
#stepEmoji {{ font-size: 34px; }}
#stepTitle {{ font-size: 15px; font-weight: 700; }}
#arrow {{ color: {ACCENT}; font-size: 24px; font-weight: 800; }}
#feature {{
    background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 14px; padding: 4px;
}}
#feature:hover {{ border-color: {ACCENT}; background: {CARD_BG_ELEVATED}; }}
#featIcon {{ font-size: 26px; }}
#featTitle {{ font-size: 14px; font-weight: 700; }}
#chip {{
    background: rgba(58,200,198,0.16); color: {ACCENT};
    border-radius: 10px; padding: 4px 10px; font-weight: 600; font-size: 12px;
}}
"""
