# RAG Query Latency Optimization — Implementation Spec

> 目标读者: Cursor / 自动化 coding agent
> 目标: 在不改变最终答案质量的前提下，显著降低 `answer_question` 的端到端延迟。
> 主入口: [rag/rag_pipeline.py](rag/rag_pipeline.py) `answer_question`

> **状态更新（在做新 Phase 0 / 3.1 / 3.3 / 5.2 之前请读）**：审查代码后发现以下任务已经实现，不要再重复做：
> - Phase 0 任务 0.1（`timings_ms` 分阶段计时）— 见 `rag/rag_pipeline.py`
> - Phase 1 任务 3.1（`retrieve_layered_context` 三层并行）— 见 `rag/retriever.py`
> - Phase 1 任务 3.3（Graph 与 retrieval 并行）— 见 `rag/rag_pipeline.py`
> - Phase 3 任务 5.2（短 query 跳过 rewrite）— 见 `_should_skip_rewrite_for_query`
>
> 仍待做：任务 0.2、3.2（子问题并行）、4.1/4.3/4.4（rewrite / multi_query / decompose LRU）、5.1、5.3、5.4。

---

## 0. 背景与延迟来源（必读）

`answer_question` 当前的串行调用链（每次用户提问都会跑）：

1. `rewrite_query` — 1 次 LLM 调用 ([rag/rag_pipeline.py:156](rag/rag_pipeline.py#L156))
2. `route_query` — 启发式 + 可能 1 次 LLM 调用 ([rag/rag_pipeline.py:159](rag/rag_pipeline.py#L159), [rag/router.py:132-189](rag/router.py#L132-L189))
3. `_run_routed_retrieval` — 走 strategy，里面可能嵌套
   - `decompose_query` (1 次 LLM)
   - 对每个子问题 → `generate_query_variants` (1 次 LLM) → `retrieve_layered_context` (3 次串行检索: primary + priors + regulatory) → 每次检索内部又是 `retrieve_hybrid` (vector + BM25 并行) ([rag/strategies.py:108-126](rag/strategies.py#L108-L126), [rag/retriever.py:73-110](rag/retriever.py#L73-L110))
4. `build_graph_context` — Neo4j 查询，**始终在 retrieval 之后串行执行** ([rag/rag_pipeline.py:199-207](rag/rag_pipeline.py#L199-L207))
5. `generate_openai_rag_answer` / `generate_prediction` — 最终生成 1 次 LLM 调用

延迟乘积最严重的路径是 `layered` 策略 + `RAG_DECOMPOSE_ENABLED=True`：
**`N_subq × (1 LLM for multi_query + 3 retrieval layers × (vector + BM25))`**，且 **`N_subq` 这层是 for 循环串行**。

下面任务按 ROI 排序，**每个任务独立可合并**。

---

## 1. 通用约束（所有任务都要遵守）

- **不要**修改默认返回结构（`answer`, `sources`, `graph_sources`, `backend`, `routing`, `sub_queries`, `retrieval_strategy`, `fusion_method` 这些字段必须保留）。
- **不要**改变 `STRATEGY_REGISTRY` 的 keys。
- **不要**删除回退链 (`fallback_chain`)。
- 所有 LLM/Neo4j 调用必须保留现有的 try/except 行为；优化不能让某条路径在异常时静默吞掉错误。
- 凡是新增缓存：必须有 TTL **或者** 进程内 LRU（不要全局无限增长）。
- 凡是新增并发：必须用 `ThreadPoolExecutor`（仓库已有的模式，见 [rag/retriever.py:44](rag/retriever.py#L44)，[rag/retriever.py:117](rag/retriever.py#L117)），不要引入 asyncio。
- 改完任意一项跑：`python -m pytest tests/ -x` 通过。

---

## 2. Phase 0 — 加阶段计时（必须先做）

**目标**: 在做任何优化前，先在日志里打出每个阶段耗时，后续每条优化都能在真实 query 上验证收益。

### 任务 0.1: 在 `answer_question` 增加分段计时

文件: [rag/rag_pipeline.py](rag/rag_pipeline.py)

在 `answer_question` 函数顶部加 `import time`（如果还没），然后在以下边界各取一次 `time.perf_counter()`:

| 阶段 | 起点 | 终点 |
|---|---|---|
| `rewrite` | 函数进入 | `rewrite_query` 返回后 |
| `route` | rewrite 后 | `route_query` 返回后 |
| `retrieval` | route 后 | `_run_routed_retrieval` 返回后 |
| `graph` | retrieval 后 | `build_graph_context` 返回后 |
| `generate` | graph 后 | answer 生成完成（无论 openai / local / fallback / predict）|
| `total` | 函数进入 | return 前 |

实现要点:
- 用一个 dict `timings: Dict[str, float] = {}` 收集 ms。
- 在每个 return 之前打一行日志: `print(f"[rag.timing] mode={resolved_mode} strategy={...} timings_ms={timings}")`
- 把 `timings` 也放进返回 dict 的新字段 `"timings_ms": timings`（前端可以忽略）。
- 不要影响 chitchat / no_context / predict 几个早 return 路径——它们也要打日志。

### 任务 0.2: 在 strategy 内部加计时

文件: [rag/strategies.py](rag/strategies.py)

在 `LayeredStrategy.run` 和 `DecompositionStrategy.run` 里，对每个子问题加 `t0 = time.perf_counter()` ... `print(f"[rag.timing] subq={i} took_ms={...:.0f}")` —— 这是为了验证下面第 4 节的子问题并行化收益。

### 验收

跑一条真实 query，日志里看到例如:

```
[rag.timing] mode=ask strategy=layered timings_ms={'rewrite': 420, 'route': 12, 'retrieval': 6800, 'graph': 380, 'generate': 1900, 'total': 9512}
[rag.timing] subq=0 took_ms=2100
[rag.timing] subq=1 took_ms=2300
[rag.timing] subq=2 took_ms=2400
```

**先把这一步合并，跑几条线上常见 query 把真实分布发出来，再决定后面哪条优先做。**

---

## 3. Phase 1 — 零风险并行化（最大 ROI）

### 任务 3.1: `retrieve_layered_context` 三层并行

文件: [rag/retriever.py:73-110](rag/retriever.py#L73-L110)

**当前**: primary / priors / regulatory 是 3 次串行检索。
**改为**: 用 `ThreadPoolExecutor(max_workers=3)` 同时发起。

实现细节:
- primary 有一个 "no domain filter 回退" 的逻辑 ([rag/retriever.py:90-96](rag/retriever.py#L90-L96))，回退必须保留：把 primary 单独跑、拿到结果后再判断；priors 和 regulatory 在外面线程池里和 primary 第一次调用一起并发。
- 更简单写法：把 primary（含回退逻辑）封装到一个内部函数 `_run_primary()`；priors / regulatory 各自一个函数。三个函数提交到线程池，`as_completed` 取结果。
- 异常处理: 任何一层抛错都不要让其他层失败 —— 单层失败返回 `[]`，并 `print(f"[rag.layered] layer={name} failed: ...")`。

预期收益: 该函数总耗时从 `3×T` 降到 `~max(T_primary, T_priors, T_reg)`，常见场景能省 1.5–3 秒。

### 任务 3.2: `_retrieve_decomposed` 子问题并行

文件: [rag/strategies.py:108-126](rag/strategies.py#L108-L126) 和 [rag/rag_pipeline.py:438-471](rag/rag_pipeline.py#L438-L471)

**两份几乎重复的实现都要改**（也可以顺手把 `rag_pipeline.py` 里那份 dead code 删掉，但请先确认没有外部 import；可用 `grep -rn "_retrieve_decomposed_layered_context" .` 校验）。

**当前**: `for subquestion in subquestions: ...` 串行。
**改为**: 把循环体抽成 `_run_subquestion(subq) -> dict`，外层用线程池并发。

实现细节:
- `max_workers = min(len(subquestions), 4)`（避免太多并发把 OpenAI rate limit 打爆，也避免压垮 Neo4j）。
- 输出聚合后顺序按子问题原始顺序保留（用 `executor.map` 或者 `submit` + 按 index 排序）。
- 失败的子问题返回空，继续聚合其他子问题。

预期收益: `N×T_layered` → `~T_layered`，3 个子问题场景能省 ~5 秒（最大头之一）。

### 任务 3.3: Graph context 与 retrieval 并行

文件: [rag/rag_pipeline.py:183-207](rag/rag_pipeline.py#L183-L207)

**当前**: `_run_routed_retrieval` 完成后才调 `build_graph_context`。但 graph context 不依赖 retrieval 结果（除了用 `sources` 推导 `document_ids` 兜底，见 [rag/rag_pipeline.py:565-570](rag/rag_pipeline.py#L565-L570)）。

**改为**:
- 如果 `retrieval_filters` 里已经有 `document_ids` 或 `preferred_document_id`：把 `build_graph_context` 和 `_run_routed_retrieval` 用线程池**同时**发起。
- 如果没有（要靠 sources 推导）：保留现在的串行行为，或者更激进 —— 用一个保守的 graph filter 先跑，retrieval 完了再决定是否复用。先做保守路径就行。

实现细节:
- 不要把 graph 调用提到 `chitchat` 早 return 之前。
- 用 `concurrent.futures.ThreadPoolExecutor(max_workers=2)`，先 `submit` retrieval，再 submit graph（若可并行），都 `result()` 拿回来。

预期收益: 节省一个 Neo4j round-trip（300ms – 1.5s 不等）。

---

## 4. Phase 2 — 缓存（中等改动，命中后非常香）

### 任务 4.1: `rewrite_query` 增加 LRU 缓存

文件: [rag/query_rewriter.py](rag/query_rewriter.py)（请先 Read 一遍确认接口）

要点:
- 缓存 key = `(query, hash(history_block))`，**不要**直接拿整个 history 字符串当 key（太大），用 `hashlib.sha1(history_block.encode()).hexdigest()[:16]`。
- 用 `functools.lru_cache(maxsize=512)` 套一层内部函数即可；或者用全局 dict + 简单 LRU。
- TTL: 进程生命周期内有效就行，无需持久化（同一会话内的重复改写很常见，例如用户连发同一个问题）。
- 只缓存成功的结果；异常路径不要污染缓存。

### 任务 4.2: `route_query` 增加 LRU 缓存

文件: [rag/router.py:36](rag/router.py#L36)

只缓存 **LLM router 路径** 的结果（`_route_with_llm`）。启发式路径已经够快了。
key: `(query, mode, hash(history_block))`。

### 任务 4.3: `generate_query_variants` 缓存

文件: [rag/multi_query.py:38](rag/multi_query.py#L38)

key: `(query, n_variants, hash(history_block))`。
原因: decomposition 场景下，多次相似 query / 重试场景中 multi-query LLM 调用会被重复触发。

### 任务 4.4: `decompose_query` 缓存

同上，key: `(question, max_subquestions, hash(history_block))`。

### 验收

把同一条 query 连发两次，第二次的 `timings_ms.rewrite`/`route`/`retrieval(inside multi_query)` 应该接近 0。

---

## 5. Phase 3 — 避免不必要的工作

### 任务 5.1: Graph context 在已有充足 sources 时跳过

文件: [rag/rag_pipeline.py:199-207](rag/rag_pipeline.py#L199-L207)

新增配置开关（[configs/settings.py](configs/settings.py)）:
- `RAG_GRAPH_CONTEXT_MIN_SOURCES`（默认 `0`，表示不跳过；可配 `5` 之类）

逻辑: 若 `len(sources) >= RAG_GRAPH_CONTEXT_MIN_SOURCES` 且 `RAG_GRAPH_CONTEXT_MIN_SOURCES > 0`，跳过 graph 调用，返回 `{"text": "", "matched_entities": [], "nodes": [], "edges": [], "skipped_reason": "skipped_sufficient_sources"}`。

**不要**默认打开 —— 先发布开关，让运维灰度。

### 任务 5.2: 短 query 直接绕过 `rewrite_query`

文件: [rag/rag_pipeline.py:156](rag/rag_pipeline.py#L156) 之前

规则: 若 `query.strip()` 不含代词 (`_PRONOUN_PATTERN` / `_CJK_PRONOUN_PATTERN`，见 [rag/router.py:24-25](rag/router.py#L24-L25)) 且 `len(history) == 0`，跳过 rewrite，直接 `retrieval_query = query`，并设置 `rewrite_result = {"query": query, "rewrite_applied": False, "rewrite_backend": "skipped_short_no_history"}`。

这步对所有"首问"都生效，能稳定砍掉 300–800ms。

### 任务 5.3: BM25 索引懒加载 + 启动时预热

文件: [rag/bm25_index.py:57-89](rag/bm25_index.py#L57-L89)

当前已经有 `_index_cache` mtime 缓存，逻辑没问题。但**首次请求**仍要 pickle.load 整个索引（可能几十 MB）。

加一个公开函数 `warm_bm25_index()`，在 [app.py](app.py) 应用启动时调用一次（找 Flask/FastAPI 的 `before_first_request` 或 startup hook）。如果 `load_bm25_index()` 抛 `FileNotFoundError`，吞掉异常并打 warning（不阻塞启动）。

### 任务 5.4: 复用 OpenAI `client` 实例

文件: [rag/router.py:155-167](rag/router.py#L155-L167), [rag/multi_query.py:84-95](rag/multi_query.py#L84-L95)，以及 [rag/openai_answering.py](rag/openai_answering.py)、[rag/prediction.py](rag/prediction.py)、[rag/query_decomposer.py](rag/query_decomposer.py)（请 grep `openai.OpenAI(` 找全）。

**当前**: 每次调用 LLM 都新建 `openai.OpenAI(...)` 客户端。这本身不重，但每次会重建 httpx connection pool。
**改为**: 创建一个 `rag/openai_client.py`，导出 `get_openai_client()`（用 `functools.lru_cache(maxsize=1)`，按 `(OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_TIMEOUT)` 缓存）。把所有调用点换成它。

注意:
- 旧 SDK 分支 (`openai.ChatCompletion.create`) 保留兼容，不需要包客户端 —— 只优化 `hasattr(openai, "OpenAI")` 分支。
- 必须保留每个调用点的 `try/except` 行为。

预期收益: 单次 ~50–150ms，多次 LLM 调用累计就明显了。

---

## 6. Phase 4 — 可选/激进（先讨论再做）

### 任务 6.1: Streaming 生成
[rag/openai_answering.py](rag/openai_answering.py) 改成 `stream=True`，把 token 一路传到前端。TTFT 改善明显，但需要前端 + API 层一起改，是另一个 PR。**本 spec 不做**，仅记录。

### 任务 6.2: 把 `rewrite + route + multi_query` 合并成单次 LLM 调用
理论上可行，prompt 设计 + 输出 schema 都要重写。**本 spec 不做**。

---

## 7. 实施顺序（推荐）

1. **Phase 0 (任务 0.1, 0.2)** — 先合并，跑真实数据验证瓶颈。
2. **任务 3.1, 3.2, 3.3** — 三个并行化，互不冲突，可以一个 PR 也可以拆成三个。
3. **任务 5.4** — 复用 client，机械改动。
4. **任务 4.1 – 4.4** — 缓存，逐个加。
5. **任务 5.2, 5.3** — 小优化。
6. **任务 5.1** — 配置开关，发布后灰度。

---

## 8. 测试要求

每完成一项:

1. `python -m pytest tests/ -x` 必须通过。
2. 至少手工跑 3 条 query 对比 before/after `timings_ms`：
   - 一条简短的 chitchat（"hi"）
   - 一条普通 ESG 提问
   - 一条复合 / 长 query（触发 decomposition）
3. 把 timings 对比贴到 PR 描述里。

---

## 9. 改动文件清单（速查）

| 文件 | 任务 |
|---|---|
| [rag/rag_pipeline.py](rag/rag_pipeline.py) | 0.1, 3.3, 5.2 |
| [rag/strategies.py](rag/strategies.py) | 0.2, 3.2 |
| [rag/retriever.py](rag/retriever.py) | 3.1 |
| [rag/query_rewriter.py](rag/query_rewriter.py) | 4.1 |
| [rag/router.py](rag/router.py) | 4.2, 5.4 |
| [rag/multi_query.py](rag/multi_query.py) | 4.3, 5.4 |
| [rag/query_decomposer.py](rag/query_decomposer.py) | 4.4, 5.4 |
| [rag/openai_answering.py](rag/openai_answering.py) | 5.4 |
| [rag/prediction.py](rag/prediction.py) | 5.4 |
| [rag/bm25_index.py](rag/bm25_index.py) | 5.3 |
| [app.py](app.py) | 5.3 (启动预热) |
| [configs/settings.py](configs/settings.py) | 5.1 (新配置项) |
| `rag/openai_client.py` (新) | 5.4 |

---

## 10. 千万不要做的事

- 不要把整个 pipeline 改成 async/await —— 现有代码全部 sync，混用会引入大量回归。
- 不要把缓存写到磁盘 / Redis（除非用户明确要求），先用进程内 LRU。
- 不要为了"清理"删掉 `rag_pipeline.py` 里的 `_retrieve_decomposed_layered_context` 之类看起来重复的函数，**先 grep 调用方**。
- 不要默认改 `RAG_DECOMPOSE_ENABLED` / `RAG_MULTI_QUERY_ENABLED` 之类的配置默认值 —— 只优化在它们开着时的延迟。
- 不要在并行化时把 `print(...)` 日志删掉，保留所有现有 fallback 日志。
- 单个子任务尽量保持 diff < 200 行，便于 review。
