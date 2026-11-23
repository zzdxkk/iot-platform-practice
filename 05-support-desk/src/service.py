"""客服编排：意图识别 -> FAQ 应答 / 建单 -> 多轮追问 -> 转人工。"""
from dialogue import Dialogue, Session
from intent import classify, route
from tickets import SLA_HOURS, TicketStore

FAQ = {
    "faq": {"多久": "一般 48 小时内发出，偏远地区顺延 1–2 天。",
            "发票": "下单后在“我的订单”里申请电子发票，1 个工作日内开出。",
            "运费": "单笔满 99 元包邮，未满收 8 元运费。"},
}

REQUIRED_SLOTS = {"refund": ["order_id", "reason"], "aftersale": ["order_id"]}


class Service:
    def __init__(self, store: TicketStore, now_fn=None):
        self.store = store
        self.now = now_fn or (lambda: 0.0)

    def handle(self, text: str, sentiment: float = 0.0) -> dict:
        intent = classify(text)
        target = route(intent, sentiment)
        out = {"text": text, "intent": intent.name, "score": intent.score,
               "route": target, "matched": intent.matched}
        if intent.name == "unknown":
            out["reply"] = "没太理解您的意思，可以换个说法，或直接转人工。"
            out["handoff"] = False
            return out
        if target.startswith("bot") and intent.name == "faq":
            for kw, ans in FAQ["faq"].items():
                if kw in text:
                    out["reply"] = ans
                    return out
            out["reply"] = "请提供更具体的问题关键词（多久/发票/运费）。"
            return out
        # 需要建单的意图：立即落工单，再进多轮补槽位
        t = self.store.create(intent.name, text[:60], self.now())
        if intent.name == "complaint":
            # 投诉不等槽位，先落单再转人工，避免客户在机器人里绕圈
            out.update({"ticket_id": t.ticket_id, "priority": t.priority,
                        "sla_due_at": t.due_at, "dialogue": None, "handoff": True,
                        "reply": f"已记录投诉并转接人工客服（工单 {t.ticket_id}，"
                                 f"{t.priority}，{SLA_HOURS[t.priority]} 小时内响应）。"})
            return out
        sess = Session(session_id=t.ticket_id, intent=intent.name,
                       required=REQUIRED_SLOTS.get(intent.name, []))
        reply = Dialogue(sess).say(text)
        out.update({"ticket_id": t.ticket_id, "priority": t.priority,
                    "sla_due_at": t.due_at, "dialogue": reply,
                    "reply": reply["reply"], "handoff": reply["handoff"] or
                    (not sess.required and target.startswith("human"))})
        return out
