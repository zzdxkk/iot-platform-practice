"""任务队列状态机：优先级、幂等去重、指数退避、有限重试、失败终态。"""
import itertools
import random
from dataclasses import dataclass, field

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


@dataclass
class Job:
    job_id: str
    payload: dict
    idem_key: str = ""
    priority: int = 5            # 数字越小越优先
    state: str = QUEUED
    attempts: int = 0
    max_attempts: int = 3
    next_at: float = 0.0
    error: str = ""
    seq: int = 0                 # 同优先级 FIFO


@dataclass
class QueueStats:
    enqueued: int = 0
    deduped: int = 0
    done: int = 0
    failed: int = 0
    retried: int = 0


class JobQueue:
    """内存队列；时间由 clock 注入，退避逻辑可被测试精确断言。"""

    def __init__(self, base_backoff: float = 0.5, max_backoff: float = 30.0,
                 clock=None, jitter=None):
        self.base, self.cap = base_backoff, max_backoff
        self.clock = clock or (lambda: 0.0)
        self.jitter = jitter or (lambda a: random.uniform(0, a))
        self.jobs: dict[str, Job] = {}
        self._by_idem: dict[str, str] = {}
        self._seq = itertools.count()
        self.stats = QueueStats()

    def enqueue(self, payload: dict, idem_key: str = "", priority: int = 5,
                job_id: str | None = None) -> Job:
        if idem_key and idem_key in self._by_idem:
            self.stats.deduped += 1
            return self.jobs[self._by_idem[idem_key]]
        jid = job_id or f"job{next(self._seq) + 1:04d}"
        if jid in self.jobs:
            raise ValueError(f"job_id 重复：{jid}")
        job = Job(jid, payload, idem_key, priority, seq=next(self._seq))
        self.jobs[jid] = job
        if idem_key:
            self._by_idem[idem_key] = jid
        self.stats.enqueued += 1
        return job

    def claim(self) -> Job | None:
        now = self.clock()
        ready = [j for j in self.jobs.values()
                 if j.state == QUEUED and j.next_at <= now]
        if not ready:
            return None
        job = min(ready, key=lambda j: (j.priority, j.next_at, j.seq))
        job.state = RUNNING
        job.attempts += 1
        return job

    def complete(self, job: Job, result=None) -> None:
        job.state = DONE
        job.error = ""
        self.stats.done += 1

    def fail(self, job: Job, error: str) -> None:
        job.error = error
        if job.attempts >= job.max_attempts:
            job.state = FAILED
            self.stats.failed += 1
            return
        delay = min(self.cap, self.base * 2 ** (job.attempts - 1))
        job.next_at = self.clock() + delay + self.jitter(delay * 0.1)
        job.state = QUEUED
        self.stats.retried += 1

    def pending(self) -> list[Job]:
        return [j for j in self.jobs.values() if j.state == QUEUED]

    def drain(self, handler, max_loops: int = 64) -> dict:
        """把可执行的任务跑到终态；handler(job) 抛异常即视为失败。"""
        loops = 0
        while loops < max_loops:
            loops += 1
            job = self.claim()
            if job is None:
                break
            try:
                handler(job)
            except Exception as e:
                self.fail(job, f"{type(e).__name__}: {e}")
            else:
                self.complete(job)
        return {"done": self.stats.done, "failed": self.stats.failed,
                "retried": self.stats.retried,
                "pending": [j.job_id for j in self.pending()]}
