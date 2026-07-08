"""Точка входа SteadyTranscribe."""
import faulthandler
import logging
import os
import platform
import sys
import traceback

os.environ.setdefault("CT2_USE_MKL", "0")


def _detect_cpu() -> str:
    """Определяет ускорение процессора (без подпроцессов!).
    Windows — системный вызов IsProcessorFeaturePresent (AVX2/AVX);
    macOS Apple Silicon — всегда быстрый NEON-режим, ISA не форсируем.
    ВАЖНО: не использовать py-cpuinfo — в собранном exe он рекурсивно
    запускает копии приложения (плодятся окна)."""
    if sys.platform == "darwin":
        # Apple Silicon (и Intel-маки): ctranslate2 сам выбирает лучший бэкенд.
        # Форсировать GENERIC нельзя — потеряем NEON/Accelerate и скорость.
        return "apple"
    try:
        import ctypes
        if sys.platform == "win32":
            # PF_AVX2_INSTRUCTIONS_AVAILABLE = 40 (Windows API IsProcessorFeaturePresent)
            if ctypes.windll.kernel32.IsProcessorFeaturePresent(40):
                return "avx2"          # быстрый режим — ISA не форсируем
            # PF_AVX_INSTRUCTIONS_AVAILABLE = 39
            if ctypes.windll.kernel32.IsProcessorFeaturePresent(39):
                os.environ["CT2_FORCE_CPU_ISA"] = "AVX"
                return "avx"
    except Exception:  # noqa: BLE001
        pass
    os.environ["CT2_FORCE_CPU_ISA"] = "GENERIC"
    return "generic"


CPU_MODE = _detect_cpu()

# macOS: python.org-сборка Python и frozen-приложение не видят системные
# корневые сертификаты — все HTTPS-запросы urllib (модели, обновления,
# аналитика) падали бы с CERTIFICATE_VERIFY_FAILED. Подставляем пакет certifi.
if sys.platform == "darwin" and not os.environ.get("SSL_CERT_FILE"):
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except Exception:  # noqa: BLE001
        pass

from .storage.settings import app_data_dir


def _setup_logging() -> str:
    log_path = os.path.join(app_data_dir(), "log.txt")
    logging.basicConfig(
        filename=log_path, level=logging.INFO, encoding="utf-8",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        faulthandler.enable(open(os.path.join(app_data_dir(), "crash.txt"), "w"))
    except Exception:  # noqa: BLE001
        pass
    return log_path


def _selftest(audio_path: str) -> int:
    """Прогон транскрипции без GUI — для проверки собранного exe в CI.
    Только ASCII в выводе (консоль Windows = cp1252)."""
    faulthandler.enable()
    print(f"SELFTEST: start CPU_MODE={CPU_MODE} ISA={os.environ.get('CT2_FORCE_CPU_ISA','fast')}",
          flush=True)
    from .core import convert
    from .core.transcriber import Transcriber
    print("SELFTEST: imports ok", flush=True)
    wav = convert.to_wav16k(audio_path)
    print("SELFTEST: ffmpeg convert ok", flush=True)
    t = Transcriber()
    # device="cuda" — воспроизводим случай пользователя (раньше падало на CUDA)
    r = t.transcribe(wav, model="tiny", language="ru", device="cuda",
                     initial_prompt="",
                     status_cb=lambda s, p: print(f"SELFTEST: progress {p*100:.0f}%", flush=True),
                     cancel_check=lambda: False, word_timestamps=True)
    print(f"SELFTEST: transcribe DONE chars={len(r.text)} words={len(r.words or [])}", flush=True)
    # проверяем и диаризацию (у неё свои onnx-модели)
    from .core import diarize
    if diarize.is_available():
        turns = diarize.diarize(wav, 2, status_cb=lambda s, p: None, cancel_check=lambda: False)
        print(f"SELFTEST: diarize DONE turns={len(turns)}", flush=True)
    else:
        print("SELFTEST: diarize models missing", flush=True)
    print("SELFTEST: ALL OK", flush=True)
    return 0


def _run_diarize(wav_path: str, num_speakers: int) -> int:
    """Диаризация в ОТДЕЛЬНОМ процессе — интерфейс не зависает.
    Печатает прогресс (PROGRESS доля) и результат (RESULT json).
    Пишет отдельный лог, чтобы диагностировать сбои."""
    _setup_logging()
    diag_log = logging.getLogger("diarize")
    try:
        diag_log.info("diarize start: %s speakers=%s", wav_path, num_speakers)
        import json
        from .core import diarize
        turns = diarize.diarize(
            wav_path, num_speakers,
            status_cb=lambda s, p: print(f"PROGRESS {p:.3f}", flush=True),
            cancel_check=lambda: False)
        diag_log.info("diarize done: turns=%s", len(turns))
        print("RESULT " + json.dumps([[t.speaker, t.start, t.end] for t in turns]), flush=True)
        return 0
    except Exception as e:  # noqa: BLE001
        diag_log.exception("diarize FAILED: %s", e)
        print(f"ERROR {e}", flush=True)
        return 1


def main():
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        sys.exit(_selftest(sys.argv[idx + 1]))
    if "--diarize" in sys.argv:
        idx = sys.argv.index("--diarize")
        sys.exit(_run_diarize(sys.argv[idx + 1], int(sys.argv[idx + 2])))
    if "--screenshots" in sys.argv:
        # UI-фотосессия для проверки глазами перед релизом (см. uitest.py)
        idx = sys.argv.index("--screenshots")
        from .uitest import run_screenshots
        sys.exit(run_screenshots(sys.argv[idx + 1]))
    if "--uninstall-ping" in sys.argv:
        # вызывается деинсталлятором: помечаем это устройство удалённым
        # в аналитике (пользователь без устройств исчезает из базы целиком)
        try:
            from .storage import analytics
            analytics.track("uninstalled")
            analytics.flush(timeout=6)
        except Exception:  # noqa: BLE001
            pass
        sys.exit(0)

    # Отложенное обновление с прошлого сеанса? Ставим ДО открытия окна:
    # установщик тихо обновит программу и сам запустит новую версию.
    try:
        from .ui import updater as _updater
        if _updater.apply_staged_at_launch():
            sys.exit(0)
    except Exception:  # noqa: BLE001
        pass

    from PySide6.QtWidgets import QApplication, QMessageBox
    log_path = _setup_logging()
    logging.info("=== SteadyTranscribe запуск ===")

    # ОДИН ЭКЗЕМПЛЯР: две копии программы делят одни файлы настроек/обновлений
    # и мешают друг другу (наблюдалось: установщик перезапустил программу, поверх
    # запустили вторую → «программа сама закрылась»). Вторая копия тихо выходит.
    from PySide6.QtCore import QLockFile
    global _single_lock
    _single_lock = QLockFile(os.path.join(app_data_dir(), "app.lock"))
    _single_lock.setStaleLockTime(0)
    if not _single_lock.tryLock(100):
        logging.info("Уже запущен другой экземпляр — выходим.")
        sys.exit(0)
    try:
        logging.info("CPU=%s cores=%s режим=%s ISA=%s OS=%s",
                     platform.processor(), os.cpu_count(), CPU_MODE,
                     os.environ.get("CT2_FORCE_CPU_ISA", "быстрый"), platform.platform())
        # на слабом CPU (без AVX2) по умолчанию — лёгкая модель, если пользователь ещё не выбирал
        from .storage import settings as _s
        conf = _s.load()
        if CPU_MODE == "generic" and not conf.get("onboarded"):
            conf["model"] = "small"
            _s.save(conf)
            logging.info("Слабый CPU: модель по умолчанию понижена до small")
    except Exception:  # noqa: BLE001
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("SteadyTranscribe")
    app.setStyle("Fusion")

    from .ui.theme import QSS
    app.setStyleSheet(QSS)
    if sys.platform == "darwin":
        # тёмная рамка окна под тёмную тему (иначе титлбар останется белым)
        try:
            from PySide6.QtCore import Qt as _Qt
            app.styleHints().setColorScheme(_Qt.ColorScheme.Dark)
        except Exception:  # noqa: BLE001
            pass

    def excepthook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.error("Необработанная ошибка:\n%s", text)
        try:
            from .storage import analytics
            analytics.track("exception", err=str(exc_value)[:200])
            analytics.flush_async()
        except Exception:  # noqa: BLE001
            pass
        from .ui import feedback
        box = QMessageBox(QMessageBox.Critical, "Ошибка SteadyTranscribe",
                          f"Произошла ошибка. Приложение продолжит работу.\n\n{exc_value}")
        send = box.addButton("Отправить разработчику", QMessageBox.AcceptRole)
        box.addButton("Закрыть", QMessageBox.RejectRole)
        box.exec()
        feedback.send_auto(extra=f"Ошибка: {exc_value}")  # тихо отправляем сразу
        if box.clickedButton() is send:
            feedback.send_report(extra=f"Ручная отправка: {exc_value}")
    sys.excepthook = excepthook

    # macOS: запуск из DMG/Загрузок → предлагаем перенести в «Программы».
    # Без этого автообновление невозможно (карантинная «транслокация» делает
    # путь приложения случайным и только для чтения).
    if sys.platform == "darwin" and not os.environ.get("STEADY_UITEST"):
        try:
            from .ui import macinstall
            if macinstall.offer_move_to_applications():
                sys.exit(0)   # скопировано и перезапущено из «Программ»
        except Exception:  # noqa: BLE001
            logging.exception("перенос в «Программы» не удался")

    from .ui.main_window import MainWindow
    window = MainWindow()
    # после обновления на простое возвращаемся СВЁРНУТЫМИ — не крадём фокус
    from .ui import notify as _notify
    from .ui import updater as _upd
    if _upd.consume_restart_marker():
        window.showMinimized()
        _notify.send(getattr(window, "tray", None), "Программа обновлена",
                     f"Установлена версия {_upd.CURRENT_VERSION}. Всё готово к работе.",
                     5000)
    else:
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
