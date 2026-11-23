"""Modbus 帧编解码：RTU（CRC16）与 TCP（MBAP），异常响应。"""
CRC_POLY = 0xA001
MAX_READ = 125


class ModbusError(Exception):
    pass


class ModbusExceptionResponse(ModbusError):
    def __init__(self, function: int, code: int):
        self.function, self.code = function, code
        super().__init__(f"从站异常：function=0x{function:02X} code=0x{code:02X}")


EXCEPTION_TEXT = {
    0x01: "非法功能码",
    0x02: "非法数据地址",
    0x03: "非法数据值",
    0x04: "从站设备故障",
    0x06: "从站忙",
    0x0B: "网关目标设备无响应",
}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ CRC_POLY
            else:
                crc >>= 1
    return crc


def encode_rtu(slave: int, function: int, body: bytes) -> bytes:
    if not 0 <= slave <= 247:
        raise ModbusError(f"从站地址越界：{slave}")
    frame = bytes([slave, function]) + body
    crc = crc16(frame)
    return frame + bytes([crc & 0xFF, (crc >> 8) & 0xFF])   # CRC 低字节在前


def decode_rtu(frame: bytes) -> dict:
    if len(frame) < 4:
        raise ModbusError("RTU 帧太短")
    body, got = frame[:-2], frame[-2:]
    crc = crc16(body)
    if bytes([crc & 0xFF, (crc >> 8) & 0xFF]) != got:
        raise ModbusError(f"CRC 校验失败：帧内 {got.hex()}，计算 {crc:04X}")
    slave, function, rest = body[0], body[1], body[2:]
    if function & 0x80:
        if not rest:
            raise ModbusError("异常帧缺少异常码")
        return {"slave": slave, "function": function & 0x7F, "exception": rest[0],
                "text": EXCEPTION_TEXT.get(rest[0], "未知异常码")}
    return {"slave": slave, "function": function, "data": rest}


def encode_tcp(unit: int, function: int, body: bytes, transaction_id: int = 1) -> bytes:
    pdu = bytes([function]) + body
    mbap = (transaction_id.to_bytes(2, "big") + b"\x00\x00" +
            (len(pdu) + 1).to_bytes(2, "big") + bytes([unit]))
    return mbap + pdu


def decode_tcp(frame: bytes) -> dict:
    if len(frame) < 8:
        raise ModbusError("MBAP 头不完整")
    tid = int.from_bytes(frame[0:2], "big")
    proto = int.from_bytes(frame[2:4], "big")
    if proto != 0:
        raise ModbusError(f"协议标识必须为 0，收到 {proto}")
    length = int.from_bytes(frame[4:6], "big")
    unit = frame[6]
    pdu = frame[7:7 + length - 1]
    if len(pdu) < length - 1 or not pdu:
        raise ModbusError(f"长度不符：声明 {length}，实际 {len(pdu) + 1}")
    function, rest = pdu[0], pdu[1:]
    if function & 0x80:
        return {"transaction_id": tid, "unit": unit, "function": function & 0x7F,
                "exception": rest[0] if rest else 0,
                "text": EXCEPTION_TEXT.get(rest[0] if rest else 0, "未知异常码")}
    return {"transaction_id": tid, "unit": unit, "function": function, "data": rest}


def exception_frame(unit: int, function: int, code: int, transaction_id: int = 1,
                   rtu: bool = False) -> bytes:
    body = bytes([code])
    if rtu:
        return encode_rtu(unit, function | 0x80, body)
    return encode_tcp(unit, function | 0x80, body, transaction_id)


def build_read_holding(slave: int, start: int, count: int, transaction_id: int = 1,
                       rtu: bool = False) -> bytes:
    if not 1 <= count <= MAX_READ:
        raise ModbusError(f"读取数量需在 1..{MAX_READ}：{count}")
    body = start.to_bytes(2, "big") + count.to_bytes(2, "big")
    return encode_rtu(slave, 0x03, body) if rtu else encode_tcp(
        slave, 0x03, body, transaction_id)


def build_write_single(slave: int, address: int, value: int, transaction_id: int = 1,
                       rtu: bool = False) -> bytes:
    body = address.to_bytes(2, "big") + value.to_bytes(2, "big")
    return encode_rtu(slave, 0x06, body) if rtu else encode_tcp(
        slave, 0x06, body, transaction_id)


def build_write_multiple(slave: int, start: int, values: list[int],
                         transaction_id: int = 1, rtu: bool = False) -> bytes:
    if not 1 <= len(values) <= 123:
        raise ModbusError(f"写入寄存器数量需在 1..123：{len(values)}")
    body = (start.to_bytes(2, "big") + len(values).to_bytes(2, "big") +
            bytes([len(values) * 2]) +
            b"".join(v.to_bytes(2, "big") for v in values))
    return encode_rtu(slave, 0x10, body) if rtu else encode_tcp(
        slave, 0x10, body, transaction_id)
