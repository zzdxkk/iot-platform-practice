"""一条内容生产链：生成 -> 审核（阻断/待审/通过）-> 模板排版 -> 导出。"""
from export import export
from moderation import publishable, scan
from templates import LIMITS, post, slots


class Pipeline:
    def __init__(self, generator, template: str, topics=None, rules=None):
        self.generator, self.template = generator, template
        self.topics, self.rules = topics or [], rules

    def run(self, briefs: list[dict], channel: str = "x") -> dict:
        items, blocked = [], []
        for brief in briefs:
            draft = self.generator(brief)
            mod = scan(draft, self.rules)
            if not publishable(mod):
                blocked.append({"id": brief.get("id"), "text": draft, "hits": mod["hits"]})
                continue
            try:
                values = {k: brief[k] for k in slots(self.template) if k in brief}
                p = post(channel, self.template, values, self.topics)
            except Exception as e:                     # 模板问题不该拖垮整批
                blocked.append({"id": brief.get("id"), "error": str(e)})
                continue
            items.append({"id": brief.get("id"), "title": brief.get("title", ""),
                          "channel": channel, "text": p["text"] if mod["verdict"] == "pass"
                          else mod["redacted"], "chars": p["chars"],
                          "truncated": p["truncated"], "verdict": mod["verdict"],
                          "hits": [h["rule"] for h in mod["hits"]]})
        return {"items": items, "blocked": blocked,
                "limits": LIMITS.get(channel)}

    def run_and_export(self, briefs, out_dir: str, name: str = "batch",
                       channel: str = "x") -> dict:
        res = self.run(briefs, channel)
        res["export"] = export(res["items"], out_dir, name)
        return res
