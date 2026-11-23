import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from client import ModbusTcpClient
from codec import (ModbusError, ModbusExceptionResponse, build_read_holding,
                   build_write_multiple, build_write_single, crc16, decode_rtu,
                   decode_tcp, encode_rtu)
from registers import RegisterMap
from server import ModbusTcpServer


class TestCRC(unittest.TestCase):
    def test_known_vector(self):
        # 01 03 00 00 00 0A 的 MODBUS CRC 是 0xCDC5
        self.assertEqual(crc16(b"\x01\x03\x00\x00\x00\x0a"), 0xCDC5)
    def test_frame_crc_little_endian(self):
        self.assertEqual(encode_rtu(1, 3, b"\x00\x00\x00\x0a")[-2:], b"\xc5\xcd")


class TestRtu(unittest.TestCase):
    def test_request_roundtrip(self):
        d = decode_rtu(encode_rtu(17, 3, b"\x00\x0a\x00\x03"))
        self.assertEqual((d["slave"], d["function"], d["data"]), (17, 3, b"\x00\x0a\x00\x03"))
    def test_crc_corruption_detected(self):
        f = encode_rtu(1, 3, b"\x00\x01\x00\x01")
        with self.assertRaises(ModbusError):
            decode_rtu(f[:-1] + bytes([f[-1] ^ 0x01]))
    def test_exception_frame(self):
        d = decode_rtu(encode_rtu(1, 0x83, b"\x02"))
        self.assertEqual((d["function"], d["exception"]), (3, 2))
        self.assertIn("非法数据地址", d["text"])
    def test_short_frame(self):
        with self.assertRaises(ModbusError):
            decode_rtu(b"\x01\x03")
    def test_slave_range(self):
        with self.assertRaises(ModbusError):
            encode_rtu(300, 3, b"")


class TestTcpFrames(unittest.TestCase):
    def test_mbap_fields(self):
        f = build_read_holding(5, 100, 2, transaction_id=7)
        self.assertEqual(f[0:2], b"\x00\x07")
        self.assertEqual(f[2:4], b"\x00\x00")
        self.assertEqual(int.from_bytes(f[4:6], "big"), 6)   # unit(1)+pdu(5)
        d = decode_tcp(f)
        self.assertEqual((d["unit"], d["function"]), (5, 3))
        self.assertEqual((int.from_bytes(d["data"][0:2], "big"),
                          int.from_bytes(d["data"][2:4], "big")), (100, 2))
    def test_read_count_limit(self):
        with self.assertRaises(ModbusError):
            build_read_holding(1, 0, 126)
    def test_write_multiple_frame(self):
        d = decode_tcp(build_write_multiple(1, 10, [1, 2, 3]))
        self.assertEqual(d["data"], b"\x00\x0a\x00\x03\x06" + b"\x00\x01\x00\x02\x00\x03")
    def test_write_count_limit(self):
        with self.assertRaises(ModbusError):
            build_write_multiple(1, 0, list(range(124)))
    def test_bad_protocol_id(self):
        with self.assertRaises(ModbusError):
            decode_tcp(b"\x00\x01\x00\x05\x00\x02\x01\x03")


class TestRegisterMap(unittest.TestCase):
    def test_read_holding(self):
        m = RegisterMap(hold={1: 10, 2: 20})
        self.assertEqual(m.read_holding(1, 2), b"\x04\x00\x0a\x00\x14")
    def test_read_input(self):
        self.assertEqual(RegisterMap(input_={0: 7}).read_input(0, 1), b"\x02\x00\x07")
    def test_address_gap_exception(self):
        m = RegisterMap(hold={1: 10})
        self.assertEqual(m.read_holding(1, 2), b"EXCEPTION:2")
    def test_write_single_updates(self):
        m = RegisterMap(hold={5: 0})
        self.assertEqual(m.write_single(5, 300), b"\x00\x05\x01\x2c")
        self.assertEqual(m.holding[5], 300)
    def test_write_value_range(self):
        m = RegisterMap(hold={5: 0})
        self.assertEqual(m.write_single(5, 70000), b"EXCEPTION:3")
    def test_read_count_zero(self):
        self.assertEqual(RegisterMap(hold={1: 1}).read_holding(1, 0), b"EXCEPTION:3")


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.units = {1: RegisterMap(hold={10: 100, 11: 200}, input_={0: 42}),
                     2: RegisterMap(hold={10: 1, 11: 2})}
        cls.srv = ModbusTcpServer(cls.units).serve_forever_in_thread()
        cls.c = ModbusTcpClient(port=cls.srv.port)
    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def test_read_and_write(self):
        self.c.write_single(1, 11, 123)
        self.assertEqual(self.c.read_holding(1, 11, 1), [123])
        self.assertEqual(len(self.c.read_holding(1, 10, 2)), 2)
    def test_illegal_address(self):
        with self.assertRaises(ModbusExceptionResponse) as ctx:
            self.c.read_holding(1, 99, 1)
        self.assertEqual(ctx.exception.code, 0x02)
    def test_unknown_unit(self):
        with self.assertRaises(ModbusExceptionResponse) as ctx:
            self.c.read_holding(9, 10, 1)
        self.assertEqual(ctx.exception.code, 0x02)
    def test_bad_count_rejected_client_side(self):
        # 数量越界在客户端就拦下，不会把非法请求打到从站
        with self.assertRaises(ModbusError):
            self.c.read_holding(1, 10, 0)
    def test_multi_unit_poll(self):
        self.c.write_single(1, 10, 111)
        r = self.c.poll([1, 2, 9], 10, 2)
        self.assertEqual(r[1][0], 111)
        self.assertEqual(r[2], [1, 2])
        self.assertTrue(str(r[9]).startswith("ERR"))     # 坏从站不影响其它从站
    def test_connection_refused(self):
        bad = ModbusTcpClient(port=1, retries=0, timeout=0.2)
        with self.assertRaises(ModbusError):
            bad.read_holding(1, 0, 1)


if __name__ == "__main__":
    unittest.main()
