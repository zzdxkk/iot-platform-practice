"""评测执行：跑系统、聚合指标、置信区间、显著性对比、门禁判定。"""
from metrics import score_case
from stats import bootstrap_ci, mean, paired_bootstrap, sign_test


class Runner:
    def __init__(self, cases: list[dict]):
        self.cases = cases

    def run(self, system_fn, name: str = "system") -> dict:
        rows = []
        for case in self.cases:
            pred = system_fn(case["input"])
            rows.append({"id": case["id"], "pred": pred,
                         "scores": score_case(pred, case)})
        keys = sorted({k for r in rows for k in r["scores"]})
        per_metric = {k: [r["scores"].get(k, 0.0) for r in rows] for k in keys}
        agg = {k: {"mean": round(mean(v), 4), "ci": bootstrap_ci(v)}
               for k, v in per_metric.items()}
        return {"name": name, "rows": rows, "metrics": per_metric, "agg": agg}

    def compare(self, a: dict, b: dict, metric: str = "f1") -> dict:
        """a、b 为两次 run 结果；按 metric 做配对检验。"""
        xs, ys = a["metrics"][metric], b["metrics"][metric]
        wins = sum(1 for x, y in zip(xs, ys) if x > y)
        losses = sum(1 for x, y in zip(xs, ys) if x < y)
        return {"metric": metric, "a": a["name"], "b": b["name"],
                "delta": paired_bootstrap(xs, ys),
                "wins": wins, "losses": losses, "sign_p": sign_test(wins, losses)}

    def gate(self, result: dict, thresholds: dict) -> dict:
        checks = {m: {"value": result["agg"][m]["mean"], "min": t,
                      "ok": result["agg"][m]["mean"] >= t}
                  for m, t in thresholds.items() if m in result["agg"]}
        return {"passed": all(c["ok"] for c in checks.values()), "checks": checks}

    def worst(self, result: dict, metric: str, k: int = 3) -> list[dict]:
        rows = sorted(result["rows"], key=lambda r: r["scores"].get(metric, 0))[:k]
        return [{"id": r["id"], metric: r["scores"].get(metric, 0)} for r in rows]
