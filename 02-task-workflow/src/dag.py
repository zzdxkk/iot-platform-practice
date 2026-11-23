"""依赖 DAG：拓扑校验、分层并行、单节点超时与重试、失败传播。"""
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass


class CycleError(Exception):
    pass


@dataclass
class Node:
    name: str
    fn: object
    deps: tuple = ()
    timeout: float | None = None
    retries: int = 0


@dataclass
class Result:
    status: str                       # ok / failed / skipped / timeout
    value: object = None
    error: str = ""
    elapsed: float = 0.0


class DAG:
    def __init__(self, max_workers: int = 4):
        self.nodes: dict[str, Node] = {}
        self.max_workers = max_workers

    def add(self, name, fn, deps=(), timeout=None, retries=0):
        if name in self.nodes:
            raise ValueError(f"重复节点：{name}")
        self.nodes[name] = Node(name, fn, tuple(deps), timeout, retries)
        return self

    def topo_levels(self) -> list[list[str]]:
        for node in self.nodes.values():
            for d in node.deps:
                if d not in self.nodes:
                    raise KeyError(f"{node.name} 依赖不存在的节点：{d}")
        pending = set(self.nodes)
        levels = []
        while pending:
            ready = sorted(n for n in pending if not (set(self.nodes[n].deps) & pending))
            if not ready:
                raise CycleError(f"检测到环：{sorted(pending)}")
            levels.append(ready)
            pending -= set(ready)
        return levels

    @staticmethod
    def _attempt(node: Node, kwargs: dict) -> Result:
        for attempt in range(node.retries + 1):
            t0 = time.monotonic()
            try:
                return Result("ok", node.fn(**kwargs), "",
                              round(time.monotonic() - t0, 4))
            except Exception as e:
                err, el = f"{type(e).__name__}: {e}", round(time.monotonic() - t0, 4)
                if attempt == node.retries:
                    return Result("failed", None, err, el)
        return Result("failed", None, "unreachable")

    def run(self, **inputs) -> dict[str, Result]:
        ctx: dict[str, Result] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for level in self.topo_levels():
                futures = {}
                for name in level:
                    node = self.nodes[name]
                    if not all(ctx[d].status == "ok" for d in node.deps):
                        ctx[name] = Result("skipped", None, "上游未成功")
                        continue
                    kwargs = {d: ctx[d].value for d in node.deps}
                    futures[pool.submit(self._attempt, node, kwargs)] = (
                        node, time.monotonic())
                for fut, (node, t_submit) in futures.items():
                    # 每个节点的超时从它入队那一刻算起，不会被同层其它节点拖长
                    remaining = None if node.timeout is None else max(
                        node.timeout - (time.monotonic() - t_submit), 0.0)
                    try:
                        ctx[node.name] = fut.result(timeout=remaining)
                    except FutTimeout:
                        # 线程无法强杀，只标记超时并让下游跳过
                        ctx[node.name] = Result(
                            "timeout", None, f"{node.name} 超过 {node.timeout}s")
        return {n: ctx[n] for n in self.nodes}


def pipeline(*steps):
    """把 steps 串成线性 DAG。"""
    g = DAG()
    prev = None
    for name, fn in steps:
        g.add(name, fn, deps=(prev,) if prev else ())
        prev = name
    return g
