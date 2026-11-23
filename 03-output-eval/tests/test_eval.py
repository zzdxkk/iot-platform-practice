import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import metrics
from dataset import DatasetError, filter_by_tag, load_jsonl
from report import render, table
from runner import Runner
from stats import bootstrap_ci, paired_bootstrap, sign_test


def write_cases(rows, tmp=None):
    p = os.path.join(tmp or tempfile.mkdtemp(), "d.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


CASES = [
    {"id": "c1", "input": "年假几天", "reference": "5 天", "tags": ["hr"]},
    {"id": "c2", "input": "住宿标准", "reference": "500 元", "tags": ["fin"]},
    {"id": "c3", "input": "报销多久到账", "reference": "3 个工作日", "tags": ["fin"]},
]


class TestMetrics(unittest.TestCase):
    def test_em(self):
        self.assertEqual(metrics.exact_match(" 5 天 ", "5 天"), 1.0)
    def test_f1_identical(self):
        self.assertAlmostEqual(metrics.token_f1("5 天", "5 天"), 1.0)
    def test_f1_partial(self):
        v = metrics.token_f1("5 天年假", "5 天")
        self.assertTrue(0 < v < 1)
    def test_bleu_identical(self):
        self.assertAlmostEqual(metrics.bleu("差旅住宿 500 元", "差旅住宿 500 元"), 1.0, places=4)
    def test_bleu_brevity_penalty(self):
        self.assertLess(metrics.bleu("500", "差旅住宿 500 元"), 0.6)
    def test_rouge_l_identical(self):
        self.assertAlmostEqual(metrics.rouge_l("报销 3 天", "报销 3 天"), 1.0)
    def test_json_field_acc(self):
        ref = {"intent": "refund", "amount": "500"}
        self.assertAlmostEqual(metrics.json_field_accuracy(
            '{"intent":"refund","amount":"500"}', ref), 1.0)
        self.assertAlmostEqual(metrics.json_field_accuracy('{"intent":"refund"}', ref), 0.5)
    def test_json_invalid(self):
        self.assertEqual(metrics.json_field_accuracy("not json", {"a": "1"}), 0.0)
    def test_score_case_switches_on_ref_type(self):
        self.assertIn("field_acc", metrics.score_case("{}", {"reference": {"a": "1"}}))
        self.assertIn("f1", metrics.score_case("x", {"reference": "x"}))


class TestStats(unittest.TestCase):
    def test_ci_contains_mean(self):
        lo, hi = bootstrap_ci([1, 1, 1, 1])
        self.assertEqual((lo, hi), (1.0, 1.0))
    def test_ci_wider_with_variance(self):
        a, b = bootstrap_ci([1, 0, 1, 0]), bootstrap_ci([0.5, 0.5, 0.5, 0.5])
        self.assertGreater(a[1] - a[0], 0)
        self.assertEqual(b[1] - b[0], 0.0)
    def test_sign_test_extreme(self):
        self.assertAlmostEqual(sign_test(10, 0), 2 / 1024, places=6)
    def test_sign_test_balanced(self):
        self.assertAlmostEqual(sign_test(5, 5), 1.0, places=3)
    def test_paired_bootstrap_detects_gain(self):
        r = paired_bootstrap([1] * 20, [0] * 20)
        self.assertGreater(r["delta"], 0)
        self.assertLess(r["p"], 0.1)


class TestDataset(unittest.TestCase):
    def test_load_ok(self):
        cases = load_jsonl(write_cases(CASES))
        self.assertEqual(len(cases), 3)
    def test_missing_field(self):
        with self.assertRaises(DatasetError):
            load_jsonl(write_cases([{"id": "x", "input": "q"}]))
    def test_duplicate_id(self):
        with self.assertRaises(DatasetError):
            load_jsonl(write_cases([CASES[0], CASES[0]]))
    def test_bad_json(self):
        p = os.path.join(tempfile.mkdtemp(), "bad.jsonl")
        Path(p).write_text("{oops\n", encoding="utf-8")
        with self.assertRaises(DatasetError):
            load_jsonl(p)
    def test_filter_tag(self):
        self.assertEqual(len(filter_by_tag(load_jsonl(write_cases(CASES)), "fin")), 2)


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.cases = CASES
        self.r = Runner(self.cases)
        self.good = self.r.run(lambda q: {"年假几天": "5 天", "住宿标准": "500 元",
                                         "报销多久到账": "3 个工作日"}[q], "good")
        self.bad = self.r.run(lambda q: "不知道", "bad")

    def test_agg_keys(self):
        self.assertIn("f1", self.good["agg"])
        self.assertEqual(self.good["agg"]["f1"]["mean"], 1.0)
    def test_gate_pass_and_fail(self):
        self.assertTrue(self.r.gate(self.good, {"f1": 0.9})["passed"])
        self.assertFalse(self.r.gate(self.bad, {"f1": 0.9})["passed"])
    def test_compare_shows_gain(self):
        c = self.r.compare(self.good, self.bad)
        self.assertEqual(c["wins"], 3)
        self.assertEqual(c["sign_p"], round(2 / 8, 6))
    def test_worst(self):
        self.assertEqual(self.r.worst(self.bad, "f1")[0]["f1"], 0.0)

    def test_report_contains_numbers(self):
        md = render([self.good, self.bad], gates=[self.r.gate(self.bad, {"f1": 0.9})],
                    comparisons=[self.r.compare(self.good, self.bad)],
                    worst=self.r.worst(self.bad, "f1", 1))
        self.assertIn("| good |", table([self.good]))
        self.assertIn("未通过", md)
        self.assertIn("符号检验", md)


if __name__ == "__main__":
    unittest.main()
