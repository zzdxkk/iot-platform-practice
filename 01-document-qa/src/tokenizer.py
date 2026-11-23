"""中英混排分词：英文按词、中文按二元组，去掉常见停用词。

没有引 jieba，是为了保持零依赖；二元组对短查询的召回够用，
代价是词表偏大、长文档索引会多一些内存。
"""
import re

STOPWORDS = {
    "的", "了", "和", "是", "在", "有", "我", "你", "他", "她", "它", "们", "吗", "呢",
    "啊", "吧", "就", "都", "与", "及", "或", "把", "被", "也", "还", "很", "会", "要",
    "the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on", "for", "at",
}

_ASCII = re.compile(r"[a-z0-9_]+")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def tokenize(text: str) -> list[str]:
    text = normalize(text)
    out: list[str] = []
    for m in _ASCII.finditer(text):
        w = m.group()
        if w.isdigit() or (len(w) > 1 and w not in STOPWORDS):
            out.append(w)
    for seg in _CJK.findall(text):
        if len(seg) == 1:
            if seg not in STOPWORDS:
                out.append(seg)
            continue
        for i in range(len(seg) - 1):
            gram = seg[i:i + 2]
            if gram not in STOPWORDS:
                out.append(gram)
    return out
