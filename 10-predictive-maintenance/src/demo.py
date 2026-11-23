"""演示：FFT 频谱、轴承故障频率、健康度退化趋势与 RUL。"""
import math

from features import bearing_frequencies, extract
from fft import peak, spectrum, synthetic
from phm import Monitor

FS, N, RPM = 2000.0, 2048, 1800


def main():
    freqs = bearing_frequencies(RPM, rollers=9, ball_d=7.94, pitch_d=39.04)
    print("== 轴承故障频率 ==")
    print("  ", {k: round(v, 2) for k, v in freqs.items()}, "Hz")

    print("\n== 频谱 ==")
    sig = synthetic(FS, N, [(freqs["fr"], 0.8)])
    f, a = spectrum(sig, FS)
    pf, pa = peak(f, a)
    print(f"  单频 30Hz：峰值 {pf:.1f}Hz（理论 {freqs['fr']}Hz，分辨率 {FS / N:.2f}Hz），幅值 {pa:.3f}")

    print("\n== 健康 vs 外圈故障 ==")
    healthy = synthetic(FS, N, [(freqs["fr"], 0.8)], noise=0.05)
    outer = synthetic(FS, N, [(freqs["fr"], 0.5), (freqs["bpfo"], 0.8),
                              (2 * freqs["bpfo"], 0.6), (3 * freqs["bpfo"], 0.4)],
                      noise=0.05)
    for name, s in (("healthy", healthy), ("outer", outer)):
        e = extract(s, FS, freqs)
        print(f"  {name:8} rms={e['rms']:.3f} kurt={e['kurtosis']:+.2f} "
              f"crest={e['crest']:.2f} bpfo={e['bpfo_ratio']:.3f} → {e['diagnosis']}")

    print("\n== 退化趋势与 RUL ==")
    mon = Monitor(FS, RPM, threshold=45.0, window=48.0)
    for i in range(6):
        # 故障冲击随运行时间增强，模拟退化
        amp = 0.12 + 0.06 * i
        block = synthetic(FS, N, [(freqs["fr"], 0.5), (freqs["bpfo"], amp),
                                  (2 * freqs["bpfo"], amp * 0.7)], noise=0.05, seed=i)
        b = mon.feed(block, t=i * 24.0)
        print(f"  t={b['t']:5.0f}h 健康度={b['health']:6.2f} 诊断={b['features']['diagnosis']}")
    rep = mon.report()
    print("  报告：", {k: rep[k] for k in ("health_now", "slope", "diagnosis", "rul",
                                          "rul_lower", "alert")})
    print("  维护排期建议：按悲观估计",
          rep["rul_lower"] if rep["rul_lower"] is not None else "无退化趋势", "小时后处理")


if __name__ == "__main__":
    main()
