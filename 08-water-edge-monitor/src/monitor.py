"""边缘监测闭环：采样 -> 检测 -> 事件 -> 紧凑上报包。"""
from detect import ALARM, NORMAL, WARNING, LeakDetector
from packet import PacketError, decode, encode


class EdgeMonitor:
    def __init__(self, device_id: int, battery_mv: int = 3600,
                 detector: LeakDetector | None = None):
        self.device_id = device_id
        self.battery_mv = battery_mv
        self.detector = detector or LeakDetector()
        self.seq = 0
        self.events: list[dict] = []
        self.packets: list[bytes] = []

    def ingest(self, ts: int, value: float) -> dict:
        ev = self.detector.update(ts, value)
        level = ev.level if ev else NORMAL
        if ev:
            self.events.append({"ts": ev.ts, "level": ev.level, "value": ev.value,
                                "baseline": ev.baseline, "score": ev.score,
                                "reason": ev.reason})
        self.seq = (self.seq + 1) & 0xFFFF
        try:
            pkt = encode(self.device_id, self.seq, value, self.battery_mv, level)
        except PacketError as e:
            return {"error": str(e), "level": level}
        self.packets.append(pkt)
        return {"level": level, "packet": pkt, "seq": self.seq}

    def run(self, samples: list[dict]) -> dict:
        for s in samples:
            self.ingest(s["ts"], s["value"])
        return {"events": self.events, "packets": len(self.packets),
                "alarms": sum(1 for e in self.events if e["level"] == ALARM),
                "warnings": sum(1 for e in self.events if e["level"] == WARNING)}

    def last_packet(self) -> dict:
        return decode(self.packets[-1]) if self.packets else {}


def replay(packets: list[bytes]) -> list[dict]:
    """模拟服务端解包，任何坏包单独标记，不中断整批。"""
    out = []
    for p in packets:
        try:
            out.append(decode(p))
        except PacketError as e:
            out.append({"error": str(e)})
    return out
