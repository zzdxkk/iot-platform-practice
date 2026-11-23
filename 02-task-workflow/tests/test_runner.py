import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from runner import Action, Runner, Final, ScriptedPlanner
from dag import DAG, CycleError, pipeline
from tools import Tool, ToolError, ToolRegistry
from trace import Trace


def make_registry():
    reg = ToolRegistry()
    reg.register(Tool("add", lambda a, b: a + b, {"a": int, "b": int},
                      ("a", "b"), "两数相加"))
    reg.register(Tool("upper", lambda s: s.upper(), {"s": str}, ("s",), "转大写"))
    return reg


class TestTools(unittest.TestCase):
    def test_coerce_str_to_int(self):
        self.assertEqual(make_registry().call("add", a="2", b="3"), 5)
    def test_missing_required(self):
        with self.assertRaises(ToolError) as c:
            make_registry().call("add", a=1)
        self.assertIn("缺少必填", str(c.exception))
    def test_unknown_param(self):
        with self.assertRaises(ToolError):
            make_registry().call("add", a=1, b=2, c=3)
    def test_unknown_tool(self):
        with self.assertRaises(ToolError):
            make_registry().call("nope")
    def test_type_mismatch(self):
        with self.assertRaises(ToolError):
            make_registry().call("upper", s=123)
    def test_retry_recovers(self):
        calls = {"n": 0}
        def flaky(x):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("boom")
            return x
        reg = ToolRegistry()
        reg.register(Tool("f", flaky, {"x": int}, ("x",), max_retries=2))
        self.assertEqual(reg.call("f", x=7), 7)
        self.assertEqual(calls["n"], 3)
    def test_retry_exhausted(self):
        reg = ToolRegistry()
        reg.register(Tool("bad", lambda: (_ for _ in ()).throw(ValueError("x")), {},
                      (), max_retries=1))
        with self.assertRaises(ToolError):
            reg.call("bad")


class TestDAG(unittest.TestCase):
    def test_levels_order(self):
        g = DAG().add("a", lambda: 1).add("b", lambda: 2).add("c", lambda x: 3, deps=("a",))
        self.assertEqual(g.topo_levels(), [["a", "b"], ["c"]])
    def test_cycle_detected(self):
        g = DAG().add("a", lambda: 1, deps=("b",)).add("b", lambda: 2, deps=("a",))
        with self.assertRaises(CycleError):
            g.topo_levels()
    def test_data_flows(self):
        g = pipeline(("one", lambda: 2), ("two", lambda one: one * 10)).run()
        self.assertEqual(g["two"].value, 20)
    def test_failure_skips_downstream(self):
        g = DAG().add("a", lambda: 1 / 0).add("b", lambda a: a, deps=("a",))
        r = g.run()
        self.assertEqual(r["a"].status, "failed")
        self.assertEqual(r["b"].status, "skipped")
    def test_timeout(self):
        import time
        g = DAG(max_workers=2).add("slow", lambda: time.sleep(0.5), timeout=0.05)
        r = g.run()
        self.assertEqual(r["slow"].status, "timeout")
    def test_parallel_runs(self):
        import time
        g = DAG(max_workers=4)
        for n in "abcd":
            g.add(n, lambda: time.sleep(0.2))
        t = time.monotonic()
        r = g.run()
        self.assertTrue(all(v.status == "ok" for v in r.values()))
        self.assertLess(time.monotonic() - t, 0.7)


class TestRunner(unittest.TestCase):
    def test_two_tools_then_final(self):
        reg = make_registry()
        p = ScriptedPlanner([Action("add", {"a": 2, "b": 3}),
                             Action("upper", {"s": "hi"})], final="done")
        out = Runner(reg, p).run("求和再转大写")
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["answer"], "done")
        self.assertEqual(p.seen, ["add -> 5", "upper -> HI"])
    def test_tool_error_becomes_observation(self):
        p = ScriptedPlanner([Action("add", {"a": 1})], final="fallback")
        out = Runner(make_registry(), p).run("x")
        self.assertIn("!!", out["observations"][0])
        self.assertEqual(out["answer"], "fallback")
    def test_max_steps_stops(self):
        p = ScriptedPlanner([Action("add", {"a": 1, "b": 1})] * 5)
        out = Runner(make_registry(), p, max_steps=3).run("loop")
        self.assertEqual(out["status"], "max_steps")
        self.assertEqual(out["steps"], 3)


class TestTrace(unittest.TestCase):
    def test_jsonl_roundtrip(self):
        tmp = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        tr = Trace(tmp)
        tr.emit("start", task="x")
        tr.emit("final", answer="y")
        lines = Trace(tmp).load()
        self.assertEqual([e["kind"] for e in lines], ["start", "final"])
        self.assertEqual(lines[1]["answer"], "y")
    def test_runner_writes_trace(self):
        tmp = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        Runner(make_registry(), ScriptedPlanner([Action("add", {"a": 1, "b": 2})]),
              Trace(tmp)).run("x")
        kinds = [e["kind"] for e in Trace(tmp).load()]
        self.assertEqual(kinds, ["tool_ok", "final"])


if __name__ == "__main__":
    unittest.main()
