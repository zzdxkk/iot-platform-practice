"""工单存储与 SLA：优先级、到期时间、超时判定、JSONL 持久化。"""
import json
import os
from dataclasses import dataclass, asdict, field

SLA_HOURS = {"P1": 1, "P2": 4, "P3": 24}
PRIORITY_BY_INTENT = {"complaint": "P1", "refund": "P2", "aftersale": "P2"}


@dataclass
class Ticket:
    ticket_id: str
    intent: str
    priority: str
    created_at: float
    summary: str = ""
    status: str = "open"
    due_at: float = 0.0
    closed_at: float = 0.0
    tags: list = field(default_factory=list)

    def __post_init__(self):
        if not self.due_at:
            self.due_at = self.created_at + SLA_HOURS[self.priority] * 3600

    def breach(self, now: float) -> bool:
        return self.closed_at > 0 and self.closed_at > self.due_at or \
            self.closed_at == 0 and now > self.due_at


class TicketStore:
    def __init__(self, path: str | None = None):
        self.path = path
        self.tickets: dict[str, Ticket] = {}
        self._n = 0
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        t = Ticket(**json.loads(line))
                        self.tickets[t.ticket_id] = t
                        self._n = max(self._n, int(t.ticket_id[1:]))

    def create(self, intent: str, summary: str, now: float,
               priority: str | None = None, tags=None) -> Ticket:
        self._n += 1
        prio = priority or PRIORITY_BY_INTENT.get(intent, "P3")
        t = Ticket(f"T{self._n:04d}", intent, prio, now, summary,
                   tags=list(tags or []))
        self.tickets[t.ticket_id] = t
        self._persist(t)
        return t

    def _persist(self, t: Ticket):
        if not self.path:
            return
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")

    def close(self, ticket_id: str, now: float) -> Ticket:
        t = self.tickets[ticket_id]
        if t.status == "closed":
            raise ValueError("工单已关闭")
        t.status, t.closed_at = "closed", now
        return t

    def breached(self, now: float) -> list[Ticket]:
        return sorted([t for t in self.tickets.values() if t.breach(now)],
                      key=lambda t: t.due_at)

    def queue_by_priority(self) -> list[Ticket]:
        return sorted([t for t in self.tickets.values() if t.status == "open"],
                      key=lambda t: (t.priority, t.due_at))
