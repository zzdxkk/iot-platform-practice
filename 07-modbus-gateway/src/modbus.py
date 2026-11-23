"""Modbus 协议网关：RTU CRC 校验 + TCP 帧解析 + 寄存器映射 + 转标准化数据。"""
import struct

def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

def build_rtu(slave, func, addr, qty):
    body = struct.pack(">BBHH", slave, func, addr, qty)
    c = crc16(body)
    return body + struct.pack("<H", c)

def parse_rtu(frame):
    body, got = frame[:-2], struct.unpack("<H", frame[-2:])[0]
    return {"valid": crc16(body) == got, "slave": body[0], "func": body[1]}

def parse_tcp(frame):
    """MBAP 头 7 字节：事务ID(2)+协议(2)+长度(2)+单元ID(1)"""
    tx, proto, length, unit = struct.unpack(">HHHB", frame[:7])
    return {"tx": tx, "proto": proto, "length": length, "unit": unit, "func": frame[7]}

class RegisterMap:
    def __init__(self, mapping): self.mapping = mapping  # name -> (addr, scale)
    def decode(self, regs):
        out = {}
        for name, (addr, scale) in self.mapping.items():
            if addr in regs: out[name] = round(regs[addr] * scale, 3)
        return out

if __name__ == "__main__":
    f = build_rtu(1, 3, 0, 2)
    print("RTU 帧:", f.hex(), parse_rtu(f))
    rm = RegisterMap({"温度": (0, 0.1), "湿度": (1, 0.5)})
    print("寄存器解析:", rm.decode({0: 256, 1: 120}))
