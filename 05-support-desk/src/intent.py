"""意图识别：关键词加权 + 字符 n-gram 相似度，输出置信度与兜底。"""
import re
from dataclasses import dataclass

# 意图 -> (关键词权重, 优先级)；优先级数字越小越紧急
INTENTS = {
    "complaint": ({"投诉": 3, "差评": 3, "太慢": 2, "坏": 2, "退钱": 2, "客服态度": 3}, 1),
    "refund": ({"退款": 3, "退钱": 2, "退货": 2, "不想要": 2}, 2),
    "presale": ({"咨询": 1, "多少钱": 2, "价格": 2, "能不能": 1, "咨询一下": 2}, 4),
    "aftersale": ({"保修": 2, "维修": 2, "换新": 2, "装不上": 2, "怎么用": 1}, 3),
    "faq": ({"多久": 2, "发票": 2, "运费": 2, "地址": 1, "时间": 1}, 5),
}


@dataclass
class Intent:
    name: str
    score: float
    priority: int
    matched: list


def _ngrams(text: str, n: int = 2) -> set[str]:
    clean = re.sub(r"\s+", "", text)
    return {clean[i:i + n] for i in range(len(clean) - n + 1)}


def classify(text: str, min_score: float = 2.0) -> Intent:
    best = Intent("unknown", 0.0, 9, [])
    grams = _ngrams(text)
    for name, (keywords, prio) in INTENTS.items():
        score, matched = 0.0, []
        for kw, w in keywords.items():
            if kw in text:
                score += w
                matched.append(kw)
        # 词面没整体命中时按单字覆盖率给部分分，避免"我要退"这类省略说法直接丢失
        if score == 0:
            chars = set(text)
            for kw in keywords:
                kwc = set(kw)
                ov = len(kwc & chars) / len(kwc)
                if ov >= 0.5:
                    score += 0.6 * ov
                    matched.append(kw + "*")
        if score > best.score:
            best = Intent(name, score, prio, matched)
    if best.score < min_score:      # 权重 2 以上的关键词算有效命中
        return Intent("unknown", best.score, 9, best.matched)
    return Intent(best.name, round(best.score, 3), best.priority, best.matched)


def route(intent: Intent, sentiment: float = 0.0) -> str:
    """投诉或负面情绪直接转人工，其余按意图分技能组。"""
    if intent.name == "complaint" or sentiment <= -0.6:
        return "human:complaint"
    return {"refund": "human:refund", "aftersale": "human:aftersale",
            "presale": "bot:sales", "faq": "bot:faq"}.get(intent.name, "bot:general")
