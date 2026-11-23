"""端到端演示：建库 -> 导入文档 -> 检索 -> 带引用回答。"""
import os
import tempfile

from qa import KnowledgeBase

DOCS = [
    ("员工手册.pdf", "入职满一年可享 5 天年假，满三年 10 天。年假需提前三个工作日在系统提交申请。"),
    ("财务制度.docx", "差旅住宿标准：一线城市 500 元/晚，二线城市 350 元/晚，报销需附发票。"),
    ("IT 运维手册.md", "VPN 连接失败时先检查客户端版本，再重置令牌；仍失败提交工单，2 小时内响应。"),
]


def main():
    path = os.path.join(tempfile.mkdtemp(), "docs.jsonl")
    kb = KnowledgeBase(path, chunk_size=120, overlap=30)
    for source, text in DOCS:
        kb.add_document(source, text)
    print(f"知识库：{len(kb.docs)} 篇文档，{len(kb.index.chunks)} 个切片，词表 {len(kb.index.df)}")

    for q in ["年假有几天", "一线城市住宿能报多少", "VPN 连不上怎么办"]:
        hits = kb.search(q, top_k=2)
        print(f"\n检索[{q}] " + " | ".join(f"{s:.3f} {c.source}" for s, c in hits))

    for q in ["年假需要提前几天申请", "住宿标准是多少"]:
        r = kb.ask(q)
        c = r["citations"][0] if r["citations"] else {}
        print(f"\nQ: {q}\nA: {r['answer']}\n   引用 {c.get('source')} "
              f"[{c.get('start')}-{c.get('end')}] score={c.get('score')}")

    kb2 = KnowledgeBase(path)     # 从 JSONL 重建，验证持久化
    print(f"\n重载后切片数：{len(kb2.index.chunks)}（与内存中一致：{len(kb2.index.chunks) == len(kb.index.chunks)}）")


if __name__ == "__main__":
    main()
