"""导出：JSONL 归档 + Markdown 合集，文件名安全化。"""
import json
import os
import re


def safe_name(name: str, fallback: str = "untitled") -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name).strip("._")
    return s[:60] or fallback


def export(items: list[dict], out_dir: str, name: str = "batch") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    stem = safe_name(name, "batch_" + str(len(items)))
    jsonl_path = os.path.join(out_dir, stem + ".jsonl")
    md_path = os.path.join(out_dir, stem + ".md")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    lines = [f"# {stem}", ""]
    for it in items:
        lines += [f"## {it.get('title') or it.get('id', '')}", "",
                  f"- 渠道：{it.get('channel', '-')}"
                  f"　字数：{it.get('chars', len(it.get('text', '')))}"
                  f"　审核：{it.get('verdict', '-')}", "",
                  it.get("text", ""), ""]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return {"jsonl": jsonl_path, "markdown": md_path, "count": len(items)}
