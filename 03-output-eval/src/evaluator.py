"""应用效果评测：用例集打分（exact / contains / token-F1）-> 汇总 -> 基线对比。"""
import json, statistics
from dataclasses import dataclass, asdict

@dataclass
class Case:
    id: str
    question: str
    reference: str
    answer: str

def exact(c): return 1.0 if c.answer.strip() == c.reference.strip() else 0.0

def contains(c): return 1.0 if c.reference.strip() in c.answer else 0.0

def token_f1(c):
    a, r = set(c.answer), set(c.reference)
    if not a or not r: return 0.0
    p = len(a & r) / len(a); rc = len(a & r) / len(r)
    return 2 * p * rc / (p + rc) if p + rc else 0.0

METRICS = {"exact": exact, "contains": contains, "token_f1": token_f1}

def evaluate(cases, metrics=("exact", "contains", "token_f1")):
    scores = {m: [METRICS[m](c) for c in cases] for m in metrics}
    summary = {m: round(statistics.mean(v), 4) for m, v in scores.items()}
    return {"n": len(cases), "summary": summary,
            "per_case": [{"id": c.id, **{m: round(scores[m][i], 4) for m in metrics}}
                         for i, c in enumerate(cases)]}

def compare(baseline, candidate, metric="token_f1"):
    b = baseline["summary"][metric]; c = candidate["summary"][metric]
    return {"metric": metric, "baseline": b, "candidate": c,
            "delta": round(c - b, 4), "improved": c > b}

if __name__ == "__main__":
    cases = [Case("1", "年假", "5天", "入职满一年有5天年假"),
             Case("2", "报销", "需要发票", "报销需要发票"),
             Case("3", "门禁", "刷卡", "刷身份证进场")]
    base = evaluate(cases)
    better = evaluate([Case("1", "年假", "5天", "5天"), Case("2", "报销", "需要发票", "需要发票"),
                       Case("3", "门禁", "刷卡", "刷卡")])
    print(json.dumps(base, ensure_ascii=False, indent=1))
    print(json.dumps(compare(base, better), ensure_ascii=False))
