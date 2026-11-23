"""命令行：导入文档、检索、问答。"""
import argparse
import json
import sys

from qa import KnowledgeBase


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/docs.jsonl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("file")
    ing.add_argument("--source")
    q = sub.add_parser("ask")
    q.add_argument("question")
    q.add_argument("-k", type=int, default=3)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=3)
    a = ap.parse_args(argv)
    kb = KnowledgeBase(a.data)
    if a.cmd == "ingest":
        text = open(a.file, encoding="utf-8").read()
        print(kb.add_document(a.source or a.file, text))
    elif a.cmd == "ask":
        print(json.dumps(kb.ask(a.question, a.k), ensure_ascii=False, indent=1))
    else:
        for score, ch in kb.search(a.query, a.k):
            print(f"{score:.4f}  {ch.source}  {ch.text[:80]}")


if __name__ == "__main__":
    main(sys.argv[1:])
