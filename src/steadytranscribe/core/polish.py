"""Локальная «полировка» расшифровки: орфография, пунктуация, связность —
БЕЗ изменения смысла и БЕЗ отправки текста куда-либо.

Работает через локальный llama-server (OpenAI-совместимый HTTP на 127.0.0.1).
На маке у пользователя он уже поднят для диктовки (модель qwen3-4b). Текст
режем на куски (по репликам). Метку говорящего («Собеседник N:», «Имя:»)
ОТРЕЗАЕМ перед отправкой в модель и возвращаем дословно — так полировка не
переписывает и не теряет метки, а привязка голоса по ним (клипы ▶, отпечатки)
не рвётся.

ЗАЩИТА ОТ ВЫДУМОК (guardrails): если модель раздула/ужала кусок больше чем
на 35% по словам — берём исходный кусок. Так «причёсывание» не превращается
в пересказ и не теряет смысл.
"""
import json
import re
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8737"
_SYSTEM = (
    "Ты — редактор-корректор русской речи. Тебе дают фрагмент авто-расшифровки "
    "разговора. Исправь орфографию, пунктуацию и расставь заглавные буквы. "
    "Убери слова-паразиты и оговорки (э, ну, как бы, вот) ТОЛЬКО если это не "
    "меняет смысл. НЕ добавляй ничего от себя, НЕ пересказывай, НЕ сокращай "
    "содержание, сохрани все факты и имена. Если строка начинается с «Имя:» — "
    "оставь эту метку в начале без изменений. Верни ТОЛЬКО исправленный текст, "
    "без пояснений."
)


def is_available(url: str = DEFAULT_URL, timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout) as r:
            return json.load(r).get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def _wc(s: str) -> int:
    return len(s.split())


_LABEL_RE = re.compile(r"^([^:\n]{1,40}:[ \t]+)")


def _split_label(chunk: str):
    """Отделить метку говорящего в начале куска → (метка, тело).

    Метка («Собеседник 2: », «Антон: ») дальше в модель НЕ уходит и
    возвращается в результат дословно: полировка не может её переписать
    или потерять, а привязка клипов голоса (по метке) остаётся целой.
    Если метки нет — метка пустая, тело = весь кусок.
    """
    m = _LABEL_RE.match(chunk)
    if m:
        return chunk[:m.end()], chunk[m.end():]
    return "", chunk


def _chat(text: str, url: str, timeout: int) -> str:
    body = json.dumps({
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": text}],
        "temperature": 0.2, "max_tokens": 2048,
        # non-thinking: не нужны рассуждения, только результат
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    out = data["choices"][0]["message"]["content"].strip()
    # снять возможный <think>…</think>, если модель всё же порассуждала
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
    return out


def _para_chunks(para: str, max_words: int = 220):
    """Куски ОДНОГО абзаца (реплики): целиком или по предложениям, если крупный."""
    if _wc(para) <= max_words:
        yield para
        return
    buf, n = [], 0
    for sent in re.split(r"(?<=[.!?…])\s+", para):
        if n + _wc(sent) > max_words and buf:
            yield " ".join(buf)
            buf, n = [], 0
        buf.append(sent)
        n += _wc(sent)
    if buf:
        yield " ".join(buf)


def polish(text: str, url: str = DEFAULT_URL, timeout: int = 120,
           progress_cb=None, cancel_check=None) -> str:
    """Причесать весь текст. Возвращает исправленный текст (метки реплик целы).
    При недоступности сервера/ошибке куска — возвращает исходный кусок.

    Собираем результат ПОЗИЦИОННО (абзац за абзацем), а не глобальным replace:
    иначе короткий кусок («Да») нашёлся бы подстрокой в другом слове, одинаковые
    куски схлопывались бы, а кусок с изменённым пробелом молча терялся."""
    paras = text.split("\n\n")
    chunked = [list(_para_chunks(p)) for p in paras]
    total = sum(len(c) for c in chunked) or 1
    done = 0
    out_paras = []
    for chunks in chunked:
        fixed_chunks = []
        for ch in chunks:
            if cancel_check and cancel_check():
                raise InterruptedError("Отменено пользователем.")
            label, body = _split_label(ch)
            if not body.strip():
                fixed_chunks.append(ch)          # только метка/пусто — не трогаем
            else:
                try:
                    fixed_body = _chat(body, url, timeout)
                    # guardrail: сильное изменение длины → берём исходное тело
                    if not fixed_body or not (0.65 <= _wc(fixed_body) / max(_wc(body), 1) <= 1.35):
                        fixed_body = body
                except Exception:  # noqa: BLE001
                    fixed_body = body
                fixed_chunks.append(label + fixed_body)   # метку возвращаем дословно
            done += 1
            if progress_cb:
                progress_cb(done, total)
        out_paras.append(" ".join(fixed_chunks))
    return "\n\n".join(out_paras)
