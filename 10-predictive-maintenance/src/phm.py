"""预测性维护闭环：分块取特征 -> 诊断 -> 健康度趋势 -> RUL 与告警。"""
from features import bearing_frequencies, extract, health_index
from rul import Trend, alert


class Monitor:
    def __init__(self, fs: float, rpm: float, rollers: int = 9, ball_d: float = 7.94,
                 pitch_d: float = 39.04, threshold: float = 40.0,
                 window: float = 24.0):
        self.fs = fs
        self.fault_freqs = bearing_frequencies(rpm, rollers, ball_d, pitch_d)
        self.threshold, self.window = threshold, window
        self.blocks: list[dict] = []

    def feed(self, block: list[float], t: float) -> dict:
        feats = extract(block, self.fs, self.fault_freqs)
        hi = health_index(feats)
        self.blocks.append({"t": t, "features": feats, "health": hi})
        return self.blocks[-1]

    def report(self) -> dict:
        if not self.blocks:
            return {"status": "no-data"}
        his = [b["health"] for b in self.blocks]
        trend = None
        if len(his) >= 3:
            trend = Trend([b["t"] for b in self.blocks], his)
        rul = trend.rul(self.blocks[-1]["t"], self.threshold) if trend else None
        lower = trend.rul_lower(self.blocks[-1]["t"], self.threshold) if trend else None
        diag = self.blocks[-1]["features"].get("diagnosis", "unknown")
        return {
            "health_now": his[-1],
            "health_first": his[0],
            "slope": round(trend.slope, 3) if trend else 0.0,
            "diagnosis": diag,
            "rul": None if rul is None else round(rul, 1),
            "rul_lower": None if lower is None else round(lower, 1),
            "alert": alert(rul, self.window),
            "fault_freqs": self.fault_freqs,
        }
