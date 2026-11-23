"""演示：意图识别与路由、多轮补槽位、工单 SLA 与超时。"""
import os
import tempfile

from dialogue import Dialogue, Session
from intent import classify, route
from service import Service
from tickets import TicketStore

MESSAGES = [
    ("我要投诉，订单 A1234567 太慢了", "complaint"),
    ("这个能退款吗", "refund"),
    ("大概多久发货", "faq"),
    ("您好", "unknown"),
]


def main():
    print("== 意图识别与路由 ==")
    for text, expect in MESSAGES:
        it = classify(text)
        print(f"  {text!r:34} -> {it.name:9} score={it.score:4} "
              f"route={route(it, -0.8 if '投诉' in text else 0)} (期望 {expect})")

    store = TicketStore(os.path.join(tempfile.mkdtemp(), "tickets.jsonl"))
    svc = Service(store, now_fn=lambda: 100.0)

    print("\n== 多轮补槽位 ==")
    first = svc.handle("我要退款")
    print("  首轮：", first["reply"], "| 工单", first["ticket_id"], first["priority"])
    sess = Session(first["ticket_id"], "refund", ["order_id", "reason"])
    d = Dialogue(sess)
    print("  用户：我的订单是 A1234567")
    print("  客服：", d.say("我的订单是 A1234567")["reply"])
    print("  用户：因为尺寸不合适")
    print("  客服：", d.say("因为尺寸不合适")["reply"])
    print("  用户：确认")
    print("  客服：", d.say("确认")["reply"], "| 终态", sess.state)

    print("\n== 工单与 SLA ==")
    t = store.create("complaint", "投诉发货慢", 100.0)
    print(f"  {t.ticket_id} 优先级 {t.priority} 到期 {t.due_at}（{t.priority} = 1 小时）")
    print("  未处理是否超时：", t.breach(100.0 + 3601))
    store.close(t.ticket_id, 100.0 + 1800)
    print("  半小时内关闭后是否超时：", t.breach(100.0 + 7200))
    late = store.create("aftersale", "保修咨询", 100.0, priority="P3")
    store.close(late.ticket_id, 100.0 + 25 * 3600)
    print("  超时工单列表：", [x.ticket_id for x in store.breached(100.0 + 30 * 3600)])
    print("  待处理队列（按优先级）：", [(x.ticket_id, x.priority)
                                       for x in store.queue_by_priority()])

    print("\n== 追问超限转人工 ==")
    s2 = Session("S9", "refund", ["order_id"], max_turns=2)
    d2 = Dialogue(s2)
    print("  ", d2.say("不知道单号")["reply"])
    print("  ", d2.say("还是不知道")["reply"], "| 状态", s2.state)


if __name__ == "__main__":
    main()
