"""演示：EWMA/CUSUM 检测、迟滞抑制、功耗预算、二进制包往返与坏包隔离。"""
from detect import LeakDetector
from monitor import EdgeMonitor, replay
from packet import SIZE, crc8, decode, encode, uplink_bytes
from power import PowerProfile

DETECTOR = "演示用合成序列：前 20 点正常，随后缓慢渗漏上升"


def series():
    out = []
    for i in range(20):
        out.append({"ts": i * 60, "value": 3.0 + (0.3 if i % 3 == 0 else -0.2)})
    for j in range(8):
        out.append({"ts": (20 + j) * 60, "value": 3.2 + 0.55 * (j + 1)})
    for j in range(6):
        out.append({"ts": (28 + j) * 60, "value": 3.1})
    out.append({"ts": 34 * 60, "value": 9.8})       # 单点尖刺，应被确认机制压掉
    out += [{"ts": (35 + j) * 60, "value": 3.15} for j in range(4)]
    return out


def main():
    print("== 检测 ==", DETECTOR)
    det = LeakDetector(sigma=0.35, warn_z=2.0, alarm_z=3.5, confirm_n=2, cooldown=10)
    m = EdgeMonitor(device_id=0x1001, battery_mv=3650, detector=det)
    res = m.run(series())
    print("  事件：", [(e["ts"], e["level"], round(e["value"], 2), e["score"]) for e in res["events"]])
    print(f"  统计：{res['alarms']} 次报警，{res['warnings']} 次告警，共 {res['packets']} 个包")
    print("  最后包解出：", m.last_packet())

    print("\n== 功耗预算 ==")
    p = PowerProfile(sleep_ua=12, measure_ma=6, measure_s=2, tx_ma=25, tx_s=0.6,
                     measures_per_day=24, reports_per_day=4)
    print("  日耗：", p.daily_mah(), "mAh")
    print("  两节 18650（标称 2500mAh）寿命：", p.life_days(2500), "天")
    print("  目标 3 年的判定：", p.meets(2500, 3))

    print("\n== 上报包 ==")
    pkt = encode(0x1001, 7, 4.25, 3650, "alarm")
    print("  包长：", len(pkt), "字节（", SIZE, "= 结构体 + CRC8）十六进制：", pkt.hex())
    print("  解码：", decode(pkt))
    bad = pkt[:-1] + bytes([pkt[-1] ^ 0xFF])
    print("  坏包：", [r for r in replay([pkt, bad])][1])
    samples = [{"dev": 0x1001, "ts": i * 60, "value": round(3.0 + i * 0.1, 2),
                "seq": i, "battery_mv": 3650} for i in range(20)]
    text, bin_size = uplink_bytes(samples)
    print(f"  体积对比：JSON 文本 {text} 字节 vs 二进制 {bin_size} 字节")


if __name__ == "__main__":
    main()
