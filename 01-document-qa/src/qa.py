"""文档问答主流程：BM25 召回 -> 句子级重排 -> 带偏移的引用。"""
from index import BM25Index, Chunk, DocStore, chunk_text, split_sentences
from tokenizer import tokenize


class KnowledgeBase:
    def __init__(self, store_path="data/docs.jsonl", chunk_size=180, overlap=45):
        self.index = BM25Index()
        self.store = DocStore(store_path)
        self.chunk_size, self.overlap = chunk_size, overlap
        self.docs: dict[str, dict] = {}
        for d in self.store.load():
            self._load(d)

    def _load(self, doc: dict) -> None:
        self.docs[doc["doc_id"]] = doc
        for k, (start, end, piece) in enumerate(
                chunk_text(doc["text"], self.chunk_size, self.overlap)):
            self.index.add(Chunk(f"{doc['doc_id']}#{k}", doc["doc_id"],
                                 doc["source"], piece, start, end))

    def add_document(self, source: str, text: str, doc_id: str | None = None,
                     persist: bool = True) -> str:
        doc_id = doc_id or f"doc{len(self.docs) + 1:03d}"
        if doc_id in self.docs:
            raise ValueError(f"doc_id 已存在：{doc_id}")
        doc = {"doc_id": doc_id, "source": source, "text": text}
        self._load(doc)
        if persist:
            self.store.append(doc_id, source, text)
        return doc_id

    def search(self, query: str, top_k: int = 3):
        return self.index.search(query, top_k)

    def ask(self, question: str, top_k: int = 3, generator=None) -> dict:
        hits = self.search(question, top_k)
        q = set(tokenize(question))
        best = None
        for score, ch in hits:
            for sent in split_sentences(ch.text):
                st = set(tokenize(sent))
                if not st:
                    continue
                overlap = sum(self.index.idf(t) for t in (q & st))
                s = overlap / (len(st) ** 0.5)
                if best is None or s > best[0]:
                    best = (s, sent, ch)
        if best is None:
            return {"question": question, "answer": "知识库中暂无相关信息。", "citations": []}
        _, sentence, ch = best
        answer = generator(question, sentence) if generator else sentence
        return {
            "question": question,
            "answer": answer,
            "citations": [{
                "chunk_id": h.chunk_id, "source": h.source,
                "start": h.start, "end": h.end, "score": round(sc, 4),
            } for sc, h in hits],
        }
