"""时域与频域特征：RMS、峰度、峰值因子、频谱重心、轴承故障频率能量。"""
import math

from fft import band_energy, fft, spectrum

FAULT_THRESHOLD = 0.15        # 故障频带能量占总能量比例


def rms(x):
    return math.sqrt(sum(v * v for v in x) / len(x)) if x else 0.0


def kurtosis(x):
    n = len(x)
    if n < 4:
        return 0.0
    m = sum(x) / n
    var = sum((v - m) ** 2 for v in x) / n
    if var == 0:
        return 0.0
    return sum((v - m) ** 4 for v in x) / (n * var * var) - 3.0


def crest_factor(x):
    r = rms(x)
    return max(abs(v) for v in x) / r if r else 0.0


def spectral_centroid(freqs, amps):
    total = sum(amps)
    return sum(f * a for f, a in zip(freqs, amps)) / total if total else 0.0


def bearing_frequencies(rpm: float, rollers: int, ball_d: float, pitch_d: float,
                        contact_deg: float = 0.0) -> dict:
    """BPFO/BPFI 标准公式：滚动体数、节径、球径、接触角。"""
    fr = rpm / 60.0
    ratio = ball_d / pitch_d * math.cos(math.radians(contact_deg))
    return {"fr": round(fr, 4),
            "bpfo": round(rollers / 2 * fr * (1 - ratio), 3),
            "bpfi": round(rollers / 2 * fr * (1 + ratio), 3),
            "bsf": round(pitch_d / (2 * ball_d) * fr * (1 - ratio ** 2), 3)}


def harmonics(f0: float, n: int = 3) -> list[float]:
    return [f0 * (i + 1) for i in range(n)]


def band_ratio(freqs, amps, centers: list[float], width: float = 4.0) -> float:
    total = sum(a * a for a in amps) or 1e-12
    hit = sum(band_energy(freqs, amps, c - width / 2, c + width / 2) for c in centers)
    return hit / total


def extract(x: list[float], fs: float, fault_freqs: dict | None = None) -> dict:
    freqs, amps = spectrum(x, fs)
    out = {"rms": round(rms(x), 4), "kurtosis": round(kurtosis(x), 3),
           "crest": round(crest_factor(x), 3),
           "centroid": round(spectral_centroid(freqs, amps), 2),
           "dominant_hz": round(max(((a, f) for f, a in zip(freqs, amps)))[1], 2)}
    if fault_freqs:
        outer = band_ratio(freqs, amps, harmonics(fault_freqs["bpfo"]))
        inner = band_ratio(freqs, amps, harmonics(fault_freqs["bpfi"]))
        out.update({"bpfo_ratio": round(outer, 4), "bpfi_ratio": round(inner, 4),
                    "diagnosis": ("outer_race" if outer >= FAULT_THRESHOLD else
                                  "inner_race" if inner >= FAULT_THRESHOLD else "healthy")})
    return out


def health_index(features: dict) -> float:
    """把多个特征压成一个 0–100 的健康度，越大越健康。"""
    h = 100.0
    h -= min(60.0, features.get("bpfo_ratio", 0) * 100)     # 外圈故障最伤
    h -= min(45.0, features.get("bpfi_ratio", 0) * 100)
    h -= min(20.0, max(0.0, features.get("kurtosis", 0)) * 3)
    h -= min(20.0, max(0.0, features.get("crest", 0) - 3.0) * 3)
    return round(max(0.0, h), 2)
