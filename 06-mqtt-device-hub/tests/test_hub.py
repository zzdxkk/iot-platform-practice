import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from broker import Broker
from codec import (CodecError, decode_packet, decode_remaining_length,
                   encode_connect, encode_connack, encode_pingreq, encode_publish,
                   encode_suback, encode_subscribe, encode_remaining_length)
from topic import matches, validate_filter, validate_topic


class TestRemainingLength(unittest.TestCase):
    def test_roundtrip_values(self):
        for n in (0, 1, 127, 128, 16383, 16384, 2097151, 268435455):
            self.assertEqual(decode_remaining_length(encode_remaining_length(n), 0)[0], n)
    def test_overflow(self):
        with self.assertRaises(CodecError):
            encode_remaining_length(268435456)
    def test_truncated(self):
        with self.assertRaises(CodecError):
            decode_remaining_length(bytes([0x30, 0x80]), 1)


class TestCodec(unittest.TestCase):
    def test_connect_roundtrip(self):
        raw = encode_connect("dev-1", clean_session=False, keepalive=45,
                             username="u", password="secret")
        d = decode_packet(raw)
        self.assertEqual((d["type"], d["client_id"], d["keepalive"]), ("CONNECT", "dev-1", 45))
        self.assertFalse(d["clean_session"])
        self.assertEqual((d["username"], d["password"]), ("u", "secret"))
    def test_connack(self):
        d = decode_packet(encode_connack(0, session_present=True))
        self.assertEqual((d["type"], d["return_code"], d["session_present"]), ("CONNACK", 0, True))
    def test_publish_qos0(self):
        d = decode_packet(encode_publish("a/b", "hi", retain=True))
        self.assertEqual((d["topic"], d["qos"], d["retain"], d["payload"]), ("a/b", 0, True, b"hi"))
    def test_publish_qos1_needs_packet_id(self):
        with self.assertRaises(CodecError):
            encode_publish("a/b", "hi", qos=1)
    def test_publish_qos1_roundtrip(self):
        d = decode_packet(encode_publish("a/b", b"\x00\x01", qos=1, packet_id=99, dup=True))
        self.assertEqual((d["qos"], d["packet_id"], d["dup"]), (1, 99, True))
        self.assertEqual(d["payload"], b"\x00\x01")
    def test_subscribe_roundtrip(self):
        d = decode_packet(encode_subscribe([("a/+", 1), ("b/#", 0)], 5))
        self.assertEqual(d["packet_id"], 5)
        self.assertEqual(d["topics"], [("a/+", 1), ("b/#", 0)])
        self.assertEqual(d["flags"], 0x02)
    def test_suback(self):
        self.assertEqual(decode_packet(encode_suback(5, [0, 0x80]))["codes"], [0, 0x80])
    def test_ping(self):
        self.assertEqual(decode_packet(encode_pingreq())["type"], "PINGREQ")
    def test_short_packet(self):
        with self.assertRaises(CodecError):
            decode_packet(b"\x30")
    def test_unknown_type(self):
        with self.assertRaises(CodecError):
            decode_packet(b"\xf0\x00")


class TestTopic(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(matches("a/b/c", "a/b/c"))
        self.assertFalse(matches("a/b/c", "a/b"))
    def test_plus(self):
        self.assertTrue(matches("dev/+/temp", "dev/1/temp"))
        self.assertFalse(matches("dev/+/temp", "dev/1/2/temp"))
    def test_hash(self):
        self.assertTrue(matches("dev/#", "dev/1/temp"))
        self.assertTrue(matches("#", "any/thing"))
    def test_dollar_sys_excluded(self):
        self.assertFalse(matches("#", "$SYS/broker/uptime"))
        self.assertTrue(matches("$SYS/#", "$SYS/broker/uptime"))
    def test_bad_filters(self):
        for bad in ("a/#/b", "a#", "a/+b", ""):
            with self.assertRaises(CodecError):
                validate_filter(bad)
    def test_publish_topic_no_wildcard(self):
        with self.assertRaises(CodecError):
            validate_topic("a/+")


class TestBroker(unittest.TestCase):
    def setUp(self):
        self.b = Broker()
        self.b.connect("c1")
        self.b.subscribe("c1", [("dev/+/temp", 1)])

    def test_route_and_poll(self):
        self.b.publish("dev/9/temp", "21.0", qos=1, packet_id=11)
        msgs = self.b.poll("c1")
        self.assertEqual(msgs[0]["topic"], "dev/9/temp")
        self.assertEqual(msgs[0]["qos"], 1)
        self.assertEqual(msgs[0]["packet_id"], 11)
    def test_not_subscribed_no_delivery(self):
        self.b.publish("other/9/temp", "x", qos=1, packet_id=12)
        self.assertEqual(self.b.poll("c1"), [])
    def test_retained_on_new_subscriber(self):
        self.b.publish("dev/1/temp", "19.5", retain=True)
        self.b.connect("c2")
        self.b.subscribe("c2", [("dev/1/+", 0)])
        msgs = self.b.poll("c2")
        self.assertEqual((msgs[0]["payload"], msgs[0]["retain"]), (b"19.5", True))
    def test_empty_payload_clears_retained(self):
        self.b.publish("dev/1/temp", "x", retain=True)
        self.b.publish("dev/1/temp", b"", retain=True)
        self.assertNotIn("dev/1/temp", self.b.retained)
    def test_offline_queue_after_disconnect(self):
        b = Broker()
        b.connect("p1", clean_session=False)     # 持久会话才有离线队列
        b.subscribe("p1", [("dev/+/temp", 1)])
        b.disconnect("p1")
        b.publish("dev/9/temp", "x", qos=1)
        self.assertEqual(len(b.sessions["p1"].queue), 1)
    def test_qos1_duplicate_dropped(self):
        r1 = self.b.accept_publish("c1", "dev/9/temp", "x", qos=1, packet_id=3)
        r2 = self.b.accept_publish("c1", "dev/9/temp", "x", qos=1, packet_id=3)
        self.assertFalse(r1["duplicate"])
        self.assertTrue(r2["duplicate"])
        self.assertEqual(r2["delivered"], [])
    def test_subscribe_bad_filter_code(self):
        codes = self.b.subscribe("c1", [("x/#/y", 0), ("ok/+", 0)])
        self.assertEqual(codes, [0x80, 0x00])
    def test_clean_session_drops_state(self):
        self.b.disconnect("c1")
        self.assertNotIn("c1", self.b.sessions)
    def test_persistent_session_keeps_subs(self):
        b = Broker()
        b.connect("p1", clean_session=False)
        b.subscribe("p1", [("a/b", 1)])
        b.disconnect("p1")
        b.connect("p1", clean_session=False)
        self.assertIn("a/b", b.sessions["p1"].subs)
    def test_shadow_delta(self):
        self.b.set_reported({"power": "on", "mode": "auto"})
        self.b.set_desired({"power": "on", "mode": "manual"})
        self.assertEqual(self.b.delta(), {"mode": "manual"})
    def test_wire_roundtrip(self):
        msg = {"topic": "dev/1/temp", "payload": b"1", "qos": 1, "retain": True,
               "packet_id": 2}
        d = decode_packet(self.b.to_wire(msg))
        self.assertEqual((d["topic"], d["packet_id"], d["retain"]), ("dev/1/temp", 2, True))


if __name__ == "__main__":
    unittest.main()
