"""工具注册与参数校验：类型强转、必填检查、未知参数拒绝、有界重试。"""
from dataclasses import dataclass, field


class ToolError(Exception):
    """工具调用失败（参数错误或执行异常）。"""


@dataclass
class Tool:
    name: str
    fn: object
    params: dict          # 参数名 -> 类型
    required: tuple = ()
    description: str = ""
    max_retries: int = 0


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"重复注册：{tool.name}")
        bad = set(tool.required) - set(tool.params)
        if bad:
            raise ValueError(f"{tool.name} 的必填参数未声明类型：{sorted(bad)}")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def spec(self) -> list[dict]:
        return [{"name": t.name, "params": {k: v.__name__ for k, v in t.params.items()},
                 "required": list(t.required), "description": t.description}
                for t in self._tools.values()]

    def _coerce(self, tool: Tool, kwargs: dict) -> dict:
        unknown = set(kwargs) - set(tool.params)
        if unknown:
            raise ToolError(f"未知参数：{sorted(unknown)}")
        missing = [k for k in tool.required if k not in kwargs]
        if missing:
            raise ToolError(f"缺少必填参数：{missing}")
        out = {}
        for k, v in kwargs.items():
            typ = tool.params[k]
            if typ is int and isinstance(v, str):
                try:
                    v = int(v)
                except ValueError:
                    raise ToolError(f"参数 {k} 需要 int，收到 {v!r}")
            if typ is float and isinstance(v, (int, str)):
                try:
                    v = float(v)
                except ValueError:
                    raise ToolError(f"参数 {k} 需要 float，收到 {v!r}")
            if typ is str and not isinstance(v, str):
                raise ToolError(f"参数 {k} 需要 str，收到 {type(v).__name__}")
            out[k] = v
        return out

    def call(self, name: str, **kwargs):
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"工具不存在：{name}")
        args = self._coerce(tool, kwargs)
        last = None
        for attempt in range(tool.max_retries + 1):
            try:
                return tool.fn(**args)
            except ToolError:
                raise
            except Exception as e:      # 业务异常参与重试
                last = e
                if attempt == tool.max_retries:
                    break
        raise ToolError(f"{name} 执行失败（重试 {tool.max_retries} 次）：{last}")
