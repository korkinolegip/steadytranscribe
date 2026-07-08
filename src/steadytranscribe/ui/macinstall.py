"""macOS: «установка» приложения = перенос бандла в папку «Программы».

Если SteadyVoice запущен из DMG, Загрузок или через карантинную транслокацию
(путь /private/var/.../AppTranslocation/ — случайный и только для чтения),
автообновление невозможно. Предлагаем один раз скопировать приложение в
/Applications (или ~/Applications) и перезапускаемся оттуда — дальше всё
обновляется само, как на Windows.
"""
import logging
import os
import subprocess


def _current_bundle() -> str | None:
    from .updater import bundle_path
    return bundle_path()


def _needs_move(bundle: str) -> bool:
    if "/AppTranslocation/" in bundle:
        return True
    parent = os.path.dirname(bundle)
    good = (os.path.realpath("/Applications"),
            os.path.realpath(os.path.expanduser("~/Applications")))
    return os.path.realpath(parent) not in good


def _target_dir() -> str:
    apps = "/Applications"
    if os.access(apps, os.W_OK):
        return apps
    user_apps = os.path.expanduser("~/Applications")
    os.makedirs(user_apps, exist_ok=True)
    return user_apps


def offer_move_to_applications() -> bool:
    """True — приложение скопировано в «Программы» и запущено оттуда:
    вызывающий должен немедленно выйти. False — работаем где есть."""
    bundle = _current_bundle()
    if bundle is None or not _needs_move(bundle):
        return False
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(QMessageBox.Question, "SteadyVoice",
                      "Перенести SteadyVoice в папку «Программы»?\n\n"
                      "Так приложение будет всегда под рукой и сможет "
                      "обновляться автоматически.")
    move_btn = box.addButton("Перенести и открыть", QMessageBox.AcceptRole)
    box.addButton("Не сейчас", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is not move_btn:
        return False
    target = os.path.join(_target_dir(), "SteadyVoice.app")
    try:
        if os.path.exists(target):
            subprocess.run(["/bin/rm", "-rf", target], check=True, timeout=120)
        # ditto сохраняет права, симлинки и подпись бандла
        subprocess.run(["/usr/bin/ditto", bundle, target], check=True, timeout=600)
        subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", target],
                       capture_output=True, timeout=60)
        subprocess.Popen(["/usr/bin/open", target])
        logging.info("приложение перенесено в %s и перезапущено", target)
        return True
    except Exception as e:  # noqa: BLE001
        logging.error("не удалось перенести в «Программы»: %s", e)
        QMessageBox.warning(None, "SteadyVoice",
                            "Не получилось перенести автоматически. "
                            "Перетащите SteadyVoice в папку «Программы» вручную.")
        return False
