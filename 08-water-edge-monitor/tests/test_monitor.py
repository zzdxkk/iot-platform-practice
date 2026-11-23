import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from detect import ALARM, NORMAL, WARNING, Cusum, Ewma, LeakDetector, rolling_std
from monitor import EdgeMonitor, replay
from packet import (FLAG_ALARM, FLAG_LOW_BATTERY, PacketError, SIZE, crc8, decode,
                    encode, uplink_bytes)
from power import PowerProfile, budget


class TestEwma(unittest.TestCase):
    def test_warmup_blocks(self):
        e = Ewma(alpha=0.2, warmup=3)
        self.assertIsNone(e.update(10))
        self.assertFalse(e.ready)
    def test_follows_slowly(self):
        e = Ewma(alpha=0.2, warmup=2)
        for v in (10, 10, 10, 20):
            e.update(v)
        self.assertTrue(e.ready)
        self.assertTrue(10 < e.value < 20)
    def test_rolling_std(self):
        self.assertEqual(rolling_std([1, 1, 1]), 0.0)
        self.assertAlmostEqual(rolling_std([0, 2, 4]), 2.0, places=6)


class TestCusum(unittest.TestCase):
    def test_detects_sustained_shift(self):
        c = Cusum(target=0, k=0.5, h=3)
        hits = [c.update(2.0)[0] for _ in range(5)]
        self.assertTrue(any(hits))
    def test_ignores_small_offset(self):
        c = Cusum(target=0, k=0.5, h=3)
        self.assertFalse(any(c.update(0.3)[0] for _ in range(10)))
    def test_detects_downward(self):
        c = Cusum(target=0, k=0.5, h=3)
        self.assertTrue(any(c.update(-2.0)[1] for _ in range(4)))


class TestDetector(unittest.TestCase):
    def feed(self, det, values, start=0):
        return [det.update(start + i, v) for i, v in enumerate(values)]

    def test_quiet_series_no_event(self):
        det = LeakDetector(sigma=0.6, confirm_n=2, cooldown=5)
        vals = [3.0, 2.9, 3.1, 3.0, 2.8, 3.2, 3.0, 3.1] * 3
        self.assertEqual(self.feed(det, vals), [None] * len(vals))
    def test_step_up_alarms(self):
        det = LeakDetector(sigma=0.6, alarm_z=3.5, confirm_n=2, cooldown=5)
        vals = [3.0, 2.9, 3.1, 3.0, 2.9, 3.1, 3.0, 3.0, 3.1, 3.0, 3.0] + [6.0] * 4
        events = [e for e in self.feed(det, vals) if e]
        self.assertTrue(events)
        self.assertEqual(events[0].level, ALARM)
    def test_single_spike_suppressed(self):
        det = LeakDetector(sigma=0.6, alarm_z=3.5, confirm_n=2, cooldown=5)
        vals = [3.0] * 12 + [9.0] + [3.0] * 5
        self.assertEqual([e for e in self.feed(det, vals) if e], [])
    def test_cooldown_suppresses_repeats(self):
        det = LeakDetector(sigma=0.6, alarm_z=3.0, confirm_n=1, cooldown=10)
        vals = [3.0] * 10 + [8.0] * 8
        events = [e for e in self.feed(det, vals) if e]
        self.assertEqual(len(events), 1, "冷却窗口内不应重复报警")


class TestPower(unittest.TestCase):
    def test_daily_mah_components(self):
        p = PowerProfile(sleep_ua=0, measure_ma=0, tx_ma=0, tx_s=0,
                         measures_per_day=0, reports_per_day=0)
        self.assertEqual(p.daily_mah(), 0.0)
    def test_daily_mah_reasonable(self):
        p = PowerProfile()
        self.assertTrue(0 < p.daily_mah() < 5)
    def test_life_days(self):
        p = PowerProfile()
        self.assertGreater(p.life_days(2500), 365)
    def test_target_check(self):
        p = PowerProfile(sleep_ua=500, measure_ma=20, tx_ma=80, measures_per_day=96)
        r = budget(p, 1200, 3)
        self.assertFalse(r["ok"])
        self.assertLess(r["life_days"], r["target_days"])


class TestPacket(unittest.TestCase):
    def test_roundtrip(self):
        pkt = encode(1, 2, 4.25, 3650, "alarm")
        d = decode(pkt)
        self.assertEqual((d["seq"], d["value"], d["level"]), (2, 4.25, "alarm"))
        self.assertEqual(d["flags"] & FLAG_ALARM, FLAG_ALARM)
    def test_low_battery_flag(self):
        self.assertTrue(decode(encode(1, 1, 3, 2700))["low_battery"])
        self.assertFalse(decode(encode(1, 1, 3, 3600))["low_battery"])
    def test_crc_corruption(self):
        pkt = encode(1, 1, 3.0, 3600)
        with self.assertRaises(PacketError):
            decode(pkt[:-1] + bytes([pkt[-1] ^ 0x01]))
    def test_wrong_length(self):
        with self.assertRaises(PacketError):
            decode(b"\x02" * (SIZE - 1))
    def test_value_range(self):
        with self.assertRaises(PacketError):
            encode(1, 1, 400.0, 3600)
    def test_device_id_range(self):
        with self.assertRaises(PacketError):
            encode(2 ** 32, 1, 1.0, 3600)
    def test_size(self):
        self.assertEqual(len(encode(1, 1, 1.0, 3600)), SIZE)
    def test_crc8_known(self):
        self.assertEqual(crc8(b"123456789"), 0xF4)


class TestMonitor(unittest.TestCase):
    def test_run_counts(self):
        m = EdgeMonitor(device_id=1)
        r = m.run([{"ts": i, "value": v} for i, v in
                   enumerate([3.0] * 10 + [3.1, 3.0] + [7.0] * 4)])
        self.assertGreaterEqual(r["alarms"], 1)
        self.assertEqual(r["packets"], 16)
    def test_last_packet_decodes(self):
        m = EdgeMonitor(device_id=0x10, battery_mv=3500)
        m.run([{"ts": 0, "value": 3.0}, {"ts": 1, "value": 3.1}])
        d = m.last_packet()
        self.assertEqual((d["device_id"], d["seq"]), (0x10, 2))
    def test_replay_isolates_bad_packet(self):
        good = encode(1, 1, 2.0, 3600)
        bad = b"\x00" * (SIZE - 1) + b"\x01"        # CRC 位被改坏
        self.assertEqual(replay([good, bad])[1]["error"], "CRC8 校验失败")
    def test_uplink_compression_ratio(self):
        text, bin_size = uplink_bytes([{"ts": 0, "value": 3.0, "seq": 1}] * 10)
        self.assertGreater(text, bin_size)


if __name__ == "__main__":
    unittest.main()
