import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from index import BM25Index, Chunk, DocStore, chunk_text, split_sentences
from qa import KnowledgeBase
from tokenizer import tokenize


class TestTokenizer(unittest.TestCase):
    def test_cjk_bigram(self):
        self.assertIn("年假", tokenize("年假规定"))
    def test_ascii_word(self):
        self.assertIn("bm25", tokenize("BM25 排序"))
    def test_stopword_dropped(self):
        self.assertNotIn("的", tokenize("的规定"))


class TestChunk(unittest.TestCase):
    def test_no_chunk_when_short(self):
        self.assertEqual(len(chunk_text("短句。")), 1)
    def test_overlap_exists(self):
        text = "第一句。" * 60
        parts = chunk_text(text, size=60, overlap=20)
        self.assertGreater(len(parts), 2)
        self.assertLess(parts[1][0], parts[0][1])
    def test_offsets_match_text(self):
        text = "甲乙丙丁。" * 30
        for start, end, piece in chunk_text(text, 40, 10):
            self.assertEqual(piece, text[start:end])
    def test_split_sentences(self):
        self.assertEqual(len(split_sentences("一。二！三？")), 3)


class TestBM25(unittest.TestCase):
    def setUp(self):
        self.ix = BM25Index()
        self.ix.add(Chunk("a#0", "a", "手册", "年假：入职满一年 5 天。"))
        self.ix.add(Chunk("b#0", "b", "财务", "差旅住宿 500 元。"))

    def test_rank_relevant_first(self):
        hits = self.ix.search("年假几天")
        self.assertTrue(hits)
        self.assertEqual(hits[0][1].doc_id, "a")
    def test_common_term_lower_idf(self):
        self.ix.add(Chunk("c#0", "c", "x", "年假 年假 年假"))
        self.assertLess(self.ix.idf("年假"), self.ix.idf("住宿"))
    def test_empty_query_no_hits(self):
        self.assertEqual(self.ix.search(""), [])


class TestStoreAndAsk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "docs.jsonl")
        self.kb = KnowledgeBase(self.path)
        self.kb.add_document("员工手册.pdf", "入职满一年可享 5 天年假，满三年 10 天。")
        self.kb.add_document("财务制度.docx", "差旅住宿：一线城市 500 元/晚，需发票。")

    def test_persist_and_reload(self):
        kb2 = KnowledgeBase(self.path)
        self.assertEqual(len(kb2.docs), 2)
        self.assertEqual(len(kb2.index.chunks), len(self.kb.index.chunks))
    def test_duplicate_doc_id_rejected(self):
        with self.assertRaises(ValueError):
            self.kb.add_document("x", "x", doc_id="doc001")
    def test_ask_returns_citation(self):
        r = self.kb.ask("年假几天")
        self.assertIn("5 天", r["answer"])
        self.assertEqual(r["citations"][0]["source"], "员工手册.pdf")
        self.assertLess(r["citations"][0]["start"], r["citations"][0]["end"])
    def test_ask_without_evidence(self):
        r = self.kb.ask("量子计算机怎么买")
        self.assertEqual(r["citations"], [])
    def test_generator_hook(self):
        r = self.kb.ask("年假", generator=lambda q, ev: f"据{ev}，答案是 5 天。")
        self.assertTrue(r["answer"].startswith("据"))


if __name__ == "__main__":
    unittest.main()
