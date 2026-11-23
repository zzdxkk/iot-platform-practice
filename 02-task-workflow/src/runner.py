"""任务执行循环：Planner 决策 -> 工具调用 -> 观察回填 -> 产出答案。"""
from dataclasses import dataclass, field


@dataclass
class Action:
    tool: str
    args: dict = field(default_factory=dict)


@dataclass
class Final:
    answer: str


class ScriptedPlanner:
    """测试与演示用：按脚本返回动作，脚本耗尽即给出结论。"""

    def __init__(self, script, final="已完成"):
        self.script = list(script)
        self.final = final
        self.seen: list[str] = []

    def next(self, task: str, observations: list[str]):
        self.seen = observations
        if self.script:
            return self.script.pop(0)
        return Final(self.final)


class Runner:
    def __init__(self, registry, planner, trace=None, max_steps: int = 8):
        self.registry, self.planner, self.trace = registry, planner, trace
        self.max_steps = max_steps

    def run(self, task: str) -> dict:
        observations: list[str] = []
        steps = 0
        while steps < self.max_steps:
            action = self.planner.next(task, observations)
            if isinstance(action, Final):
                self._emit("final", answer=action.answer, steps=steps)
                return {"answer": action.answer, "steps": steps,
                        "observations": observations, "status": "done"}
            steps += 1
            try:
                out = self.registry.call(action.tool, **action.args)
                obs = f"{action.tool} -> {out}"
                self._emit("tool_ok", tool=action.tool, args=action.args, out=str(out))
            except Exception as e:
                obs = f"{action.tool} !! {e}"
                self._emit("tool_error", tool=action.tool, args=action.args, err=str(e))
            observations.append(obs)
        self._emit("max_steps", steps=steps)
        return {"answer": None, "steps": steps, "observations": observations,
                "status": "max_steps"}

    def _emit(self, kind, **f):
        if self.trace:
            self.trace.emit(kind, **f)
