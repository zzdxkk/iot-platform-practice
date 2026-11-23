"""JSONL 评测集：字段校验、去重、按 tag 切分。"""
import json


class DatasetError(Exception):
    pass


REQUIRED = ("id", "input", "reference")


def load_jsonl(path: str) -> list[dict]:
    cases, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as e:
                raise DatasetError(f"第 {lineno} 行不是合法 JSON：{e}")
            for k in REQUIRED:
                if k not in case:
                    raise DatasetError(f"第 {lineno} 行缺少字段 {k}")
            if case["id"] in seen:
                raise DatasetError(f"第 {lineno} 行 id 重复：{case['id']}")
            seen.add(case["id"])
            case.setdefault("tags", [])
            cases.append(case)
    if not cases:
        raise DatasetError("数据集为空")
    return cases


def filter_by_tag(cases: list[dict], tag: str) -> list[dict]:
    return [c for c in cases if tag in c["tags"]]


def split(cases: list[dict], ratio: float = 0.2) -> tuple[list[dict], list[dict]]:
    """按 run_id 稳定切分，避免每次跑都不一样。"""
    dev = [c for c in cases if sum(map(ord, c["id"])) % 100 < ratio * 100]
    train = [c for c in cases if c not in dev]
    return train, dev
