"""内容审核：分级规则（block/review/pass）、命中行号、PII 脱敏。"""
import re
from dataclasses import dataclass

BLOCK, REVIEW, PASS = "block", "review", "pass"


@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    tier: str
    reason: str


DEFAULT_RULES = [
    Rule("联系方式", re.compile(r"1[3-9]\d{9}|[\w.+-]+@[\w-]+\.[\w.]+"), REVIEW,
         "疑似手机号/邮箱，需人工确认"),
    Rule("绝对化用语", re.compile(r"(最好|第一|百分百|绝对|永久有效|包治)"), REVIEW,
         "广告法风险词"),
    Rule("诱导交易", re.compile(r"(私下转账|加微信付款|先付定金到个人)"), BLOCK,
         "绕过平台的交易引导"),
    Rule("违法内容", re.compile(r"(赌博|博彩|代开发票)"), BLOCK, "明确违规"),
]


def redact(text: str) -> str:
    t = re.sub(r"1[3-9]\d{9}", lambda m: m.group()[:3] + "****" + m.group()[-4:], text)
    t = re.sub(r"([\w.+-]+)@([\w-]+\.[\w.]+)", r"\1***@\2", t)
    return t


def scan(text: str, rules=None, min_len: int = 5) -> dict:
    rules = DEFAULT_RULES if rules is None else rules
    hits = [{"rule": r.name, "tier": r.tier, "reason": r.reason,
             "matched": m.group()} for r in rules for m in r.pattern.finditer(text)]
    if any(h["tier"] == BLOCK for h in hits):      # 阻断优先级最高，短文本也不例外
        verdict = BLOCK
    elif len(text.strip()) < min_len:
        verdict = REVIEW
    elif any(h["tier"] == REVIEW for h in hits):
        verdict = REVIEW
    else:
        verdict = PASS
    return {"verdict": verdict, "hits": hits,
            "redacted": redact(text) if hits else text}


def publishable(result: dict) -> bool:
    return result["verdict"] != BLOCK
