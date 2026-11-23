"""从站寄存器表：读/写处理、地址与值校验、异常码生成。"""
from codec import MAX_READ, ModbusError

ILLEGAL_FUNCTION, ILLEGAL_ADDRESS, ILLEGAL_VALUE, DEVICE_FAILURE = 0x01, 0x02, 0x03, 0x04


class RegisterMap:
    def __init__(self, hold: dict[int, int] | None = None,
                 input_: dict[int, int] | None = None):
        self.holding = dict(hold or {})
        self.input = dict(input_ or {})
        self.writes = 0

    def _check(self, table: dict, start: int, count: int):
        if start < 0 or start + count > 0x10000:
            raise ModbusError("地址越界")
        for a in range(start, start + count):
            if a not in table:
                raise ModbusError(f"未定义寄存器 {a}")

    def read_holding(self, start: int, count: int) -> bytes:
        if not 1 <= count <= MAX_READ:
            return self._except(ILLEGAL_VALUE)
        try:
            self._check(self.holding, start, count)
        except ModbusError:
            return self._except(ILLEGAL_ADDRESS)
        vals = [self.holding[start + i] for i in range(count)]
        return bytes([count * 2]) + b"".join(v.to_bytes(2, "big") for v in vals)

    def read_input(self, start: int, count: int) -> bytes:
        if not 1 <= count <= MAX_READ:
            return self._except(ILLEGAL_VALUE)
        try:
            self._check(self.input, start, count)
        except ModbusError:
            return self._except(ILLEGAL_ADDRESS)
        vals = [self.input[start + i] for i in range(count)]
        return bytes([count * 2]) + b"".join(v.to_bytes(2, "big") for v in vals)

    def write_single(self, address: int, value: int) -> bytes:
        if not 0 <= value <= 0xFFFF:
            return self._except(ILLEGAL_VALUE)
        if address not in self.holding:
            return self._except(ILLEGAL_ADDRESS)
        self.holding[address] = value
        self.writes += 1
        return address.to_bytes(2, "big") + value.to_bytes(2, "big")

    def write_multiple(self, start: int, values: list[int]) -> bytes:
        if not 1 <= len(values) <= 123 or any(not 0 <= v <= 0xFFFF for v in values):
            return self._except(ILLEGAL_VALUE)
        try:
            self._check(self.holding, start, len(values))
        except ModbusError:
            return self._except(ILLEGAL_ADDRESS)
        for i, v in enumerate(values):
            self.holding[start + i] = v
        self.writes += len(values)
        return start.to_bytes(2, "big") + len(values).to_bytes(2, "big")

    @staticmethod
    def _except(code: int) -> bytes:
        return ("EXCEPTION:" + str(code)).encode()
