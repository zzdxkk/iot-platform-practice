"""倒排索引 + BM25 打分 + JSONL 文档存储。"""
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tokenizer import tokenize

_SENT_END = "。！？!?."


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    source: str
    text: str
    start: int = 0
    end: int = 0
    tokens: list[str] = field(default_factory=list)


def chunk_text(text: str, size: int = 180, overlap: int = 45) -> list[tuple[int, int, str]]:
    """按字符滑窗切分，尽量把切点落在句末标点上。"""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    out = []
    start, n = 0, len(text)
    while start < n:
        end = min(n, start + size)
        if end < n:
            floor = start + size // 2
            window = text[floor:end]
            cut = max(window.rfind(ch) for ch in _SENT_END)
            if cut >= 0:
                end = floor + cut + 1
        out.append((start, end, text[start:end]))
        if end >= n:
            break
        start = max(0, end - overlap)
    return out


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.chunks: list[Chunk] = []
        self.tf: list[Counter] = []
        self.df: Counter = Counter()
        self.postings: dict[str, list[int]] = defaultdict(list)
        self.total_len = 0

    def add(self, chunk: Chunk) -> None:
        chunk.tokens = tokenize(chunk.text)
        idx = len(self.chunks)
        self.chunks.append(chunk)
        self.tf.append(Counter(chunk.tokens))
        self.total_len += len(chunk.tokens)
        for tok in set(chunk.tokens):
            self.df[tok] += 1
            self.postings[tok].append(idx)

    @property
    def avg_len(self) -> float:
        return self.total_len / len(self.chunks) if self.chunks else 0.0

    def idf(self, token: str) -> float:
        n, df = len(self.chunks), self.df.get(token, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens: list[str], idx: int) -> float:
        tf = self.tf[idx]
        dl = max(1, len(self.chunks[idx].tokens))
        s = 0.0
        for q in query_tokens:
            f = tf.get(q, 0)
            if not f:
                continue
            s += self.idf(q) * f * (self.k1 + 1) / (
                f + self.k1 * (1 - self.b + self.b * dl / (self.avg_len or 1))
            )
        return s

    def search(self, query: str, top_k: int = 3) -> list[tuple[float, Chunk]]:
        q = tokenize(query)
        cand: set[int] = set()
        for tok in q:
            cand.update(self.postings.get(tok, ()))
        ranked = sorted(((self.score(q, i), self.chunks[i]) for i in cand),
                        key=lambda x: -x[0])
        return [(sc, ch) for sc, ch in ranked[:top_k] if sc > 0]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?.\n]+", text)
    return [p.strip() for p in parts if p.strip()]


class DocStore:
    """一行一条文档的 JSONL 存储；进程重启后可直接重建索引。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, doc_id: str, source: str, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"doc_id": doc_id, "source": source, "text": text},
                               ensure_ascii=False) + "\n")

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
