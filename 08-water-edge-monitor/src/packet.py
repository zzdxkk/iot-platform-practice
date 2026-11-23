"""紧凑上报包：定长二进制 + CRC8，压缩文本上报的体积。"""
import struct

VERSION = 2
FMT = ">BHIBhH"          # version, seq, device_id, flags, value*100, battery_mv
SIZE = struct.calcsize(FMT) + 1

FLAG_ALARM = 0x01
FLAG_WARN = 0x02
FLAG_LOW_BATTERY = 0x04


class PacketError(Exception):
    pass


def crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def encode(device_id: int, seq: int, value: float, battery_mv: int,
           level: str = "normal", version: int = VERSION) -> bytes:
    flags = {"normal": 0, "warning": FLAG_WARN, "alarm": FLAG_ALARM}.get(level, 0)
    if battery_mv < 2800:
        flags |= FLAG_LOW_BATTERY
    if not 0 <= device_id <= 0xFFFFFFFF:
        raise PacketError("device_id 超出 4 字节")
    if not 0 <= seq <= 0xFFFF:
        raise PacketError("seq 超出 2 字节")
    scaled = int(round(value * 100))
    if not -32768 <= scaled <= 32767:
        raise PacketError(f"测量值超出 int16 范围：{value}")
    body = struct.pack(FMT, version, seq, device_id, flags, scaled, battery_mv)
    return body + bytes([crc8(body)])


def decode(data: bytes) -> dict:
    if len(data) != SIZE:
        raise PacketError(f"长度不符：期望 {SIZE}，收到 {len(data)}")
    body, got = data[:-1], data[-1]
    if crc8(body) != got:
        raise PacketError("CRC8 校验失败")
    version, seq, device_id, flags, scaled, battery = struct.unpack(FMT, body)
    if version != VERSION:
        raise PacketError(f"版本不支持：{version}")
    level = "alarm" if flags & FLAG_ALARM else "warning" if flags & FLAG_WARN else "normal"
    return {"version": version, "seq": seq, "device_id": device_id, "flags": flags,
            "value": scaled / 100, "battery_mv": battery, "level": level,
            "low_battery": bool(flags & FLAG_LOW_BATTERY)}


def uplink_bytes(samples: list[dict]) -> int:
    """对比 JSON 文本与二进制体积，用来说明压缩收益。"""
    import json
    text = sum(len(json.dumps(s, ensure_ascii=False)) for s in samples)
    return text, SIZE * len(samples)
