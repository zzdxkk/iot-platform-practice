"""异常检测：EWMA 基线 + CUSUM 累积偏移 + 迟滞/冷却，避免抖动报警。"""
from dataclasses import dataclass

NORMAL, WARNING, ALARM = "normal", "warning", "alarm"


@dataclass
class Event:
    ts: int
    level: str
    value: float
    baseline: float
    score: float
    reason: str


class Ewma:
    """对"正常态"做慢速基线跟踪；暖机阶段不参与判定。"""

    def __init__(self, alpha: float = 0.2, warmup: int = 8):
        self.alpha, self.warmup = alpha, warmup
        self.value: float | None = None
        self.n = 0

    def update(self, x: float) -> float | None:
        self.n += 1
        if self.value is None:
            self.value = x
        else:
            self.value = self.alpha * x + (1 - self.alpha) * self.value
        return None if self.n <= self.warmup else self.value

    @property
    def ready(self) -> bool:
        return self.value is not None and self.n > self.warmup


class Cusum:
    """双侧 CUSUM：对"高于/低于目标"的持续小偏移敏感。"""

    def __init__(self, target: float = 0.0, k: float = 0.5, h: float = 4.0):
        self.target, self.k, self.h = target, k, h
        self.hi = self.lo = 0.0

    def update(self, x: float) -> tuple[bool, bool]:
        self.hi = max(0.0, self.hi + (x - self.target) - self.k)
        self.lo = max(0.0, self.lo - (x - self.target) - self.k)
        up, down = self.hi > self.h, self.lo > self.h
        if up:
            self.hi = 0.0
        if down:
            self.lo = 0.0
        return up, down


def rolling_std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


class LeakDetector:
    def __init__(self, sigma: float = 0.6, warn_z: float = 2.0, alarm_z: float = 3.5,
                 confirm_n: int = 2, cooldown: int = 20, cusum_h: float = 4.0):
        self.sigma = sigma
        self.warn_z, self.alarm_z = warn_z, alarm_z
        self.confirm_n, self.cooldown = confirm_n, cooldown
        self.ewma = Ewma()
        self.cusum = Cusum(k=0.5, h=cusum_h)
        self._hits = 0
        self._cooldown_left = 0
        self._last_level = NORMAL
        self.history: list[float] = []

    def update(self, ts: int, value: float) -> Event | None:
        baseline = self.ewma.value or value
        self.history.append(value)
        if len(self.history) > 60:
            self.history.pop(0)
        if not self.ewma.ready:
            self.ewma.update(value)
            return None
        z = (value - self.ewma.value) / (self.sigma or 1e-9)
        up, down = self.cusum.update(z)
        level = NORMAL
        if abs(z) >= self.alarm_z or up:
            level = ALARM
        elif abs(z) >= self.warn_z:
            level = WARNING
        if level != NORMAL:
            self._hits += 1
        else:
            self._hits = 0
        if self._cooldown_left > 0:
            # 冷却期只做去抖，不把异常值学进正常基线（否则渗漏会被"学成正常"）
            self._cooldown_left -= 1
            return None
        if level == NORMAL:
            self.ewma.update(value)          # 正常点持续更新基线
            self._last_level = NORMAL
            return None
        if self._hits < self.confirm_n:
            return None                      # 连续确认，压掉单点尖刺
        ev = Event(ts, level, value, round(self.ewma.value, 3), round(z, 3),
                   "CUSUM 单侧累积" if up else f"z={z:.2f} 超阈值")
        self._last_level = level
        self._cooldown_left = self.cooldown
        self._hits = 0
        self.cusum.hi = self.cusum.lo = 0.0
        return ev
