"""Автообновление через GitHub Releases — как в современных программах (Chrome).

Схема «скачал → отложил → применил в удобный момент»:
1. Проверка при запуске (и периодически). Новая версия ТИХО скачивается в фоне
   в папку updates и «ложится на полку» (staged) — переживает перезапуск и крах.
2. Установка — только когда пользователю не мешает:
   • при ПРОСТОЕ (окно неактивно ≥10 мин, ничего не обрабатывается) — тихо
     ставится и возвращается свёрнутой, не крадя фокус;
   • при ВЫХОДЕ — тихо ставится без перезапуска (/NORELAUNCH);
   • при СЛЕДУЮЩЕМ ЗАПУСКЕ — если отложенное обновление ещё не применилось.
3. Во время расшифровки/разделения установка никогда не запускается.
Защита от цикла: после 2 неудачных попыток отложенное обновление сбрасывается.
"""
import json
import os
import subprocess
import sys
import urllib.request

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout,
)

from ..storage.settings import app_data_dir

CURRENT_VERSION = "1.5.13"
REPO = "korkinolegip/steadytranscribe"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

# Файловый домен GitHub (objects.githubusercontent.com) периодически блокируется
# в РФ — сам API при этом работает. Качаем по цепочке: напрямую → через зеркала.
# Подлинность файла с зеркала гарантирует SHA256 из описания релиза (см. ниже).
_DOWNLOAD_MIRRORS = [
    "",                              # GitHub напрямую
    "https://mirror.ghproxy.com/",
    "https://ghproxy.net/",
    "https://gh-proxy.com/",
]


def _parse_version(tag: str) -> tuple:
    nums = tag.lstrip("vV").split(".")
    try:
        return tuple(int(n) for n in nums[:3])
    except ValueError:
        return (0, 0, 0)


# ---------- «полка» отложенных обновлений (staged) ----------

def _updates_dir() -> str:
    path = os.path.join(app_data_dir(), "updates")
    os.makedirs(path, exist_ok=True)
    return path


def _pending_path() -> str:
    return os.path.join(_updates_dir(), "pending.json")


def load_pending() -> dict | None:
    """{"version", "path", "attempts"} или None."""
    try:
        with open(_pending_path(), encoding="utf-8") as f:
            p = json.load(f)
        if p.get("version") and p.get("path"):
            return p
    except (OSError, ValueError):
        pass
    return None


def save_pending(version: str, installer_path: str) -> None:
    with open(_pending_path(), "w", encoding="utf-8") as f:
        json.dump({"version": version, "path": installer_path, "attempts": 0}, f)


def clear_pending() -> None:
    """Убрать отложенное обновление вместе со скачанными установщиками."""
    try:
        for name in os.listdir(_updates_dir()):
            try:
                os.remove(os.path.join(_updates_dir(), name))
            except OSError:
                pass
    except OSError:
        pass


# установщик уже запущен из этого сеанса — защита от ДВОЙНОГО запуска
# (двойной запуск = два конфликтующих установщика = сорванное обновление)
_install_launched = False


def install_in_progress() -> bool:
    return _install_launched


def run_installer_silent(installer_path: str, relaunch: bool = True,
                         visible: bool = False) -> None:
    """Тихая установка. relaunch=False (/NORELAUNCH) — при выходе: пользователь
    закрыл программу, не открываем её заново. visible=True (/SILENT вместо
    /VERYSILENT) — показать узкое окно прогресса установки (для ручного
    «Обновить сейчас», чтобы было видно, что установка идёт)."""
    global _install_launched
    import logging
    mode = "/SILENT" if visible else "/VERYSILENT"
    args = [installer_path, mode, "/SUPPRESSMSGBOXES", "/NORESTART",
            "/LOG=" + os.path.join(app_data_dir(), "install.log")]
    if not relaunch:
        args.append("/NORELAUNCH")
    logging.info("update: запуск установщика %s", args)
    subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    _install_launched = True


def install_pending(relaunch: bool) -> bool:
    """Запустить отложенное обновление, посчитав попытку (защита от цикла)."""
    import logging
    p = load_pending()
    if not p or not os.path.exists(p["path"]):
        logging.warning("update: установка не запущена — файл обновления отсутствует "
                        "(антивирус удалил?): %s", p)
        return False
    p["attempts"] = int(p.get("attempts", 0)) + 1
    try:
        with open(_pending_path(), "w", encoding="utf-8") as f:
            json.dump(p, f)
    except OSError:
        pass
    try:
        run_installer_silent(p["path"], relaunch=relaunch)
        logging.info("update: установщик %s запущен (relaunch=%s, попытка %s)",
                     p["version"], relaunch, p["attempts"])
        return True
    except Exception as e:  # noqa: BLE001
        logging.error("update: не удалось запустить установщик: %s", e)
        return False


def apply_staged_at_launch() -> bool:
    """Вызывается в самом начале запуска. Если с прошлого раза отложено более
    новое обновление — ставим его сейчас (установщик перезапустит программу).
    True — установка пошла, вызывающий должен немедленно выйти."""
    import logging
    p = load_pending()
    if not p:
        clear_pending()   # подчистить осиротевшие файлы установщиков (место на диске)
        return False
    stale = (_parse_version(p["version"]) <= _parse_version(CURRENT_VERSION)
             or not os.path.exists(p["path"]))
    if stale or int(p.get("attempts", 0)) >= 2:
        logging.info("update: отложенное %s сброшено (stale=%s, попыток=%s)",
                     p.get("version"), stale, p.get("attempts"))
        if not stale:
            # две НЕУДАЧНЫЕ попытки — не уходим в тихий цикл: пометим, чтобы
            # показать пользователю видимый диалог обновления с текстом ошибки
            mark_update_failed()
        clear_pending()   # уже применилось / файла нет / две неудачные попытки
        return False
    logging.info("update: применяю отложенное %s при запуске", p.get("version"))
    return install_pending(relaunch=True)


# маркер «автообновление дважды не удалось» → показать видимый диалог
def _fail_flag_path() -> str:
    return os.path.join(app_data_dir(), "update_failed")


def mark_update_failed() -> None:
    try:
        with open(_fail_flag_path(), "w", encoding="utf-8") as f:
            f.write("1")
    except OSError:
        pass


def consume_update_failed() -> bool:
    if os.path.exists(_fail_flag_path()):
        try:
            os.remove(_fail_flag_path())
        except OSError:
            pass
        return True
    return False


# маркер «после обновления на простое вернуться свёрнутым, не красть фокус»
def _marker_path() -> str:
    return os.path.join(app_data_dir(), "restart_minimized")


def mark_restart_minimized() -> None:
    try:
        with open(_marker_path(), "w", encoding="utf-8") as f:
            f.write("1")
    except OSError:
        pass


def consume_restart_marker() -> bool:
    if os.path.exists(_marker_path()):
        try:
            os.remove(_marker_path())
        except OSError:
            pass
        return True
    return False


class UpdateChecker(QThread):
    """Проверяет новую версию. Отдаёт версию, URL лёгкого установщика и его SHA256
    (из описания релиза — для проверки файла, скачанного через зеркало)."""
    update_available = Signal(str, str, str)

    def run(self):
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "SteadyTranscribe"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
            tag = data.get("tag_name", "")
            if _parse_version(tag) > _parse_version(CURRENT_VERSION):
                # ЗАДЕЛ НА БУДУЩЕЕ: сначала строгое каноничное имя лёгкого
                # установщика (это имя — контракт, менять нельзя), затем
                # мягкие запасные варианты — если имена в релизе поменяются.
                import re
                exes = [a for a in data.get("assets", []) if a["name"].endswith(".exe")]
                strict = [a for a in exes
                          if re.fullmatch(r"SteadyTranscribe-Setup-[\d.]+\.exe", a["name"])]
                light = [a for a in exes if "with-model" not in a["name"].lower()]
                pick = strict or light or exes
                url = pick[0]["browser_download_url"] if pick else RELEASES_PAGE
                m = re.search(r"sha256:\s*([0-9a-fA-F]{64})", data.get("body") or "")
                sha = m.group(1).lower() if m else ""
                self.update_available.emit(tag.lstrip("vV"), url, sha)
        except Exception:  # noqa: BLE001
            pass


class InstallerDownloader(QThread):
    """Скачивание установщика: GitHub напрямую → зеркала (файловый домен GitHub
    блокируется в РФ). Файл с зеркала принимается только при совпадении SHA256."""
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, sha256: str = "", parent=None):
        super().__init__(parent)
        self.url = url
        self.sha256 = (sha256 or "").lower()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _download(self, url: str, dest: str) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "SteadyTranscribe"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            got = 0
            with open(dest, "wb") as f:
                while True:
                    if self._cancel:
                        raise InterruptedError
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
        # оборванное скачивание не должно попасть в установку
        if total and got != total:
            raise OSError(f"скачано {got} из {total} байт — обрыв сети")

    def _verify(self, dest: str, from_mirror: bool) -> None:
        """SHA256 против отпечатка из описания релиза. Для зеркала — обязательно
        (иначе зеркалу пришлось бы верить на слово), напрямую — если отпечаток есть."""
        if not self.sha256:
            if from_mirror:
                raise OSError("нет отпечатка SHA256 — файлу с зеркала нельзя доверять")
            return
        import hashlib
        h = hashlib.sha256()
        with open(dest, "rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        if h.hexdigest() != self.sha256:
            raise OSError("файл повреждён или подменён (SHA256 не совпал)")

    def run(self):
        import logging
        dest = os.path.join(_updates_dir(), "SteadyTranscribe-Update.exe")
        last_err = None
        for prefix in _DOWNLOAD_MIRRORS:
            url = prefix + self.url if prefix else self.url
            try:
                self._download(url, dest)
                self._verify(dest, from_mirror=bool(prefix))
                logging.info("update: скачано и проверено (%s)",
                             prefix or "GitHub напрямую")
                self.done.emit(dest)
                return
            except InterruptedError:
                self.failed.emit("Обновление отменено.")
                return
            except Exception as e:  # noqa: BLE001
                logging.error("update: источник «%s» не сработал: %s",
                              prefix or "прямой", e)
                last_err = e
        self.failed.emit(f"Не удалось скачать обновление (все источники): {last_err}")


class UpdateDialog(QDialog):
    """Скачивает и тихо устанавливает обновление — всё внутри программы."""

    def __init__(self, version: str, url: str, sha256: str = "", parent=None):
        super().__init__(parent)
        self.url = url
        self.sha256 = sha256
        self.version = version
        self.setWindowTitle("Обновление SteadyVoice")
        self.setMinimumWidth(460)
        self.downloader = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        self.label = QLabel(
            f"Доступна версия <b>{version}</b> (у вас {CURRENT_VERSION}).<br>"
            "«Обновить сейчас» — займёт пару минут: программа скачает, установит "
            "и перезапустится сама.<br>"
            "«Позже» — обновление тихо скачается в фоне и установится само "
            "при закрытии программы.")
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.hide()
        self.status = QLabel()
        self.status.setObjectName("hint")
        lay.addWidget(self.progress)
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.update_btn = QPushButton("⬇ Обновить сейчас")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._start)
        self.later_btn = QPushButton("Позже")
        self.later_btn.clicked.connect(self.reject)
        btns.addWidget(self.update_btn)
        btns.addWidget(self.later_btn)
        lay.addLayout(btns)

    def _start(self):
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        # уже скачано в фоне (лежит «на полке»)? — ставим сразу, не качаем заново
        p = load_pending()
        if p and p.get("version") == self.version and os.path.exists(p["path"]):
            self.status.setText("Обновление уже скачано — устанавливаю…")
            self._on_done(p["path"])
            return
        self.progress.show()
        self.status.setText("Скачивание обновления…")
        self.downloader = InstallerDownloader(self.url, self.sha256, self)
        self.downloader.progress.connect(self._on_progress)
        self.downloader.done.connect(self._on_done)
        self.downloader.failed.connect(self._on_failed)
        self.downloader.start()

    def _on_progress(self, done: int, total: int):
        if total:
            self.progress.setMaximum(100)
            self.progress.setValue(int(done / total * 100))
            self.progress.setFormat(f"{done // 1048576} / {total // 1048576} МБ")
        else:
            self.progress.setMaximum(0)

    def _on_done(self, installer_path: str):
        self.status.setText("Установка обновления… Появится окно прогресса, "
                            "после установки программа откроется сама.")
        # запоминаем «на полке»: если установка сорвётся — повторная попытка
        # пройдёт уже без скачивания
        save_pending(self.version, installer_path)
        try:
            # visible=True: узкое окно прогресса установки (Inno /SILENT) —
            # видно, что установка идёт; затем программа перезапустится сама
            run_installer_silent(installer_path, relaunch=True, visible=True)
        except Exception as e:  # noqa: BLE001
            self._on_failed(f"Не удалось запустить установку: {e}")
            return
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_failed(self, msg: str):
        self.update_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        self.progress.hide()
        self.status.setText(f"⚠️ {msg}")


def check_async(parent) -> UpdateChecker:
    """Ручная/явная проверка: показывает диалог с кнопкой «Обновить сейчас»."""
    checker = UpdateChecker(parent)
    checker.update_available.connect(
        lambda version, url, sha: UpdateDialog(version, url, sha, parent).exec())
    checker.start()
    return checker
