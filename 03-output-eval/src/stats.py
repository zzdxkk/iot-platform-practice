"""统计显著性：bootstrap 置信区间、配对 bootstrap、精确符号检验。"""
import math
import random


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def bootstrap_ci(xs, n_boot=2000, alpha=0.05, seed=0):
    """百分位 bootstrap：样本少也给出不确定度，而不是只报一个均值。"""
    if not xs:
        return (0.0, 0.0)
    rng, m = random.Random(seed), len(xs)
    stats = sorted(mean([xs[rng.randrange(m)] for _ in range(m)]) for _ in range(n_boot))
    lo = stats[int(n_boot * alpha / 2)]
    hi = stats[int(n_boot * (1 - alpha / 2)) - 1]
    return (round(lo, 4), round(hi, 4))


def paired_bootstrap(a, b, n_boot=2000, seed=0):
    """同一批样本上比较两个系统：差值 CI 与双尾 p 值。"""
    if len(a) != len(b) or not a:
        raise ValueError("配对样本长度必须一致且非空")
    diffs = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    m = len(diffs)
    boots = sorted(mean([diffs[rng.randrange(m)] for _ in range(m)]) for _ in range(n_boot))
    lo, hi = boots[int(n_boot * 0.025)], boots[int(n_boot * 0.975) - 1]
    # p 值取 bootstrap 分布落在 0 两侧的比例，双侧
    p = sum(1 for v in boots if v <= 0) / n_boot if mean(diffs) > 0 else \
        sum(1 for v in boots if v >= 0) / n_boot
    return {"delta": round(mean(diffs), 4), "ci": (round(lo, 4), round(hi, 4)),
            "p": round(min(1.0, 2 * p), 4)}


def sign_test(wins: int, losses: int) -> float:
    """精确二项符号检验（双尾），n<=1000 时用组合数精确求和。"""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 6)
