"""IoT 设备接入中心：物模型定义 -> 设备影子 -> 遥测入库 -> 规则引擎告警。"""
import time, json
from collections import defaultdict

class ThingModel:
    """物模型：属性/事件/服务三要素，是 IoT 平台的核心抽象。"""
    def __init__(self, name, props): self.name, self.props = name, props
    def validate(self, data):
        bad = [k for k in data if k not in self.props]
        return not bad, bad

class DeviceShadow:
    def __init__(self): self.state = defaultdict(dict)
    def update(self, device, reported):
        self.state[device].update(reported)
        return dict(self.state[device])

class RuleEngine:
    def __init__(self, rules): self.rules = rules  # [(field, op, threshold, level)]
    def evaluate(self, data):
        alerts = []
        for field, op, th, level in self.rules:
            v = data.get(field)
            if v is None: continue
            hit = (v > th) if op == ">" else (v < th) if op == "<" else False
            if hit: alerts.append({"field": field, "value": v, "level": level})
        return alerts

class DeviceHub:
    def __init__(self, model, rules):
        self.model, self.shadow, self.rules = model, DeviceShadow(), RuleEngine(rules)
        self.telemetry = []
    def ingest(self, device, payload):
        ok, bad = self.model.validate(payload)
        if not ok: return {"ok": False, "invalid": bad}
        self.shadow.update(device, payload)
        rec = {"ts": time.time(), "device": device, "data": payload,
               "alerts": self.rules.evaluate(payload)}
        self.telemetry.append(rec)
        return {"ok": True, "record": rec}

if __name__ == "__main__":
    model = ThingModel("温湿度终端", ["temp", "humi", "battery"])
    hub = DeviceHub(model, [("temp", ">", 30, "high"), ("battery", "<", 20, "low")])
    for d, p in [("dev01", {"temp": 25, "humi": 60, "battery": 90}),
                 ("dev01", {"temp": 35, "humi": 55, "battery": 18}),
                 ("dev02", {"temp": 22, "humi": 70, "battery": 80, "bad": 1})]:
        print(json.dumps(hub.ingest(d, p), ensure_ascii=False))
