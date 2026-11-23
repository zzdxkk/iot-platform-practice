# 01 · 文档问答服务（BM25 检索 + 引用回溯）

## 解决什么问题
把一堆内部文档（手册、制度、FAQ）变成能回答问题的知识库，而且答案必须能指回原文位置，方便人工核对。难点不在生成一段话，而在检索：中文要分词、切片不能截断语义、排序要能被解释。

## 怎么实现
- `src/tokenizer.py`：英文按词、中文按二元组切分，带停用词表；纯标准库实现，不依赖分词词典
- `src/index.py`：`Chunk`（含 `start/end` 原文偏移）、按句末对齐的滑窗切片（相邻切片有重叠）、`BM25Index`（k1=1.5、b=0.75，倒排表 postings + 文档频次 df → idf）、`DocStore`（JSONL 追加写与加载）
- `src/qa.py`：启动时从 JSONL 重建索引；`ask()` 先用 BM25 召回 top-k 切片，再在切片内做句子级重排（idf 加权重合度 / 句长平方根），返回答案时带 `chunk_id/source/start/end/score`
- `src/server.py`：标准库 `http.server`，`/health`、`/stats`、`GET /search`、`POST /docs`、`POST /ask`；`PORT`、`DATA` 环境变量
- `src/cli.py`：`ingest / search / ask` 三个子命令

## 跑起来
```bash
python3 src/demo.py                        # 建库、检索、问答、验证持久化
PORT=8080 DATA=data/docs.jsonl python3 src/server.py
curl -s -X POST localhost:8080/ask -d '{"question":"年假几天"}'
python3 src/cli.py ingest 员工手册.txt --source 手册
python3 -m unittest discover -s tests -v   # 15 项
```

## 验证
15 项测试覆盖：中英文分词、停用词、切片偏移与原文一致、切片重叠、BM25 排序与 idf 方向、空查询、JSONL 重载后切片数一致、重复 doc_id 拒绝、引用偏移有效、无证据时不给引用、generator 钩子。

## 边界
- 答案默认是"抽句"（extractive），`ask(generator=...)` 才接外部生成服务；仓库不内置任何外部调用
- BM25 只做词面匹配，同义改写会漏；中文二元组会放大长词权重，效果弱于专用分词器
- 切片偏移基于原文，`start/end` 直接可用来做高亮；JSONL 是单机追加写，多进程同时写会冲突
- 没有权限控制、增量删除、向量检索与语义重排；`/docs` 无鉴权，只适合内网
