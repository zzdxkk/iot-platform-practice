"""radix-2 FFT、Hann 窗、单边幅值谱、频带能量。"""
import cmath
import math


class FFTError(Exception):
    pass


def _bit_reverse(a: list[complex]) -> None:
    n = len(a)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]


def fft(x: list) -> list[complex]:
    """迭代式 radix-2，长度必须是 2 的幂。"""
    n = len(x)
    if n == 0 or n & (n - 1):
        raise FFTError(f"FFT 长度必须是 2 的幂：{n}")
    a = [complex(v) for v in x]
    _bit_reverse(a)
    size = 2
    while size <= n:
        half = size // 2
        w_step = cmath.exp(-2j * math.pi / size)
        for start in range(0, n, size):
            w = 1 + 0j
            for k in range(start, start + half):
                t = a[k + half] * w
                a[k + half] = a[k] - t
                a[k] = a[k] + t
                w *= w_step
        size *= 2
    return a


def ifft(X: list[complex]) -> list[complex]:
    n = len(X)
    conj = [c.conjugate() for c in X]
    out = fft(conj)
    return [c.conjugate() / n for c in out]


def hann(n: int) -> list[float]:
    if n == 1:
        return [1.0]
    return [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]


def spectrum(x: list[float], fs: float, window: bool = True) -> tuple[list[float], list[float]]:
    """返回 (频率轴, 单边幅值)，幅值已按窗增益与 N/2 归一，正弦峰值≈幅度。"""
    n = len(x)
    w = hann(n) if window else [1.0] * n
    gain = sum(w) / n if window else 1.0
    X = fft([xi * wi for xi, wi in zip(x, w)])
    half = n // 2
    amps = [abs(X[0]) / (n * gain)]
    for k in range(1, half):
        amps.append(2 * abs(X[k]) / (n * gain))
    freqs = [k * fs / n for k in range(half)]
    return freqs, amps


def band_energy(freqs: list[float], amps: list[float], lo: float, hi: float) -> float:
    return sum(a * a for f, a in zip(freqs, amps) if lo <= f <= hi)


def peak(freqs: list[float], amps: list[float], lo: float = 0.0,
         hi: float = float("inf")) -> tuple[float, float]:
    cand = [(a, f) for f, a in zip(freqs, amps) if lo <= f <= hi]
    if not cand:
        raise FFTError(f"频段内没有谱线：{lo}-{hi}")
    a, f = max(cand)
    return f, a


def synthetic(fs: float, n: int, comps: list[tuple[float, float]],
              noise: float = 0.0, seed: int = 0) -> list[float]:
    """合成多频信号：[(频率, 幅度), ...]，可加确定性的伪噪声。"""
    import random
    rng = random.Random(seed)
    return [sum(amp * math.sin(2 * math.pi * f * i / fs + 0.3) for f, amp in comps)
            + (rng.gauss(0, noise) if noise else 0.0) for i in range(n)]
