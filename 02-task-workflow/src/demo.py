"""演示：工具注册 + 依赖 DAG 并行执行 + 执行循环 + JSONL 轨迹。"""
import os
import tempfile
import time

from runner import Action, Runner, ScriptedPlanner
from dag import DAG
from tools import Tool, ToolRegistry
from trace import Trace

ORDERS = [{"id": i, "region": "east" if i % 2 else "west", "amount": 100 + i * 10}
          for i in range(1, 7)]


def build_registry():
    reg = ToolRegistry()
    reg.register(Tool("fetch_orders", lambda region: [o for o in ORDERS
                                                      if o["region"] == region],
                      {"region": str}, ("region",), "按区域拉订单"))
    reg.register(Tool("sum_amount", lambda rows: sum(r["amount"] for r in rows),
                      {"rows": list}, ("rows",), "订单金额求和"))
    return reg


def main():
    reg = build_registry()
    print("已注册工具：", reg.names())

    # 1) DAG：两个区域并发拉单，再合并求和
    def fetch(region):
        time.sleep(0.08)
        return [o for o in ORDERS if o["region"] == region]

    def merge(east, west):
        return sum(sum(o["amount"] for o in r) for r in (east, west))

    g = DAG(max_workers=4).add("east", lambda: fetch("east")).add(
        "west", lambda: fetch("west")).add("merge", merge, deps=("east", "west"))
    t0 = time.monotonic()
    res = g.run()
    print("DAG 分层：", g.topo_levels())
    for name, r in res.items():
        print(f"  {name}: {r.status} value={r.value} 用时 {r.elapsed}s")
    print(f"DAG 总耗时 {time.monotonic() - t0:.3f}s（串行至少 0.16s）")

    # 2) 失败传播
    bad = DAG().add("boom", lambda: 1 / 0).add("after", lambda boom: boom, deps=("boom",))
    br = bad.run()
    print("失败传播：", {k: v.status for k, v in br.items()})

    # 3) 执行循环 + 轨迹
    trace_path = os.path.join(tempfile.mkdtemp(), "trace.jsonl")
    planner = ScriptedPlanner([
        Action("fetch_orders", {"region": "east"}),
        Action("sum_amount", {"rows": [{"amount": 1}, {"amount": 2}]}),
    ], final="east 区订单已汇总")
    out = Runner(reg, planner, Trace(trace_path)).run("汇总东区订单金额")
    print("执行状态：", out["status"], "| 步数：", out["steps"])
    for obs in out["observations"]:
        print("  观察：", obs)
    print("轨迹事件：", [e["kind"] for e in Trace(trace_path).load()])


if __name__ == "__main__":
    main()
