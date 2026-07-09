"""Разделение по собеседникам (локально, sherpa-onnx).

Модели маленькие (~44 МБ суммарно) и поставляются вместе с приложением —
интернет для диаризации не нужен.

Схема (переработана 2026-07-08 после сравнения с Plaud на реальной встрече):
1. sherpa-onnx ищет ГРАНИЦЫ речи (сегментация pyannote) — это она делает хорошо;
   её собственную кластеризацию «кто есть кто» игнорируем: FastClustering
   на встречах ошибалась — 73.8% слов у правильного говорящего против эталона.
2. Речь режем на ОКНА по 1.5 с (шаг 0.75) и считаем отпечаток голоса (CAM++)
   каждого окна — мелкая грануляция вместо целых сегментов.
3. Окна кластеризуем сами (k-means по нормированным эмбеддингам; число голосов
   от пользователя, либо авто по силуэту) + медианное сглаживание по времени.
Итог на той же встрече: 90.9% и структура реплик как у эталона (76 против 75
переключений). Модели те же, скорость почти та же (+15 с на 14-минутный файл).
"""
import os
import sys
from dataclasses import dataclass

from .transcriber import Word


@dataclass
class SpeakerTurn:
    speaker: int   # 0-based
    start: float
    end: float


# окна отпечатков голоса
_WIN = 1.5          # длина окна, с
_HOP = 0.75         # шаг, с
_MIN_WIN = 0.6      # окно короче — пропускаем (отпечаток шумный)
_SMOOTH_RADIUS = 2  # медианное сглаживание меток: ±2 окна


def _models_dir() -> str:
    from .resources import resource
    if getattr(sys, "frozen", False):
        return resource("diarization")
    return resource("assets", "diarization")


def is_available() -> bool:
    d = _models_dir()
    return (os.path.exists(os.path.join(d, "segmentation.onnx"))
            and os.path.exists(os.path.join(d, "embedding.onnx")))


def _kmeans(X, k: int, iters: int = 80, seed: int = 7):
    """k-means с k-means++ инициализацией (numpy; детерминирован по seed)."""
    import numpy as np
    rng = np.random.RandomState(seed)
    cents = [X[rng.randint(len(X))]]
    for _ in range(k - 1):
        d2 = np.min([np.sum((X - c) ** 2, axis=1) for c in cents], axis=0)
        cents.append(X[rng.choice(len(X), p=d2 / (d2.sum() + 1e-12))])
    C = np.stack(cents)
    lab = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        newC = np.stack([X[lab == j].mean(0) if np.any(lab == j) else C[j]
                         for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return lab


def _silhouette(X, lab) -> float:
    """Средний силуэт (косинусная дистанция) — для авто-выбора числа голосов."""
    import numpy as np
    D = 1.0 - X @ X.T
    ks = np.unique(lab)
    if len(ks) < 2:
        return 0.0
    s = []
    for i in range(len(X)):
        same = lab == lab[i]
        same[i] = False
        if not np.any(same):
            continue
        a = D[i, same].mean()
        b = min(D[i, lab == kk].mean() for kk in ks if kk != lab[i])
        s.append((b - a) / max(a, b, 1e-9))
    return float(np.mean(s)) if s else 0.0


def diarize(wav_path: str, num_speakers: int, status_cb, cancel_check) -> list[SpeakerTurn]:
    """num_speakers: 0 = авто. Возвращает реплики по времени."""
    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    status_cb("Определение собеседников…", 0.25)
    audio, sr = sf.read(wav_path, dtype="float32")
    d = _models_dir()
    nthreads = max(os.cpu_count() or 4, 2)  # все ядра — ускоряет медленную диаризацию

    # --- этап 1: границы речи (кластеры sherpa игнорируем — см. докстринг) ---
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=os.path.join(d, "segmentation.onnx")),
            num_threads=nthreads),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=os.path.join(d, "embedding.onnx"), num_threads=nthreads),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=0.6),
        # короткие «да»/«угу» не должны склеиваться с чужой репликой
        min_duration_on=0.2, min_duration_off=0.1)
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)

    def progress(processed, total):  # noqa: ANN001
        if cancel_check():
            return 1  # ненулевое значение прерывает обработку
        frac = processed / max(total, 1)
        status_cb(f"Определение собеседников… {int(frac * 70)}%", 0.25 + frac * 0.14)
        return 0

    segs = diarizer.process(audio, callback=progress).sort_by_start_time()
    if cancel_check():
        raise InterruptedError("Отменено пользователем.")
    if not segs:
        return [], {}

    # --- этап 2: отпечатки голоса окон 1.5 с внутри речи ---
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=os.path.join(d, "embedding.onnx"), num_threads=nthreads))
    wins: list[tuple[float, float]] = []
    for s in segs:
        t = s.start
        while t < s.end:
            w_end = min(t + _WIN, s.end)
            if w_end - t >= _MIN_WIN:
                wins.append((t, w_end))
            if w_end >= s.end:
                break
            t += _HOP
    if not wins:
        return [SpeakerTurn(0, s.start, s.end) for s in segs], {}
    embs = []
    for i, (t0, t1) in enumerate(wins):
        if cancel_check():
            raise InterruptedError("Отменено пользователем.")
        stream = extractor.create_stream()
        stream.accept_waveform(sr, audio[int(t0 * sr):int(t1 * sr)])
        stream.input_finished()
        e = np.array(extractor.compute(stream), dtype=np.float32)
        embs.append(e / (np.linalg.norm(e) + 1e-9))
        if i % 40 == 0:
            frac = i / len(wins)
            status_cb(f"Определение собеседников… {70 + int(frac * 25)}%",
                      0.39 + frac * 0.05)
    X = np.stack(embs)

    # --- этап 3: кластеризация окон + сглаживание ---
    status_cb("Определение собеседников… 95%", 0.44)
    max_k = min(6, len(wins))
    if num_speakers > 0:
        k = min(num_speakers, len(wins))
        lab = _kmeans(X, k)
    else:
        # авто: лучший силуэт по k=2..6; ниже порога — один говорящий.
        # Порог откалиброван на реальных данных: монолог даёт силуэт ≤0.10,
        # живая встреча трёх человек — ≥0.24 (см. experiments-diar/)
        best_s, best_lab = 0.15, np.zeros(len(wins), dtype=int)
        for k in range(2, max_k + 1):
            lab_k = _kmeans(X, k)
            s = _silhouette(X, lab_k)
            if s > best_s:
                best_s, best_lab = s, lab_k
        lab = best_lab

    # медианное сглаживание по времени — убирает мигание меток на стыках
    order = np.argsort([w[0] for w in wins])
    lab_sorted = lab[order]
    smoothed = lab_sorted.copy()
    for i in range(len(lab_sorted)):
        lo, hi = max(0, i - _SMOOTH_RADIUS), min(len(lab_sorted), i + _SMOOTH_RADIUS + 1)
        vals, cnt = np.unique(lab_sorted[lo:hi], return_counts=True)
        smoothed[i] = vals[np.argmax(cnt)]

    # центроид каждого голоса (для запоминания/узнавания между записями):
    # среднее нормированных эмбеддингов его окон, снова L2-нормируем
    centroids: dict = {}
    for spk in set(int(x) for x in smoothed):
        idx = [order[p] for p in range(len(order)) if int(smoothed[p]) == spk]
        if idx:
            c = X[idx].mean(axis=0)
            c = c / (np.linalg.norm(c) + 1e-9)
            centroids[spk] = [round(float(x), 6) for x in c]

    # окна (с перекрытием) → непрерывные реплики: граница — середина перекрытия
    turns: list[SpeakerTurn] = []
    for pos in range(len(order)):
        i = order[pos]
        spk = int(smoothed[pos])
        st, en = wins[i]
        if turns and turns[-1].speaker == spk and st <= turns[-1].end + 0.01:
            turns[-1].end = max(turns[-1].end, en)
        elif turns and st < turns[-1].end:   # смена голоса внутри перекрытия
            mid = (st + turns[-1].end) / 2
            turns[-1].end = mid
            turns.append(SpeakerTurn(spk, mid, en))
        else:
            turns.append(SpeakerTurn(spk, st, en))
    return turns, centroids


def _speaker_at(t: float, turns: list[SpeakerTurn]) -> int:
    """Кто говорит в момент t (по максимальному перекрытию точки со реплик)."""
    best, best_overlap = 0, -1.0
    for turn in turns:
        if turn.start <= t <= turn.end:
            return turn.speaker
        # ближайшая по расстоянию, если точка вне всех реплик
        dist = min(abs(t - turn.start), abs(t - turn.end))
        if -dist > best_overlap:
            best_overlap = -dist
            best = turn.speaker
    return best


_SENT_END = (".", "!", "?", "…")


def _fix_boundaries(assigned: list[int], words: list[Word]) -> list[int]:
    """Возвращает «прилипшее» продолжение фразы прежнему говорящему.

    Оконная кластеризация + дрейф таймкодов whisper дают типичный артефакт:
    короткий хвост-продолжение чужого предложения улетает к СЛЕДУЮЩЕМУ
    говорящему («…я не знаю, как это | происходит.» — «происходит» уезжает
    к соседу). Двигаем такой островок назад ТОЛЬКО при совпадении трёх общих
    признаков (замерено на реальной встрече vs Plaud: +7 верных / −0 регрессий,
    точность 91.2% против 90.1% у прежней версии и 90.8% вообще без починки):
      1. островок короткий (≤3 слов) и сам завершает предложение (.!?…);
      2. реплика ПРЕДЫДУЩЕГО говорящего оборвана (без .!?… в конце) — мысль
         ещё не закончена, значит островок её продолжает;
      3. плотное примыкание (пауза между словами ≤0.4 с) — тот же голос, а не
         новая короткая реплика (у настоящих «да/угу» пауза до них больше).

    Прежняя версия переносила обрывки в ОБЕ стороны по границам предложений и
    в среднем СНИЖАЛА точность (портила больше слов, чем чинила). Заменена на
    это направленное безрегрессионное правило (стратегия continuation_merge,
    выбрана из 6 после аудита на переобучение — опирается только на общие
    признаки: паузы, пунктуацию, длину, без привязки к конкретным словам).
    """
    out = list(assigned)
    n = len(words)
    if n == 0:
        return out
    # границы прогонов подряд идущих слов одного говорящего (по ИСХОДНЫМ меткам)
    starts = [0] + [i for i in range(1, n) if assigned[i] != assigned[i - 1]] + [n]
    for gi in range(1, len(starts) - 1):
        g_start = starts[gi]
        g_end = starts[gi + 1] - 1
        if g_end - g_start + 1 > 3:                       # только короткий островок
            continue
        if not words[g_end].text.strip().endswith(_SENT_END):
            continue                                       # островок должен завершать предложение
        if words[g_start - 1].text.strip().endswith(_SENT_END):
            continue                                       # предыдущая мысль уже закончена
        if words[g_start].start - words[g_start - 1].end > 0.4:
            continue                                       # была реальная пауза → чужой голос
        prev_spk = assigned[g_start - 1]
        for i in range(g_start, g_end + 1):
            out[i] = prev_spk
    return out


def build_dialogue(words: list[Word], turns: list[SpeakerTurn]) -> str:
    """Собирает диалог по СЛОВАМ: каждое слово относим к говорящему в его момент.
    Так короткие реплики-вставки («да», «угу») попадают правильному собеседнику.
    Прилипшие хвосты-продолжения возвращаются прежнему говорящему (_fix_boundaries)."""
    if not words:
        return ""
    assigned = [_speaker_at((w.start + w.end) / 2, turns) for w in words]
    assigned = _fix_boundaries(assigned, words)
    lines: list[str] = []
    current, buf = None, []
    for w, speaker in zip(words, assigned):
        if speaker != current:
            if buf:
                lines.append(f"Собеседник {current + 1}: " + "".join(buf).strip())
            current, buf = speaker, []
        buf.append(w.text)
    if buf:
        lines.append(f"Собеседник {current + 1}: " + "".join(buf).strip())
    return "\n\n".join(lines)


def speaker_fragments(words: list[Word], turns: list[SpeakerTurn],
                      max_len: float = 7.0, pad: float = 0.15) -> dict:
    """Для каждого говорящего — интервал (start, end) образцового фрагмента,
    чтобы его можно было прослушать при выборе имени (как в Plaud).

    Берём самый длинный НЕПРЕРЫВНЫЙ сольный прогон слов говорящего (чтобы не
    поймать «угу»), центрируем и обрезаем до max_len секунд. Ключ словаря —
    0-based индекс говорящего (как в build_dialogue, +1 при показе)."""
    if not words:
        return {}
    assigned = _fix_boundaries(
        [_speaker_at((w.start + w.end) / 2, turns) for w in words], words)
    # непрерывные группы одного говорящего
    best: dict = {}   # speaker -> (длительность, start, end)
    i, n = 0, len(words)
    while i < n:
        j = i
        while j + 1 < n and assigned[j + 1] == assigned[i]:
            j += 1
        spk = assigned[i]
        st, en = words[i].start, words[j].end
        dur = en - st
        if dur >= 1.5 and (j - i + 1) >= 3:   # не «угу», хотя бы 3 слова
            if spk not in best or dur > best[spk][0]:
                best[spk] = (dur, st, en)
        i = j + 1
    out: dict = {}
    for spk, (dur, st, en) in best.items():
        if dur > max_len:                     # обрезаем по центру
            mid = (st + en) / 2
            st, en = mid - max_len / 2, mid + max_len / 2
        out[spk] = (max(st - pad, 0.0), en + pad)
    return out
