"""DAG 工作流编排：任务依赖、并行执行、失败重试——对应任务编排的关键能力。"""
import time
from concurrent.futures import ThreadPoolExecutor

class Task:
    def __init__(self, name, fn, deps=(), retries=1):
        self.name, self.fn, self.deps, self.retries = name, fn, list(deps), retries
    def run(self, ctx):
        for i in range(self.retries + 1):
            try:
                return self.fn(ctx)
            except Exception as e:
                if i == self.retries: raise
                time.sleep(0.01)

class Workflow:
    def __init__(self): self.tasks = {}
    def add(self, task): self.tasks[task.name] = task; return self
    def execute(self):
        ctx, done = {}, set()
        pending = list(self.tasks.values())
        while pending:
            ready = [t for t in pending if all(d in done for d in t.deps)]
            if not ready: raise RuntimeError("检测到循环依赖或缺失依赖")
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(t.run, ctx): t for t in ready}
                for f, t in futs.items(): ctx[t.name] = f.result()
            done.update(t.name for t in ready)
            pending = [t for t in pending if t not in ready]
        return ctx

if __name__ == "__main__":
    wf = Workflow()
    wf.add(Task("采集", lambda c: "原始数据"))
    wf.add(Task("清洗", lambda c: c["采集"] + "->已清洗", deps=["采集"]))
    wf.add(Task("分析", lambda c: c["清洗"] + "->已分析", deps=["清洗"]))
    wf.add(Task("告警检测", lambda c: "无告警", deps=["清洗"]))
    print(wf.execute())
