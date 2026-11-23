"""MQTT 3.1.1 报文编解码（无第三方依赖）：CONNECT/CONNACK/PUBLISH/PUBACK/SUBSCRIBE/SUBACK/PING/DISCONNECT。"""
UTF8_MAX = 65535

CONNECT, CONNACK, PUBLISH, PUBACK, PUBREC, PUBREL, PUBCOMP = 1, 2, 3, 4, 5, 6, 7
SUBSCRIBE, SUBACK, UNSUBSCRIBE, UNSUBACK, PINGREQ, PINGRESP, DISCONNECT = 8, 9, 10, 11, 12, 13, 14

TYPE_NAMES = {CONNECT: "CONNECT", CONNACK: "CONNACK", PUBLISH: "PUBLISH",
              PUBACK: "PUBACK", SUBSCRIBE: "SUBSCRIBE", SUBACK: "SUBACK",
              UNSUBSCRIBE: "UNSUBSCRIBE", UNSUBACK: "UNSUBACK",
              PINGREQ: "PINGREQ", PINGRESP: "PINGRESP", DISCONNECT: "DISCONNECT"}


class CodecError(Exception):
    pass


def encode_remaining_length(n: int) -> bytes:
    if n < 0 or n > 268435455:
        raise CodecError(f"remaining length 越界：{n}")
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            return bytes(out)


def decode_remaining_length(data: bytes, pos: int = 1) -> tuple[int, int]:
    value, mult, i = 0, 1, 0
    while True:
        if pos + i >= len(data):
            raise CodecError("remaining length 被截断")
        b = data[pos + i]
        value += (b & 0x7F) * mult
        i += 1
        if not b & 0x80:
            break
        mult *= 128
        if i > 3:
            raise CodecError("remaining length 超过 4 字节")
    return value, pos + i


def _utf8(s: str) -> bytes:
    b = s.encode("utf-8")
    if len(b) > UTF8_MAX:
        raise CodecError("字符串超过 65535 字节")
    return len(b).to_bytes(2, "big") + b


def _read_utf8(buf: bytes, i: int) -> tuple[str, int]:
    if i + 2 > len(buf):
        raise CodecError("字符串长度字段缺失")
    n = int.from_bytes(buf[i:i + 2], "big")
    i += 2
    if i + n > len(buf):
        raise CodecError("字符串内容被截断")
    return buf[i:i + n].decode("utf-8", "replace"), i + n


def _packet(ptype: int, flags: int, body: bytes) -> bytes:
    return bytes([(ptype << 4) | flags]) + encode_remaining_length(len(body)) + body


def encode_connect(client_id: str, clean_session: bool = True, keepalive: int = 60,
                   username: str | None = None, password: str | None = None) -> bytes:
    flags = 0x02 if clean_session else 0
    if username:
        flags |= 0x80
    if password:
        flags |= 0x40
    body = _utf8("MQTT") + bytes([4, flags]) + keepalive.to_bytes(2, "big") + _utf8(client_id)
    if username:
        body += _utf8(username)
    if password:
        body += _utf8(password)
    return _packet(CONNECT, 0, body)


def encode_connack(return_code: int = 0, session_present: bool = False) -> bytes:
    return _packet(CONNACK, 0, bytes([1 if session_present else 0, return_code]))


def encode_publish(topic: str, payload, qos: int = 0, retain: bool = False,
                   packet_id: int | None = None, dup: bool = False) -> bytes:
    if qos not in (0, 1, 2):
        raise CodecError(f"不支持的 QoS：{qos}")
    if qos > 0 and not packet_id:
        raise CodecError("QoS>0 需要 packet_id")
    flags = (0x08 if dup else 0) | (qos << 1) | (0x01 if retain else 0)
    body = _utf8(topic)
    if qos > 0:
        body += packet_id.to_bytes(2, "big")
    if isinstance(payload, bytes):
        body += payload
    else:
        body += str(payload).encode("utf-8")
    return _packet(PUBLISH, flags, body)


def encode_puback(packet_id: int) -> bytes:
    return _packet(PUBACK, 0, packet_id.to_bytes(2, "big"))


def encode_subscribe(topics, packet_id: int) -> bytes:
    """topics: [(filter, qos), ...]"""
    body = packet_id.to_bytes(2, "big")
    for topic, qos in topics:
        body += _utf8(topic) + bytes([qos])
    return _packet(SUBSCRIBE, 0x02, body)      # SUBSCRIBE 固定 flags=0b0010


def encode_suback(packet_id: int, codes) -> bytes:
    return _packet(SUBACK, 0, packet_id.to_bytes(2, "big") + bytes(codes))


def encode_pingreq() -> bytes:
    return _packet(PINGREQ, 0, b"")


def encode_pingresp() -> bytes:
    return _packet(PINGRESP, 0, b"")


def encode_disconnect() -> bytes:
    return _packet(DISCONNECT, 0, b"")


def decode_packet(data: bytes) -> dict:
    if len(data) < 2:
        raise CodecError("报文太短")
    ptype, flags = data[0] >> 4, data[0] & 0x0F
    name = TYPE_NAMES.get(ptype)
    if name is None:
        raise CodecError(f"未知报文类型：{ptype}")
    rl, pos = decode_remaining_length(data)
    body = data[pos:pos + rl]
    if len(body) < rl:
        raise CodecError(f"{name} 报文长度不足：声明 {rl}，实际 {len(body)}")
    out = {"type": name, "flags": flags, "length": rl}
    if name == "CONNECT":
        proto, i = _read_utf8(body, 0)
        level, cflags = body[i], body[i + 1]
        keepalive = int.from_bytes(body[i + 2:i + 4], "big")
        cid, i = _read_utf8(body, i + 4)
        out.update({"protocol": proto, "level": level, "keepalive": keepalive,
                    "clean_session": bool(cflags & 0x02), "client_id": cid})
        if cflags & 0x80:
            out["username"], i = _read_utf8(body, i)
        if cflags & 0x40:
            out["password"], i = _read_utf8(body, i)
    elif name == "PUBLISH":
        qos = (flags >> 1) & 0x03
        retain, dup = bool(flags & 0x01), bool(flags & 0x08)
        topic, i = _read_utf8(body, 0)
        pid = None
        if qos > 0:
            pid = int.from_bytes(body[i:i + 2], "big")
            i += 2
        out.update({"topic": topic, "qos": qos, "retain": retain, "dup": dup,
                    "packet_id": pid, "payload": body[i:]})
    elif name in ("PUBACK", "SUBACK", "UNSUBACK"):
        out["packet_id"] = int.from_bytes(body[:2], "big")
        if name == "SUBACK":
            out["codes"] = list(body[2:])
    elif name == "SUBSCRIBE":
        out["packet_id"] = int.from_bytes(body[:2], "big")
        topics, i = [], 2
        while i < len(body):
            f, i = _read_utf8(body, i)
            topics.append((f, body[i]))
            i += 1
        out["topics"] = topics
    elif name in ("CONNACK",):
        out.update({"session_present": bool(body[0]), "return_code": body[1]})
    return out
