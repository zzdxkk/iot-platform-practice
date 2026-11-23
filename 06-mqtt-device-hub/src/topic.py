"""主题校验与通配符匹配：+ 单层、# 多层、$SYS 例外。"""
from codec import CodecError


def validate_filter(filter_: str) -> None:
    if not filter_ or len(filter_) > 65535:
        raise CodecError("订阅过滤器为空或过长")
    levels = filter_.split("/")
    for i, lv in enumerate(levels):
        if "#" in lv:
            if lv != "#" or i != len(levels) - 1:
                raise CodecError(f"# 只能单独出现在最后一层：{filter_}")
        if "+" in lv and lv != "+":
            raise CodecError(f"+ 必须独占一层：{filter_}")


def validate_topic(topic: str) -> None:
    if not topic or len(topic) > 65535:
        raise CodecError("主题为空或过长")
    if "+" in topic or "#" in topic:
        raise CodecError(f"发布主题不能含通配符：{topic}")


def matches(filter_: str, topic: str) -> bool:
    validate_filter(filter_)
    # MQTT 规范：以 $ 开头的主题不被通配符匹配
    if topic.startswith("$") and filter_.split("/")[0] in ("+", "#"):
        return False
    fl, tl = filter_.split("/"), topic.split("/")
    i = 0
    for i, lv in enumerate(fl):
        if lv == "#":
            return True
        if i >= len(tl):
            return False
        if lv != "+" and lv != tl[i]:
            return False
    return len(fl) == len(tl)
