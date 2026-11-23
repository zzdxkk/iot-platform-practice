# 03 · 输出质量评测与门禁

## 解决什么问题
换了实现、调了参数或改了模板，输出到底变好还是变差？只看几个样例会得出误判。这个工程把评测做成可复跑的一条链：JSONL 用例集 → 多指标打分 → bootstrap 置信区间 → 与基线做配对显著性检验 → 门禁判定 → Markdown 报告。

## 怎么实现
- `src/metrics.py`：`exact_match`、`contains_ref`、`token_f1`（英文按词/中文按字）、`bleu`（1–4 gram + 长度惩罚）、`rouge_l`（LCS 的 F 值）、`json_field_accuracy`（结构化输出逐字段命中）
- `src/stats.py`：百分位 `bootstrap_ci`（默认 2000 次重采样）、`paired_bootstrap`（同批样本上的差值 CI 与双尾 p）、`sign_test`（精确二项符号检验）
- `src/dataset.py`：JSONL 加载并校验（必填字段、id 去重、坏 JSON 报行号）、按 tag 过滤、稳定切分
- `src/runner.py`：`run()` 出逐条明细与聚合（均值 + CI）、`compare()` 出胜负数与 p 值、`gate()` 按阈值判定、`worst()` 取最差样本
- `src/report.py`：渲染 Markdown（指标表、门禁结论、对比结论、最差样本）

## 跑起来
```bash
python3 src/demo.py                        # 基线 vs 改进版：报告 + 门禁 + p 值
python3 -m unittest discover -s tests -v   # 24 项
```

## 验证
24 项测试覆盖：EM/F1/BLEU/ROUGE-L 的边界（完全相同=1、长度惩罚使短答案变低、部分重合落在 0~1）、JSON 字段命中的半对与非法 JSON、CI 的收敛与宽度、符号检验的极端值（10:0 → p=0.00195）与均衡值、配对 bootstrap 能检出整体提升、数据集缺字段/重复 id/坏 JSON 报错、tag 过滤、门禁通过与不通过、报告中出现对比结论。

## 边界
- 指标都是字面/词面级，不判语义等价；BLEU 对中文按单字，只用于相对比较，不是论文口径
- 样本数少时 CI 很宽，p 值只是参考；`sign_test` 在 n 很大时浮点会失真（工程上应换成正态近似）
- 被测系统是函数注入（`system_fn`），仓库里不含任何外部调用；线上要接真实服务、缓存与并发
- 门禁阈值写在调用处，没有配置中心和回归基线存档；用例集规模是示例级（8 条）
