"""Modbus TCP 服务端：MBAP 解析、多从站、异常帧回包。"""
import socketserver
import threading

from codec import ModbusError, decode_tcp, encode_tcp
from registers import ILLEGAL_ADDRESS, ILLEGAL_FUNCTION, ILLEGAL_VALUE, RegisterMap


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        units: dict[int, RegisterMap] = self.server.units      # type: ignore[attr-defined]
        while True:
            raw = self.request.recv(512)
            if not raw:
                return
            try:
                req = decode_tcp(raw)
            except ModbusError as e:
                self.request.sendall(encode_tcp(0, 0x03, bytes([ILLEGAL_VALUE])))
                continue
            unit = req["unit"]
            table = units.get(unit)
            if table is None:
                self.request.sendall(encode_tcp(unit, req["function"] | 0x80,
                                                bytes([ILLEGAL_ADDRESS]),
                                                req["transaction_id"]))
                continue
            try:
                body = self._dispatch(table, req)
            except ModbusError:
                body = ("EXCEPTION:" + str(ILLEGAL_ADDRESS)).encode()
            if body.startswith(b"EXCEPTION:"):
                code = int(body.split(b":")[1])
                self.request.sendall(encode_tcp(unit, req["function"] | 0x80,
                                                bytes([code]), req["transaction_id"]))
            else:
                self.request.sendall(encode_tcp(unit, req["function"], body,
                                                req["transaction_id"]))

    @staticmethod
    def _dispatch(table: RegisterMap, req: dict) -> bytes:
        fn, data = req["function"], req["data"]
        if fn == 0x03:
            return table.read_holding(int.from_bytes(data[0:2], "big"),
                                      int.from_bytes(data[2:4], "big"))
        if fn == 0x04:
            return table.read_input(int.from_bytes(data[0:2], "big"),
                                    int.from_bytes(data[2:4], "big"))
        if fn == 0x06:
            return table.write_single(int.from_bytes(data[0:2], "big"),
                                      int.from_bytes(data[2:4], "big"))
        if fn == 0x10:
            count = int.from_bytes(data[2:4], "big")
            values = [int.from_bytes(data[4 + i * 2:6 + i * 2], "big") for i in range(count)]
            return table.write_multiple(int.from_bytes(data[0:2], "big"), values)
        return ("EXCEPTION:" + str(ILLEGAL_FUNCTION)).encode()


class ModbusTcpServer:
    def __init__(self, units: dict[int, RegisterMap], host: str = "127.0.0.1", port: int = 0):
        self.units = units
        self.server = socketserver.ThreadingTCPServer((host, port), _Handler)
        self.server.daemon_threads = True
        self.server.units = units                       # type: ignore[attr-defined]
        self.port = self.server.server_address[1]
        self._thread: threading.Thread | None = None

    def serve_forever_in_thread(self) -> "ModbusTcpServer":
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
