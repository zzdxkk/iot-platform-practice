"""Markdown 报告：指标表 + 最差样本 + 对比结论。"""
def table(results: list[dict]) -> str:
    metrics = sorted({m for r in results for m in r["agg"]})
    head = "| 系统 | " + " | ".join(metrics) + " |"
    sep = "|" + "---|" * (len(metrics) + 1)
    body = []
    for r in results:
        cells = []
        for m in metrics:
            a = r["agg"].get(m)
            cells.append(f"{a['mean']:.3f} [{a['ci'][0]:.3f},{a['ci'][1]:.3f}]" if a else "-")
        body.append(f"| {r['name']} | " + " | ".join(cells) + " |")
    return "\n".join([head, sep] + body)


def render(results, gates=None, comparisons=None, worst=None) -> str:
    out = ["# 评测报告", "", "样本数：" + str(len(results[0]["rows"])), "", table(results)]
    if gates:
        out += ["", "## 门禁", ""]
        for g in gates:
            out.append(f"- {'通过' if g['passed'] else '未通过'}：" + "，".join(
                f"{m}={c['value']:.3f} (>= {c['min']})" for m, c in g["checks"].items()))
    if comparisons:
        out += ["", "## 对比", ""]
        for c in comparisons:
            out.append(f"- {c['a']} vs {c['b']}（{c['metric']}）："
                       f"Δ={c['delta']['delta']:+.3f} "
                       f"CI=[{c['delta']['ci'][0]:+.3f},{c['delta']['ci'][1]:+.3f}] "
                       f"p={c['delta']['p']:.4f}；胜负 {c['wins']}:{c['losses']}，"
                       f"符号检验 p={c['sign_p']:.4f}")
    if worst:
        out += ["", "## 最差样本", ""]
        for w in worst:
            out.append(f"- {w}")
    return "\n".join(out) + "\n"
