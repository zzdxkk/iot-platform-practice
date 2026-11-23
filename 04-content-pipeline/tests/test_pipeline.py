import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from export import export, safe_name
from moderation import BLOCK, PASS, REVIEW, Rule, publishable, redact, scan
from pipeline import Pipeline
from queue import DONE, FAILED, QUEUED, JobQueue
from templates import LIMITS, TemplateError, hashtags, post, render, slots, truncate


class TestQueue(unittest.TestCase):
    def make(self):
        self.now = 0.0
        return JobQueue(base_backoff=1.0, clock=lambda: self.now, jitter=lambda a: 0.0)

    def test_priority_order(self):
        q = self.make()
        q.enqueue({"n": 1}, priority=5)
        q.enqueue({"n": 2}, priority=1)
        self.assertEqual(q.claim().payload["n"], 2)
    def test_fifo_same_priority(self):
        q = self.make()
        q.enqueue({"n": 1})
        q.enqueue({"n": 2})
        self.assertEqual(q.claim().payload["n"], 1)
    def test_idempotent_enqueue(self):
        q = self.make()
        a = q.enqueue({"x": 1}, idem_key="k")
        b = q.enqueue({"x": 2}, idem_key="k")
        self.assertEqual(a.job_id, b.job_id)
        self.assertEqual(len(q.jobs), 1)
        self.assertEqual(q.stats.deduped, 1)
    def test_exponential_backoff(self):
        q = self.make()
        job = q.enqueue({"x": 1}, job_id="j1")
        q.claim()
        q.fail(job, "e1")
        self.assertEqual(job.state, QUEUED)
        self.assertEqual(job.next_at, 1.0)
        self.now = 1.0
        q.claim()
        q.fail(job, "e2")
        self.assertEqual(job.next_at, 3.0)
    def test_retry_exhausted(self):
        q = self.make()
        job = q.enqueue({"x": 1}, job_id="j1")
        for _ in range(job.max_attempts):
            self.now += 10.0
            q.claim()
            q.fail(job, "boom")
        self.assertEqual(job.state, FAILED)
        self.assertEqual(q.stats.retried, job.max_attempts - 1)
    def test_nothing_ready_before_backoff(self):
        q = self.make()
        job = q.enqueue({"x": 1})
        q.claim()
        q.fail(job, "e")
        self.assertIsNone(q.claim())
    def test_drain_reports_pending(self):
        q = self.make()
        job = q.enqueue({"x": 1})
        r = q.drain(lambda j: (_ for _ in ()).throw(RuntimeError("no")))
        self.assertEqual(r["failed"], 0)
        self.assertEqual(r["pending"], [job.job_id])


class TestTemplates(unittest.TestCase):
    def test_slots(self):
        self.assertEqual(slots("{a} 和 {b} 和 {a}"), ["a", "b"])
    def test_render_ok(self):
        self.assertEqual(render("{n} 天", {"n": 5}), "5 天")
    def test_missing_slot(self):
        with self.assertRaises(TemplateError):
            render("{a}{b}", {"a": "x"})
    def test_extra_param(self):
        with self.assertRaises(TemplateError):
            render("{a}", {"a": "x", "b": "y"})
    def test_empty_value(self):
        with self.assertRaises(TemplateError):
            render("{a}", {"a": "  "})
    def test_truncate_on_sentence(self):
        self.assertEqual(truncate("第一句。第二句。", 6), "第一句。…")
    def test_truncate_short_untouched(self):
        self.assertEqual(truncate("短", 10), "短")
    def test_hashtag_clean(self):
        self.assertEqual(hashtags(["智能 硬件", "低功耗!", ""], n=2), "#智能硬件 #低功耗")
    def test_post_limit(self):
        p = post("x", "{a}", {"a": "长" * 400})
        self.assertEqual(p["chars"], LIMITS["x"])
        self.assertTrue(p["truncated"])
    def test_unknown_channel(self):
        with self.assertRaises(TemplateError):
            post("tiktok", "{a}", {"a": "x"})


class TestModeration(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(scan("智能水表支持远程抄表，续航三年。")["verdict"], PASS)
    def test_block_takes_precedence(self):
        r = scan("加微信付款更便宜，电话 13800138000")
        self.assertEqual(r["verdict"], BLOCK)
    def test_review_on_phone(self):
        self.assertEqual(scan("有问题打 13800138000")["verdict"], REVIEW)
    def test_too_short(self):
        self.assertEqual(scan("好")["verdict"], REVIEW)
    def test_redact_phone(self):
        self.assertEqual(redact("电话 13800138000"), "电话 138****8000")
    def test_redact_email(self):
        self.assertEqual(redact("邮箱 a@b.com"), "邮箱 a***@b.com")
    def test_custom_rules(self):
        r = scan("含禁用词", rules=[Rule("自定义", __import__("re").compile("禁用"), BLOCK, "x")])
        self.assertEqual(r["verdict"], BLOCK)
    def test_publishable(self):
        self.assertFalse(publishable({"verdict": BLOCK}))
        self.assertTrue(publishable({"verdict": REVIEW}))


class TestExportAndPipeline(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(safe_name("a/b:c*"), "a_b_c")
        self.assertEqual(safe_name("///"), "untitled")
    def test_export_files(self):
        d = tempfile.mkdtemp()
        r = export([{"id": "a", "text": "x", "verdict": "pass"}], d, "批 1")
        self.assertTrue(os.path.exists(r["jsonl"]))
        with open(r["markdown"], encoding="utf-8") as f:
            self.assertIn("x", f.read())

    def test_pipeline_blocks_bad(self):
        pipe = Pipeline(lambda b: f"{b['product']}：{b['point']}", "{product}｜{point}")
        res = pipe.run([{"id": "ok", "product": "水表", "point": "续航三年"},
                        {"id": "bad", "product": "网关", "point": "私下转账八折"}])
        self.assertEqual([i["id"] for i in res["items"]], ["ok"])
        self.assertEqual(res["blocked"][0]["id"], "bad")
    def test_pipeline_review_redacts(self):
        pipe = Pipeline(lambda b: "咨询热线 13800138000，工作时段接听。", "{product}｜{point}")
        res = pipe.run([{"id": "r", "product": "表", "point": "支持远程抄表"}])
        self.assertEqual(res["items"][0]["verdict"], REVIEW)
        self.assertIn("****", res["items"][0]["text"])
    def test_pipeline_template_error_isolated(self):
        pipe = Pipeline(lambda b: "正常内容", "{product}｜{point}")
        res = pipe.run([{"id": "x", "product": "表", "extra": 1}])
        self.assertEqual(res["items"], [])
        self.assertIn("缺少占位符", res["blocked"][0]["error"])


if __name__ == "__main__":
    unittest.main()
