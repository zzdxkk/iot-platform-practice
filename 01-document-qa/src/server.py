"""知识库 HTTP 服务：/health、/stats、POST /docs、POST /ask、GET /search。"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from qa import KnowledgeBase

KB = KnowledgeBase(os.environ.get("DATA", "data/docs.jsonl"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._json({"ok": True, "docs": len(KB.docs),
                               "chunks": len(KB.index.chunks)})
        if u.path == "/stats":
            return self._json({"docs": len(KB.docs), "chunks": len(KB.index.chunks),
                               "vocab": len(KB.index.df)})
        if u.path == "/search":
            q = (parse_qs(u.query).get("q") or [""])[0]
            hits = KB.search(q, int((parse_qs(u.query).get("k") or ["3"])[0]))
            return self._json({"query": q, "hits": [
                {"chunk_id": c.chunk_id, "source": c.source, "score": round(s, 4),
                 "text": c.text} for s, c in hits]})
        self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "invalid json"}, 400)
        if u.path == "/docs":
            if not body.get("text"):
                return self._json({"error": "text 必填"}, 400)
            try:
                doc_id = KB.add_document(body.get("source", "inline"),
                                         body["text"], body.get("doc_id"))
            except ValueError as e:
                return self._json({"error": str(e)}, 409)
            return self._json({"doc_id": doc_id}, 201)
        if u.path == "/ask":
            return self._json(KB.ask(body.get("question", ""), int(body.get("top_k", 3)))
                              if body.get("question") else {"answer": "", "citations": []})
        self.send_error(404)

    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"listening on http://127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
