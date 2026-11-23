# 02 · 任务工作流（工具调用 + 依赖 DAG + 轨迹）

## 解决什么问题
一个能跑通的多步任务执行器要处理三件现实问题：工具参数经常错（上游传字符串、漏字段、多塞字段）、工具会失败需要重试、任务本身是有依赖的多步流程（能并行的要并行，失败要停）。这个工程把这层"执行壳"做出来，让决策层可替换。

## 怎么实现
- `src/tools.py`：`Tool`（名字、函数、参数类型表、必填项、最大重试）+ `ToolRegistry`：拒绝未知参数、检查必填、按声明类型做 int/float 强转、执行异常参与有界重试，最终抛 `ToolError` 并保留错误原因
- `src/dag.py`：`DAG.add(name, fn, deps, timeout, retries)`；`topo_levels()` 做拓扑分层并检出环/悬空依赖；按层用 `ThreadPoolExecutor` 并行；单节点超时按入队时刻计，超时/失败后下游自动 `skipped`
- `src/runner.py`：决策循环（`Planner.next(task, observations)` → `Action` 或 `Final`），工具异常转成观察文本回填，`max_steps` 兜底；`ScriptedPlanner` 用于测试与演示，真实场景替换成任意决策函数即可
- `src/trace.py`：每步一条 JSONL 事件（工具、参数、结果、错误、相对时间戳），可回放

## 跑起来
```bash
python3 src/demo.py                        # 工具注册、DAG 并行与失败传播、执行轨迹
python3 -m unittest discover -s tests -v   # 18 项
```

## 验证
18 项测试覆盖：字符串参数强转成 int、缺必填/未知参数/未知工具/类型不符四类报错、重试两次后成功与重试耗尽、DAG 分层顺序、环检测、依赖数据传递、上游失败导致下游 skipped、超时标记、四个节点并行耗时小于串行、执行器两工具后收尾、工具错误进观察、`max_steps` 截断、轨迹 JSONL 往返、执行器写轨迹。

## 边界
- 决策层是脚本化 planner，仓库里没有接任何推理服务；换真实决策只替换 `Planner.next`
- 线程无法被强杀，超时只做标记与下游跳过，不保证线程立即退出；要在生产里硬超时需进程级隔离
- DAG 无持久化、无优先级、无动态分支；重试是固定次数，没有指数退避与熔断
- 轨迹只追加写本地文件，没有采样、聚合与上传
