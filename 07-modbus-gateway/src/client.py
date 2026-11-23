"""Modbus TCP 客户端：读/写、异常码抛错、多从站批量轮询、重试。"""
import socket
from codec import (ModbusExceptionResponse, ModbusError, build_read_holding,
                   build_write_single, decode_tcp)


class ModbusTcpClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 502,
                 timeout: float = 1.0, retries: int = 1):
        self.host, self.port = host, port
        self.timeout, self.retries = timeout, retries
        self._tid = 0

    def _next_tid(self) -> int:
        self._tid = (self._tid + 1) & 0xFFFF
        return self._tid or 1

    def _request(self, frame: bytes) -> dict:
        last = None
        for attempt in range(self.retries + 1):
            try:
                with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                    s.sendall(frame)
                    raw = s.recv(512)
                if not raw:
                    raise ModbusError("连接被对端关闭")
            except OSError as e:            # 只有网络错误才重试
                last = e
                if attempt == self.retries:
                    break
                continue
            resp = decode_tcp(raw)
            if "exception" in resp:
                # 从站异常是业务结果，不重试，直接丢给调用方判断
                raise ModbusExceptionResponse(resp["function"], resp["exception"])
            return resp
        raise ModbusError(f"请求失败（重试 {self.retries} 次）：{last}")

    def read_holding(self, unit: int, start: int, count: int) -> list[int]:
        resp = self._request(build_read_holding(unit, start, count, self._next_tid()))
        data = resp["data"]
        if data[0] != count * 2:
            raise ModbusError(f"返回字节数不符：声明 {data[0]}，期望 {count * 2}")
        return [int.from_bytes(data[1 + i * 2:3 + i * 2], "big") for i in range(count)]

    def write_single(self, unit: int, address: int, value: int) -> int:
        resp = self._request(build_write_single(unit, address, value, self._next_tid()))
        return int.from_bytes(resp["data"][2:4], "big")

    def poll(self, units: list[int], start: int, count: int) -> dict:
        out = {}
        for u in units:
            try:
                out[u] = self.read_holding(u, start, count)
            except ModbusError as e:
                out[u] = f"ERR: {e}"
        return out
