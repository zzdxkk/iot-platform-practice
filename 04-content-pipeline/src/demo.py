"""演示：带退避的任务队列 + 审核分级 + 模板排版 + 导出。"""
import os
import tempfile

from pipeline import Pipeline
from queue import JobQueue
from templates import hashtags, post

BRIEFS = [
    {"id": "b1", "title": "夏季巡检", "product": "智能水表", "point": "低功耗，两节电池用三年"},
    {"id": "b2", "title": "促销", "product": "网关", "point": "私下转账享八折"},
    {"id": "b3", "title": "案例", "product": "温湿度传感器", "point": "冷库 24 小时监控，报警延迟小于 10 秒"},
    {"id": "b4", "title": "客服", "product": "烟感报警器", "point": "咨询可拨 13800138000"},
]

TEMPLATE = "{product}｜{point}。详情见评论区置顶，客服会逐一回复。"


def main():
    # 1) 队列：注入 clock，验证幂等与退避
    now = [0.0]
    q = JobQueue(base_backoff=1.0, clock=lambda: now[0], jitter=lambda a: 0.0)
    q.enqueue({"task": "gen", "n": 1}, idem_key="gen:b1")
    q.enqueue({"task": "gen", "n": 2}, idem_key="gen:b1")     # 幂等命中，不重复入队
    q.enqueue({"task": "gen", "n": 3}, priority=1)
    print("入队后：", len(q.jobs), "个任务，去重计数", q.stats.deduped)

    seen = {}

    def flaky(job):
        seen[job.job_id] = seen.get(job.job_id, 0) + 1
        if job.payload["n"] == 3 and seen[job.job_id] == 1:
            raise RuntimeError("下游 502")      # 首次失败，等退避窗口再重试
        return "ok"

    print("第一轮 drain：", q.drain(flaky))
    now[0] += 5.0                                             # 快进退避窗口
    print("退避后 drain：", q.drain(flaky))
    print("任务终态：", {j.job_id: j.state for j in q.jobs.values()} )

    # 2) 审核 + 排版 + 导出
    def generator(brief):
        return f"{brief['product']}：{brief['point']}。{brief['title']}专场。"

    pipe = Pipeline(generator, TEMPLATE, topics=["智能硬件", "低功耗"])
    out = pipe.run_and_export(BRIEFS, os.path.join(tempfile.mkdtemp(), "out"), "demo")
    print("\n通过：", [(i["id"], i["verdict"], i["chars"]) for i in out["items"]])
    print("待审（已脱敏）：", [(i["id"], i["hits"]) for i in out["items"] if i["verdict"] == "review"])
    print("阻断：", [(b["id"], [h["rule"] for h in b.get("hits", [])]) for b in out["blocked"]])
    print("导出文件：", os.path.basename(out["export"]["jsonl"]),
          os.path.basename(out["export"]["markdown"]))
    print("话题标签示例：", hashtags(["智能硬件", "低功耗", "水表", "多余"], n=3))
    long = post("x", "{product}｜{point}。" + "补充说明。" * 80,
                {"product": "网关", "point": "支持 200 个节点"}, ["物联网", "边缘计算"])
    print(f"超长裁剪：{long['chars']}/{long['limit']}，truncated={long['truncated']}")


if __name__ == "__main__":
    main()
