"""灰度发布：按设备分桶分批放量，失败率超阈值自动熔断并回滚。"""
import hashlib

STAGES = (5, 25, 100)          # 百分比


def bucket_of(device_id: str) -> int:
    h = hashlib.sha256(device_id.encode()).hexdigest()
    return int(h[:8], 16) % 100


class Rollout:
    def __init__(self, failure_threshold: float = 0.1, min_samples: int = 10):
        self.stages = list(STAGES)
        self.stage_idx = 0
        self.threshold = failure_threshold
        self.min_samples = min_samples
        self.results: dict[str, bool] = {}
        self.halted = False
        self.rolled_back = False
        self.history: list[dict] = []

    @property
    def percent(self) -> int:
        return 0 if self.halted else self.stages[self.stage_idx]

    def eligible(self, device_id: str) -> bool:
        """当前阶段放量的设备：分桶落在本阶段百分比内。"""
        return not self.halted and bucket_of(device_id) < self.stages[self.stage_idx]

    def report(self, device_id: str, ok: bool) -> dict:
        self.results[device_id] = ok
        bad = sum(1 for v in self.results.values() if not v)
        total = len(self.results)
        rate = bad / total if total else 0.0
        if total >= self.min_samples and rate > self.threshold:
            self.halted, self.rolled_back = True, True
            self.history.append({"stage": self.stages[self.stage_idx], "halted": True,
                                 "failure_rate": round(rate, 4), "samples": total})
        return {"failure_rate": round(rate, 4), "halted": self.halted,
                "samples": total}

    def promote(self) -> dict:
        if self.halted:
            raise RuntimeError("已熔断，先处理回滚再推进")
        if self.stage_idx + 1 >= len(self.stages):
            return {"stage": self.stages[-1], "done": True}
        self.stage_idx += 1
        self.history.append({"stage": self.stages[self.stage_idx], "halted": False})
        return {"stage": self.stages[self.stage_idx], "done": False}
