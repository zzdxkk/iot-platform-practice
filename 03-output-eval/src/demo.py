"""演示：同一批用例上跑两个系统，出门禁结论与显著性对比。"""
import json
import os

from dataset import load_jsonl
from report import render
from runner import Runner

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "..", "data", "eval_cases.jsonl")

ANSWERS = {"年假几天": "5 天", "住宿标准": "500 元", "报销多久到账": "3 个工作日",
           "VPN 连不上": "先检查客户端版本，再重置令牌", "发票丢了": "提交情况说明后可补办"}


def baseline(q):
    """模拟"改之前"的系统：只命中一半关键词，答案不完整。"""
    return ANSWERS[q].split("，")[0][:2] if q in ANSWERS else "未知"


def improved(q):
    return ANSWERS.get(q, "未知")


def main():
    cases = load_jsonl(CASES)
    r = Runner(cases)
    a = r.run(baseline, "baseline")
    b = r.run(improved, "improved")
    gate = r.gate(b, {"f1": 0.6, "contains": 0.5})
    cmp = r.compare(b, a, "f1")
    md = render([a, b], gates=[gate], comparisons=[cmp], worst=r.worst(a, "f1", 2))
    print(md)
    print("门禁通过：", gate["passed"], " 显著性：p=%.4f" % cmp["delta"]["p"])


if __name__ == "__main__":
    main()
