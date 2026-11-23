"""JSONL 轨迹：每步一条事件，含时间戳、工具、参数、结果、耗时。"""
import json
import os
import time


class Trace:
    def __init__(self, path: str | None = None):
        self.path = path
        self.events: list[dict] = []
        self.t0 = time.monotonic()
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def emit(self, kind: str, **fields) -> dict:
        ev = {"kind": kind, "t": round(time.monotonic() - self.t0, 4), **fields}
        self.events.append(ev)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    def load(self) -> list[dict]:
        if not self.path or not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
