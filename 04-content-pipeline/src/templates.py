"""内容模板：占位符校验、长度裁剪、平台限制、话题标签。"""
import re

PLACEHOLDER = re.compile(r"\{(\w+)\}")
LIMITS = {"x": 280, "xiaohongshu": 1000, "wechat": 2000}


class TemplateError(Exception):
    pass


def slots(template: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(template)))


def render(template: str, values: dict) -> str:
    need = set(slots(template))
    missing = need - set(values)
    extra = set(values) - need
    if missing:
        raise TemplateError(f"缺少占位符：{sorted(missing)}")
    if extra:
        raise TemplateError(f"多余参数：{sorted(extra)}")
    for k, v in values.items():
        if not isinstance(v, (str, int, float)):
            raise TemplateError(f"参数 {k} 类型不支持：{type(v).__name__}")
        if isinstance(v, str) and not v.strip():
            raise TemplateError(f"参数 {k} 为空")
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template)


def truncate(text: str, limit: int, ellipsis: str = "…") -> str:
    """优先在句末/分句处截断，避免把词切断。"""
    if len(text) <= limit:
        return text
    cut = limit - len(ellipsis)
    window = text[:cut]
    for sep in ("。", "！", "？", "；", "，", " "):
        i = window.rfind(sep)
        if i >= cut * 0.6:
            return window[:i + 1].rstrip() + ellipsis
    return window.rstrip() + ellipsis


def hashtags(topics: list[str], n: int = 3) -> str:
    clean = [re.sub(r"[^\w\u4e00-\u9fff]", "", t) for t in topics]
    clean = [t for t in clean if t][:n]
    return " ".join(f"#{t}" for t in clean)


def post(channel: str, template: str, values: dict, topics=None) -> dict:
    if channel not in LIMITS:
        raise TemplateError(f"未知渠道：{channel}")
    body = render(template, values)
    tags = hashtags(topics or [])
    if tags:
        body = f"{body}\n{tags}"
    out = truncate(body, LIMITS[channel])
    return {"channel": channel, "text": out, "chars": len(out),
            "truncated": len(body) > LIMITS[channel], "limit": LIMITS[channel]}
