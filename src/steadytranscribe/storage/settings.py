"""Настройки приложения: JSON в %APPDATA%/SteadyTranscribe/settings.json."""
import json
import os
import sys

# Версия схемы настроек. ЗАДЕЛ НА БУДУЩЕЕ: любое переименование/изменение смысла
# ключа — новая версия + шаг в _MIGRATIONS. Тогда обновления программы никогда
# не «ломают» старые настройки пользователей и не требуют переустановки.
SETTINGS_VERSION = 1

DEFAULTS = {
    "settings_version": SETTINGS_VERSION,
    "model": "large-v3-turbo",    # по умолчанию максимальное качество (как согласовано)
    "language": "auto",           # auto | ru | en | ...
    "device": "auto",             # auto | cpu | cuda
    "initial_prompt": "",         # словарь-подсказка: имена, термины (напр. SteadyControl)
    "history_limit": 50,          # как maxEntries в оригинале
    "hf_mirror": "auto",          # auto: huggingface.co → fallback hf-mirror.com
    "onboarded": False,           # мини-обучение при первом запуске показано
    "auto_update": True,          # тихо качать обновления и ставить при простое/выходе/запуске
    "last_version": "",           # версия прошлого запуска — для уведомления «обновлено до X»
}

# Миграции старых настроек: {из_версии: функция(data) -> data}.
# Пример на будущее: 1 → 2 переименовать ключ — _MIGRATIONS[1] = lambda d: {...}
_MIGRATIONS: dict = {}


def _migrate(data: dict) -> dict:
    v = int(data.get("settings_version", 1) or 1)
    while v < SETTINGS_VERSION:
        step = _MIGRATIONS.get(v)
        if step is None:
            break
        data = step(data)
        v += 1
        data["settings_version"] = v
    return data

MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3-turbo"]
MODEL_LABELS = {
    "tiny": "Tiny — самая быстрая, черновое качество (~75 МБ)",
    "base": "Base — быстрая (~145 МБ)",
    "small": "Small — баланс скорости и качества (~480 МБ)",
    "medium": "Medium — высокое качество, медленнее (~1.5 ГБ)",
    "large-v3-turbo": "Large v3 Turbo — максимальное качество (~1.6 ГБ, рекомендуется)",
}
LANGUAGE_CHOICES = [("auto", "Автоопределение"), ("ru", "Русский"), ("en", "English"),
                    ("uk", "Українська"), ("de", "Deutsch"), ("es", "Español"), ("fr", "Français")]


def app_data_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/Library/Application Support")
    path = os.path.join(base, "SteadyTranscribe")
    os.makedirs(path, exist_ok=True)
    return path


def _settings_path() -> str:
    return os.path.join(app_data_dir(), "settings.json")


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            stored = json.load(f)
        stored = _migrate(stored)
        data.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    # CUDA больше не поддерживается (сборка CPU-only) — переносим на процессор
    if data.get("device") in ("cuda", "auto"):
        data["device"] = "cpu"
    return data


def save(settings: dict) -> None:
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump({k: settings[k] for k in DEFAULTS if k in settings}, f,
                  ensure_ascii=False, indent=2)


def reset() -> None:
    """Сброс настроек к значениям по умолчанию (устраняет битые старые настройки)."""
    try:
        os.remove(_settings_path())
    except OSError:
        pass
