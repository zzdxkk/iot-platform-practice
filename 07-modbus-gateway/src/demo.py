"""演示：RTU/TCP 帧编解码、CRC、寄存器服务端与客户端、异常码、批量轮询。"""
from client import ModbusTcpClient
from codec import (ModbusError, ModbusExceptionResponse, build_read_holding, crc16,
                   decode_rtu, decode_tcp, encode_rtu)
from registers import RegisterMap
from server import ModbusTcpServer


def main():
    print("== RTU 帧与 CRC ==")
    frame = encode_rtu(1, 0x03, b"\x00\x00\x00\x0a")
    print("  请求帧 hex：", frame.hex(), "（CRC=%04X）" % crc16(frame[:-2]))
    print("  解码：", decode_rtu(frame))
    broken = frame[:-1] + bytes([frame[-1] ^ 0xFF])
    try:
        decode_rtu(broken)
    except ModbusError as e:
        print("  篡改 1 字节：", e)

    print("\n== TCP 报文（MBAP）==")
    tcp = build_read_holding(2, 10, 3, transaction_id=42)
    print("  hex：", tcp.hex(), "->", decode_tcp(tcp))

    print("\n== 服务端/客户端 ==")
    units = {1: RegisterMap(hold={10: 100, 11: 200, 12: 300}, input_={0: 42}),
             2: RegisterMap(hold={10: 7, 11: 8, 12: 9})}
    srv = ModbusTcpServer(units).serve_forever_in_thread()
    c = ModbusTcpClient(port=srv.port)
    print(f"  监听 127.0.0.1:{srv.port}")
    print("  从站1 读 10..12：", c.read_holding(1, 10, 3))
    print("  写 11=250 后读：", c.write_single(1, 11, 250), c.read_holding(1, 11, 1))
    print("  批量轮询 1/2：", c.poll([1, 2], 10, 3))

    for desc, fn in [
        ("非法地址 99", lambda: c.read_holding(1, 99, 1)),
        ("读数量 0", lambda: c.read_holding(1, 10, 0)),
        ("不存在的从站 9", lambda: c.read_holding(9, 10, 1)),
    ]:
        try:
            fn()
            print(f"  {desc}: 未抛错（不符合预期）")
        except ModbusExceptionResponse as e:
            print(f"  {desc}: {e} — 0x{e.code:02X}")
        except ModbusError as e:
            print(f"  {desc}: {e}")

    print("  寄存器写入计数：", {u: t.writes for u, t in units.items()})
    srv.stop()


if __name__ == "__main__":
    main()
