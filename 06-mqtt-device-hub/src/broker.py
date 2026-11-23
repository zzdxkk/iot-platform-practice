"""内存 MQTT broker：会话、订阅、retained、QoS1 去重、设备影子 delta。"""
from codec import encode_publish
from topic import matches, validate_filter, validate_topic


class Session:
    def __init__(self, client_id: str, clean_session: bool = True):
        self.client_id = client_id
        self.clean_session = clean_session
        self.subs: dict[str, int] = {}          # filter -> qos
        self.queue: list[dict] = []             # 离线待下发（QoS1）
        self.connected = True


class Broker:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.retained: dict[str, bytes] = {}
        self.shadow = {"desired": {}, "reported": {}}
        self.stats = {"received": 0, "delivered": 0, "dropped": 0, "retained": 0}
        self._seen: dict[str, set[int]] = {}    # client -> 已处理 packet_id（QoS1 去重）

    # --- 连接 ---
    def connect(self, client_id: str, clean_session: bool = True) -> dict:
        old = self.sessions.get(client_id)
        if old and old.clean_session:
            self.sessions[client_id] = Session(client_id, clean_session)
        elif old:
            old.connected = True                       # 保留订阅与离线队列
        else:
            self.sessions[client_id] = Session(client_id, clean_session)
        self._seen.setdefault(client_id, set())
        return {"client_id": client_id, "clean_session": clean_session,
                "session_present": bool(old and not clean_session)}

    def disconnect(self, client_id: str) -> None:
        s = self.sessions.get(client_id)
        if s:
            s.connected = False
            if s.clean_session:
                self.sessions.pop(client_id)

    # --- 订阅 ---
    def subscribe(self, client_id: str, topics: list[tuple[str, int]]) -> list[int]:
        s = self.sessions.get(client_id)
        if s is None:
            raise KeyError(f"未连接：{client_id}")
        codes = []
        for filter_, qos in topics:
            try:
                validate_filter(filter_)
            except Exception:
                codes.append(0x80)                     # 失败码
                continue
            if qos not in (0, 1, 2):
                codes.append(0x80)
                continue
            s.subs[filter_] = qos
            codes.append(0x00)                         # 最大 QoS 0，简化协商
            for topic, payload in self.retained.items():
                if matches(filter_, topic):
                    s.queue.append({"topic": topic, "payload": payload,
                                    "qos": min(qos, 0), "retain": True})
        return codes

    # --- 发布 ---
    def publish(self, topic: str, payload, qos: int = 0, retain: bool = False,
                packet_id: int | None = None) -> dict:
        validate_topic(topic)
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        self.stats["received"] += 1
        if retain:
            if data:
                self.retained[topic] = data
                self.stats["retained"] += 1
            else:
                self.retained.pop(topic, None)          # 空 payload 清除 retained
        delivered = []
        for s in self.sessions.values():
            for filter_, sub_qos in s.subs.items():
                if not matches(filter_, topic):
                    continue
                eff_qos = min(qos, sub_qos)
                pid = packet_id if eff_qos > 0 else None
                msg = {"topic": topic, "payload": data, "qos": eff_qos,
                       "retain": retain, "packet_id": pid}
                s.queue.append(msg)
                delivered.append((s.client_id, filter_, eff_qos))
                self.stats["delivered"] += 1
                break                                     # 同一会话只发一次
        return {"delivered": delivered, "retained": retain}

    def poll(self, client_id: str) -> list[dict]:
        s = self.sessions[client_id]
        out, s.queue = s.queue, []
        return out

    def to_wire(self, msg: dict) -> bytes:
        return encode_publish(msg["topic"], msg["payload"], msg["qos"],
                              msg["retain"], msg["packet_id"])

    # --- QoS1 去重 ---
    def accept_publish(self, client_id: str, topic: str, payload, qos: int = 1,
                       packet_id: int | None = None, retain: bool = False) -> dict:
        if qos > 0:
            if not packet_id:
                raise ValueError("QoS1 报文必须带 packet_id")
            if packet_id in self._seen[client_id]:
                self.stats["dropped"] += 1
                return {"duplicate": True, "delivered": []}
            self._seen[client_id].add(packet_id)
        return {"duplicate": False, **self.publish(topic, payload, qos, retain, packet_id)}

    # --- 设备影子 ---
    def set_reported(self, values: dict) -> None:
        self.shadow["reported"].update(values)

    def set_desired(self, values: dict) -> None:
        self.shadow["desired"].update(values)

    def delta(self) -> dict:
        d = self.shadow["desired"]
        return {k: v for k, v in d.items() if self.shadow["reported"].get(k) != v}
