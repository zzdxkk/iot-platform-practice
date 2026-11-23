"""多轮对话状态机：槽位抽取、追问、确认、取消、超时转人工。"""
import re
from dataclasses import dataclass, field

NEW, ASKING, CONFIRM, DONE, HANDOFF, CANCELLED = (
    "new", "asking", "confirm", "done", "handoff", "cancelled")

SLOTS = {
    "order_id": re.compile(r"(?:订单|单号)\s*(?:是|为|:|：)?\s*([A-Za-z0-9]{6,20})"),
    "phone": re.compile(r"1[3-9]\d{9}"),
    "reason": re.compile(r"(?:原因|因为|由于)\s*(.{2,20})"),
}

QUESTIONS = {
    "order_id": "请提供订单号（字母/数字 6–20 位）。",
    "phone": "请提供下单手机号（11 位）。",
    "reason": "能说下具体原因吗？例如：尺寸不合适、质量问题。",
}


@dataclass
class Session:
    session_id: str
    intent: str
    required: list
    slots: dict = field(default_factory=dict)
    state: str = NEW
    turns: int = 0
    max_turns: int = 6
    transcript: list = field(default_factory=list)


class Dialogue:
    def __init__(self, session: Session):
        self.s = session

    def missing(self) -> list[str]:
        return [k for k in self.s.required if k not in self.s.slots]

    def say(self, text: str) -> dict:
        self.s.turns += 1
        self.s.transcript.append({"role": "user", "text": text})
        if self.s.state in (DONE, CANCELLED, HANDOFF):
            return self._reply("该会话已结束，如需继续请重新发起。", final=True)
        if text.strip() in ("取消", "不用了", "算了"):
            self.s.state = CANCELLED
            return self._reply("已为您取消本次申请。", final=True)
        for key, pat in SLOTS.items():
            if key in self.s.required and key not in self.s.slots:
                m = pat.search(text)
                if m:
                    self.s.slots[key] = m.group(1).strip() if m.groups() else m.group()
        missing = self.missing()
        if missing:
            self.s.state = ASKING
            if self.s.turns >= self.s.max_turns:
                self.s.state = HANDOFF
                return self._reply("已转接人工客服，请稍候。", handoff=True)
            return self._reply(QUESTIONS[missing[0]] + f"（还需 {len(missing)} 项）")
        if self.s.state != CONFIRM:
            self.s.state = CONFIRM
            return self._reply("信息已收到：" + "，".join(
                f"{k}={v}" for k, v in self.s.slots.items()) + "。确认提交吗？")
        if text.strip() in ("确认", "是", "好", "可以"):
            self.s.state = DONE
            return self._reply("已提交，工单会在承诺时效内处理。", final=True)
        self.s.state = ASKING
        return self._reply("请回复“确认”提交，或“取消”放弃。")

    def _reply(self, text, final=False, handoff=False):
        self.s.transcript.append({"role": "bot", "text": text})
        return {"state": self.s.state, "reply": text, "slots": dict(self.s.slots),
                "final": final, "handoff": handoff}
