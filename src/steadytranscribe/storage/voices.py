"""База «отпечатков голоса» — узнаём собеседников между записями (как в Plaud).

Отпечаток = усреднённый L2-нормированный вектор (эмбеддинг CAM++, ~192 числа),
хранится локально. Когда пользователь подтверждает имя («это Олег»), мы
запоминаем голос; в следующей записи предлагаем имя сами.

ЧЕГО не делаем: не храним аудио и текст — только числовой отпечаток.
Файл: voices.json в каталоге данных приложения.

Пороги узнавания (косинус):
  ≥ HIGH  — уверенно, авто-имя;
  ≥ LOW   — гипотеза «похоже на X?», показываем с подтверждением;
  < LOW   — «Собеседник N».
ВАЖНО про пороги: текущий эмбеддер CAM++ на русской речи различает голоса
средне — замер на реальной встрече дал сходство РАЗНЫХ людей 0.47–0.63.
Поэтому пороги подняты консервативно (0.82/0.72): лучше не узнать, чем
подставить чужое имя. Надёжное узнавание между встречами включится с
проф-моделью (лучший эмбеддер, см. дорожную карту) — тогда пороги снизим.
Модель отпечатка хранится рядом с вектором: при смене эмбеддера база
несовместима и её надо пересобирать (сравниваем только векторы своей модели).
"""
import json
import os
import time

from .settings import app_data_dir

HIGH = 0.82
LOW = 0.72
_MODEL = "campp"        # текущий эмбеддер (см. core/diarize.py)


def _path() -> str:
    return os.path.join(app_data_dir(), "voices.json")


def _load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("voices"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "model": _MODEL, "voices": []}


def _save(data: dict) -> None:
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _norm(vec: list) -> list:
    import math
    s = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / s for x in vec]


def _cos(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b))    # оба уже L2-нормированы


def all_names() -> list:
    return [v["name"] for v in _load().get("voices", [])]


def enroll(name: str, embedding: list) -> None:
    """Запомнить/дополнить отпечаток голоса. Несколько образцов усредняются —
    отпечаток крепнет с каждой подтверждённой записью (устойчивее к простуде/
    микрофону). База несовместимой модели сбрасывается (эмбеддер сменился)."""
    name = name.strip()
    if not name or not embedding:
        return
    data = _load()
    if data.get("model") != _MODEL:
        data = {"version": 1, "model": _MODEL, "voices": []}
    emb = _norm(list(embedding))
    for v in data["voices"]:
        if v["name"].lower() == name.lower():
            n = v.get("n", 1)
            # скользящее среднее центроида (потом ре-нормируем)
            v["vec"] = _norm([(a * n + b) / (n + 1) for a, b in zip(v["vec"], emb)])
            v["n"] = n + 1
            v["updated"] = int(time.time())
            _save(data)
            return
    data["voices"].append({"name": name, "vec": emb, "n": 1,
                           "updated": int(time.time())})
    _save(data)


def identify(embeddings: dict) -> dict:
    """Сопоставить кластеры новой записи с известными голосами.

    embeddings: {ключ_кластера: вектор-центроид}.
    Возвращает {ключ_кластера: {"name", "score", "confident"}} только для
    кластеров, похожих на кого-то из базы (жадное 1:1 — одно имя не уходит
    двум кластерам). confident=True при score≥HIGH."""
    data = _load()
    if data.get("model") != _MODEL:
        return {}
    known = data.get("voices", [])
    if not known:
        return {}
    # все пары (score, ключ, имя), затем жадно разбираем по убыванию
    pairs = []
    for key, vec in embeddings.items():
        nv = _norm(list(vec))
        for v in known:
            pairs.append((_cos(nv, v["vec"]), key, v["name"]))
    pairs.sort(reverse=True)
    out: dict = {}
    used_names: set = set()
    for score, key, name in pairs:
        if score < LOW or key in out or name in used_names:
            continue
        out[key] = {"name": name, "score": round(score, 3), "confident": score >= HIGH}
        used_names.add(name)
    return out


def forget(name: str) -> None:
    data = _load()
    data["voices"] = [v for v in data["voices"] if v["name"].lower() != name.strip().lower()]
    _save(data)


def rename(old: str, new: str) -> None:
    """Переименовать голос. Если голос с именем new уже есть — СЛИТЬ отпечатки
    (это один человек, названный по-разному): усредняем векторы по числу
    образцов, суммируем n. Так «Олег» + «Олег Коркин» → один голос."""
    old, new = old.strip(), new.strip()
    if not new or old == new:                   # только точное совпадение — no-op;
        return                                  # регистровую правку («иван»→«Иван») пропускаем дальше
    data = _load()
    src = next((v for v in data["voices"] if v["name"].lower() == old.lower()), None)
    if src is None:
        return
    dst = next((v for v in data["voices"]
                if v["name"].lower() == new.lower() and v is not src), None)
    if dst is None:
        src["name"] = new                       # просто переименование
    else:
        na, nb = dst.get("n", 1), src.get("n", 1)
        dst["vec"] = _norm([(a * na + b * nb) / (na + nb)
                            for a, b in zip(dst["vec"], src["vec"])])
        dst["n"] = na + nb
        dst["updated"] = int(time.time())
        data["voices"] = [v for v in data["voices"] if v is not src]
    _save(data)
