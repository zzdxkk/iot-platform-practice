import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from dialogue import CANCELLED, CONFIRM, DONE, HANDOFF, Dialogue, Session
from intent import classify, route
from service import Service
from tickets import Ticket, TicketStore


class TestIntent(unittest.TestCase):
    def test_complaint_wins(self):
        it = classify("我要投诉，太差了")
        self.assertEqual(it.name, "complaint")
        self.assertEqual(it.priority, 1)
    def test_refund(self):
        self.assertEqual(classify("我想退款").name, "refund")
    def test_faq(self):
        self.assertEqual(classify("发票怎么开").name, "faq")
    def test_unknown_low_score(self):
        self.assertEqual(classify("你好").name, "unknown")
    def test_partial_char_credit(self):
        # "我要退"没写完整关键词：给部分分但不足以判定意图，同时留下候选线索
        it = classify("我要退")
        self.assertEqual(it.name, "unknown")
        self.assertTrue(any("退款" in m for m in it.matched))
    def test_route_complaint_always_human(self):
        self.assertEqual(route(classify("投诉")), "human:complaint")
    def test_route_negative_sentiment(self):
        self.assertEqual(route(classify("发票怎么开"), sentiment=-0.9), "human:complaint")
    def test_route_faq_bot(self):
        self.assertEqual(route(classify("多久发货")), "bot:faq")


class TestDialogue(unittest.TestCase):
    def make(self, required=("order_id", "reason")):
        sess = Session("S1", "refund", list(required))
        return sess, Dialogue(sess)

    def test_slot_extract_and_ask(self):
        s, d = self.make()
        r = d.say("订单号 A1234567")
        self.assertEqual(s.slots["order_id"], "A1234567")
        self.assertEqual(s.state, "asking")
        self.assertIn("原因", r["reply"])
    def test_confirm_then_done(self):
        s, d = self.make()
        d.say("订单号 A1234567")
        d.say("因为尺寸不合适")
        self.assertEqual(s.state, CONFIRM)
        r = d.say("确认")
        self.assertEqual(s.state, DONE)
        self.assertTrue(r["final"])
    def test_cancel(self):
        s, d = self.make(("order_id",))
        r = d.say("取消")
        self.assertEqual(s.state, CANCELLED)
        self.assertTrue(r["final"])
    def test_max_turns_handoff(self):
        s = Session("S2", "refund", ["order_id"], max_turns=2)
        d = Dialogue(s)
        d.say("不知道")
        r = d.say("还是不知道")
        self.assertEqual(s.state, HANDOFF)
        self.assertTrue(r["handoff"])
    def test_finished_session_rejects(self):
        s, d = self.make(("order_id",))
        d.say("订单号 A1234567")
        d.say("确认")
        self.assertIn("已结束", d.say("再问一句")["reply"])
    def test_phone_regex(self):
        s, d = self.make(("phone",))
        d.say("13800138000")
        self.assertEqual(s.slots["phone"], "13800138000")


class TestTickets(unittest.TestCase):
    def test_sla_by_priority(self):
        t = Ticket("T1", "complaint", "P1", 100.0)
        self.assertEqual(t.due_at, 100.0 + 3600)
    def test_breach_open(self):
        t = Ticket("T1", "refund", "P2", 0.0)
        self.assertTrue(t.breach(5 * 3600))
        self.assertFalse(t.breach(3 * 3600))
    def test_breach_closed_in_time(self):
        t = Ticket("T1", "refund", "P2", 0.0)
        t.closed_at = 3600
        self.assertFalse(t.breach(10**9))
    def test_breach_closed_late(self):
        t = Ticket("T1", "refund", "P2", 0.0)
        t.closed_at = 5 * 3600
        self.assertTrue(t.breach(10**9))
    def test_store_persist_reload(self):
        p = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        st = TicketStore(p)
        st.create("complaint", "投诉", 0.0)
        st.create("faq", "问", 0.0)
        self.assertEqual(len(TicketStore(p).tickets), 2)
    def test_priority_queue_order(self):
        st = TicketStore()
        st.create("faq", "p3", 0.0)
        st.create("complaint", "p1", 10.0)
        st.create("refund", "p2", 5.0)
        self.assertEqual([t.priority for t in st.queue_by_priority()], ["P1", "P2", "P3"])
    def test_double_close_rejected(self):
        st = TicketStore()
        t = st.create("refund", "x", 0.0)
        st.close(t.ticket_id, 1.0)
        with self.assertRaises(ValueError):
            st.close(t.ticket_id, 2.0)


class TestService(unittest.TestCase):
    def setUp(self):
        self.st = TicketStore()
        self.svc = Service(self.st, now_fn=lambda: 100.0)

    def test_faq_answered_without_ticket(self):
        r = self.svc.handle("发票怎么开")
        self.assertIn("电子发票", r["reply"])
        self.assertEqual(self.st.tickets, {})
    def test_refund_creates_ticket_and_asks(self):
        r = self.svc.handle("我要退款")
        self.assertIn(r["ticket_id"], self.st.tickets)
        self.assertEqual(r["priority"], "P2")
        self.assertIn("订单号", r["reply"])
    def test_unknown_no_ticket(self):
        r = self.svc.handle("你好")
        self.assertEqual(r["intent"], "unknown")
        self.assertFalse(r["handoff"])
    def test_complaint_priority_p1(self):
        r = self.svc.handle("我要投诉，订单 A1234567 拖了一周")
        self.assertEqual(r["priority"], "P1")
        self.assertIn("人工", r["reply"])


if __name__ == "__main__":
    unittest.main()
