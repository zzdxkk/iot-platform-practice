"""自动评测指标：完全匹配、词级 F1、包含、BLEU-4、ROUGE-L、JSON 字段命中。"""
import json
import math
import re

_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    """英文按词、中文按单字，保证中英混排也能比较。"""
    out = []
    for m in _WORD.finditer(text.lower()):
        out.append(m.group())
    cjk = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    return out + cjk


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def exact_match(pred: str, ref: str) -> float:
    return 1.0 if normalize(pred) == normalize(ref) else 0.0


def contains_ref(pred: str, ref: str) -> float:
    return 1.0 if normalize(ref) in normalize(pred) else 0.0


def token_f1(pred: str, ref: str) -> float:
    p, r = tokens(pred), tokens(ref)
    if not p and not r:
        return 1.0
    if not p or not r:
        return 0.0
    common = sum(min(p.count(t), r.count(t)) for t in set(p) & set(r))
    if common == 0:
        return 0.0
    prec, rec = common / len(p), common / len(r)
    return 2 * prec * rec / (prec + rec)


def _ngrams(seq, n):
    return [tuple(seq[i:i + n]) for i in range(len(seq) - n + 1)]


def bleu(pred: str, ref: str, max_n: int = 4) -> float:
    p, r = tokens(pred), tokens(ref)
    if not p or not r:
        return 0.0
    logs, used = [], []
    for n in range(1, max_n + 1):
        pn, rn = _ngrams(p, n), _ngrams(r, n)
        if not pn:
            continue
        hit = sum(min(pn.count(g), rn.count(g)) for g in set(pn)) if rn else 0
        logs.append(math.log((hit + 1e-9) / len(pn)))
        used.append(n)
    if not logs:
        return 0.0
    bp = 1.0 if len(p) > len(r) else math.exp(1 - len(r) / len(p))
    return bp * math.exp(sum(logs) / len(logs))


def _lcs(a, b):
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if a[i - 1] == b[j - 1] else max(
                dp[i - 1][j], dp[i][j - 1])
    return dp[-1][-1]


def rouge_l(pred: str, ref: str, beta: float = 1.2) -> float:
    p, r = tokens(pred), tokens(ref)
    if not p or not r:
        return 0.0
    lcs = _lcs(p, r)
    if lcs == 0:
        return 0.0
    prec, rec = lcs / len(p), lcs / len(r)
    return (1 + beta ** 2) * prec * rec / (rec + beta ** 2 * prec)


def json_field_accuracy(pred: str, ref: dict) -> float:
    """参考答案是 dict 时，逐字段比较预测里的 JSON。"""
    try:
        got = json.loads(pred) if isinstance(pred, str) else pred
    except (json.JSONDecodeError, TypeError):
        return 0.0
    if not isinstance(got, dict) or not ref:
        return 0.0
    hit = sum(1 for k, v in ref.items()
              if str(got.get(k, "")).strip() == str(v).strip())
    return hit / len(ref)


def score_case(pred: str, case: dict) -> dict:
    ref = case["reference"]
    if isinstance(ref, dict):
        return {"field_acc": json_field_accuracy(pred, ref)}
    return {
        "em": exact_match(pred, ref),
        "f1": token_f1(pred, ref),
        "bleu": bleu(pred, ref),
        "rouge_l": rouge_l(pred, ref),
        "contains": contains_ref(pred, ref),
    }
