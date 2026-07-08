"""Скриншот-харнесс: программа фотографирует сама себя (для проверки UI глазами).

Запуск: SteadyTranscribe --screenshots <папка>
Снимает каждую страницу на двух размерах окна (минимальном 800×500 и обычном
1280×800) + все состояния мини-игры. Используется в CI перед релизом:
разработчик СМОТРИТ снимки и ловит наезды текста/обрезанные кнопки до пользователей.
"""
import os


def run_screenshots(out_dir: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    os.environ.setdefault("STEADY_UITEST", "1")

    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    app.setStyle("Fusion")
    from .ui.theme import QSS
    app.setStyleSheet(QSS)
    from .ui.main_window import MainWindow
    win = MainWindow()
    win.show()

    def shot(name: str):
        app.processEvents()
        win.grab().save(os.path.join(out_dir, name + ".png"))

    pages = {0: "transcribe", 1: "models", 2: "settings", 3: "history",
             4: "stats", 5: "help"}
    for width, height, tag in ((800, 500, "min"), (1280, 800, "std")):
        win.resize(width, height)
        app.processEvents()
        for idx, name in pages.items():
            win.stack.setCurrentIndex(idx)
            app.processEvents()
            shot(f"{tag}-{name}")

        # состояния мини-игры (на странице расшифровки)
        win.stack.setCurrentIndex(0)
        game = win.transcribe_page.game
        game.begin()                     # призыв
        shot(f"{tag}-game-invite")
        game._expand()                   # готов к игре
        shot(f"{tag}-game-ready")
        game._state = "run"              # бег с препятствиями (все виды графики)
        game._score, game._frames = 137, 40
        game._obstacles = [{"x": 260.0, "size": 36, "kind": "coffee"},
                           {"x": 380.0, "size": 40, "kind": "tg"},
                           {"x": 500.0, "size": 34, "kind": "rkn"},
                           {"x": 620.0, "size": 38, "kind": "vpn"},
                           {"x": 730.0, "size": 32, "kind": "zzz"}]
        game.update()
        shot(f"{tag}-game-run")
        game._state = "dead"             # проигрыш
        game.update()
        shot(f"{tag}-game-dead")
        game._finish_text = "Расшифровка готова — пора работать!"
        game._state = "finish"           # финал в середине анимации
        game._finish_phase = 0.45
        game.update()
        shot(f"{tag}-game-finish")
        game.hide_now()

    # ASCII only: консоль Windows (cp1252) падает на кириллице
    print(f"SCREENSHOTS OK: {len(os.listdir(out_dir))} files", flush=True)
    return 0
