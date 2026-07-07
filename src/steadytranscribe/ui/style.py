"""Стили: адаптируются к светлой/тёмной теме системы через палитру Qt."""

STYLE = """
#h1 { font-size: 20px; font-weight: 700; }
#h2 { font-size: 15px; font-weight: 600; }
#subtitle, #hint { color: palette(mid); font-size: 12px; }
#card {
    background: palette(base);
    border: 1px solid palette(midlight);
    border-radius: 12px;
}
#errorCard { border: 1px solid #d9534f; }
#errorText { color: #d9534f; }
#cardTitle { font-size: 14px; font-weight: 600; }
#dropZone {
    border: 2px dashed palette(mid);
    border-radius: 10px;
    padding: 18px;
    color: palette(text);
}
#dropZone[hover="true"] { border-color: palette(highlight); }
#fileName { font-size: 13px; }
#stats { color: palette(mid); font-size: 12px; }
QPushButton#primary {
    background: palette(highlight);
    color: palette(highlighted-text);
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton#historyRow {
    text-align: left;
    padding: 8px 12px;
    border: 1px solid palette(midlight);
    border-radius: 8px;
    background: palette(base);
}
QPushButton#historyRow[selected="true"] { border: 1px solid #34a853; }
#toast {
    background: #34a853;
    color: white;
    padding: 6px 14px;
    border-radius: 8px;
    font-weight: 600;
}
QProgressBar { border-radius: 6px; height: 10px; }
"""
