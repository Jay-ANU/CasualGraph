# Tasks for Codex — Agent 效果优化

> 目标读者：Codex / Cursor 类 coding agent
> 目标：在不改变现有用户场景的前提下，显著提升 RAG Agent 的**召回质量、生成可信度、感知延迟、反馈闭环**。
> 项目入口：`rag/rag_pipeline.py` 的 `answer_question`；前端入口 `frontend/src/pages/Agent.tsx`。
>
> **核心原则（先读这条再开干）**：
> 1. **先建反馈、再调召回、最后调生成**。所有"优化"都需要可量化收益。
> 2. **不要做 multi-agent 改造**（成本爆炸、当前任务复杂度不需要）。
> 3. **每个任务独立可合并**，按 P0 → P1 → P2 顺序做。
> 4. **每个改动必须保留 `timings_ms` 埋点**（用于前后对比）。
> 5. **不要破坏现有 SSE 流式接口契约**（前端依赖）。

---

## 1. 当前架构速记（动手前必读）

### 在线问答路径
```
user query
  → query_rewriter (LLM)
  → router (启发式 + LLM 兜底)
  → strategy (vector_only / hybrid / layered / decomposition / graph_first)
  → graph_context (与 retrieval 并行)
  → LLM 生成 (Flash: OpenAI / Deep: Claude)
  → SSE Stream
```

### 关键文件
| 文件 | 作用 |
|---|---|
| `rag/rag_pipeline.py` | 主流程编排 + `timings_ms` 埋点 |
| `rag/router.py` | 启发式 + LLM 路由决策 + LRU 缓存 |
| `rag/strategies.py` | 5 种检索策略实现 |
| `rag/retriever.py` | 向量检索 + BM25 + 三层并行 |
| `rag/bm25_index.py` | 本地 BM25 索引 |
| `rag/query_rewriter.py` | 代词消解 + 上下文改写 |
| `rag/query_decomposer.py` | 复合问题拆分 |
| `rag/graph_context.py` | Neo4j 图查询 |
| `rag/openai_answering.py` | 答案生成 + streaming |
| `chat_memory_service.py` | Redis 短期记忆 + 摘要压缩 |
| `notifications/` | HITL 兜底通知 |
| `frontend/src/pages/Agent.tsx` | 主聊天界面 |
| `frontend/src/components/PredictionAnswer.tsx` | 预测答案渲染 |

### 当前评测基线
- 评测集：`evals/` 下 200 条标注 query × 平均 5 个相关 chunk
- 当前指标：Recall@5 = 88%、Citation Precision ~93%、Faithfulness ~90%、复合 query P95 ~6s

---

# P0 任务（最高 ROI，本月做完）

## P0-1：用户反馈循环（点赞 / 点踩 + 原因标注）

### 背景
**这是所有其他优化的前提**。当前没有真实反馈数据，所有调优都靠人工抽检。建反馈循环后，bad case 能自动进评测集，形成数据飞轮。

### 涉及文件
- 前端：`frontend/src/pages/Agent.tsx` 的答案渲染区
- 后端新增：`app.py` 加 `/feedback` 端点
- 数据存储：复用现有 SQLite（`backend/causalgraph.db`），新增 `answer_feedback` 表
- 类型：`frontend/src/types/api.ts` 加 `FeedbackPayload` 类型

### 实现步骤
1. **数据库 schema**（先迁移）：
   ```sql
   CREATE TABLE IF NOT EXISTS answer_feedback (
     id            INTEGER PRIMARY KEY AUTOINCREMENT,
     user_id       TEXT NOT NULL,
     session_id    TEXT NOT NULL,
     message_id    TEXT NOT NULL,
     query         TEXT NOT NULL,
     answer        TEXT NOT NULL,
     rating        TEXT NOT NULL,           -- 'up' | 'down'
     reason_tags   TEXT,                    -- JSON array: ['missing_evidence', 'wrong_citation', 'hallucination', 'irrelevant']
     reason_text   TEXT,                    -- 用户填的可选自由文本
     sources_json  TEXT,                    -- 当时返回的 sources 数组（JSON）
     timings_json  TEXT,                    -- 当时的 timings_ms（JSON）
     created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   CREATE INDEX idx_feedback_rating ON answer_feedback(rating, created_at);
   ```

2. **后端 API**：
   - `POST /feedback`：写入一条反馈
   - `GET /admin/feedback/recent?rating=down&limit=50`：管理员查看最近差评（已有 admin auth 复用）
   - 鉴权：用现有 JWT auth pattern（参考 `app.py` 里其他 endpoint）

3. **前端 UI**：
   - 每条 agent 回答下方加 `👍 👎` 两个 icon 按钮（用 lucide-react 的 `ThumbsUp` / `ThumbsDown`）
   - 点 👎 弹一个 inline 下拉，允许选 ≥1 个标签：
     - `Missing evidence`（漏证据）
     - `Wrong citation`（引用错位）
     - `Hallucination`（编造）
     - `Irrelevant`（答非所问）
     - `Other`（可填自由文本）
   - 点 👍 直接提交，无 reason 收集
   - 提交后按钮变 active 状态，不允许重复提交（前端本地标记 + 后端去重）

4. **样式**：用现有 MiniMax 设计系统的 `cg-btn-icon` 风格

### 验收
- [ ] 数据库表创建成功，能写入 + 查询
- [ ] 前端点赞 / 点踩按钮可见、可点击
- [ ] 点踩弹出标签选择，提交后写入数据库
- [ ] `GET /admin/feedback/recent` 能返回最近差评
- [ ] 不影响 SSE 流式接口

### 风险
- 用户隐私：原始 query 和 answer 都进库，需要在隐私政策里写明
- 滥用：同一 message_id 不允许重复提交（数据库唯一约束）

### 估时
3-5 天

---

## P0-2：流式输出 + 首 token 优化

### 背景
当前用户等 4-6s 才看到完整答案。SSE 已经在用，但前端实际是**等完整 answer 拼好再渲染**，浪费了流式能力。

### 涉及文件
- 前端：`frontend/src/pages/Agent.tsx` 的 SSE 处理逻辑
- 后端：`rag/openai_answering.py` 的 `stream_openai_rag_answer`（确认已经按 token 推送）
- 类型：`frontend/src/types/api.ts` 的 `RagStreamEvent`

### 实现步骤
1. **检查后端**：
   - 确认 `stream_openai_rag_answer` 在每个 token 到达时立即 yield SSE `data:` 帧
   - 如果是攒齐后才 yield，改成 chunked 推送
   - 首帧应包含 `meta` 事件（含 `mode`、`strategy`、`session_id`），用户立刻看到"正在检索…"等状态

2. **前端流式渲染**：
   - 当前 `readSseEvents` 已经能边解析边触发 `onEvent`，但 React 状态更新可能 batched
   - 用 `useReducer` + `flushSync` 强制每个 token 立即更新 DOM
   - 或者用 `useDeferredValue` 让滚动跟随 token 流

3. **首 token 显示进度**：
   - 收到 `meta` 事件后立刻显示 "Retrieving…" → "Generating…" 进度条
   - 收到第一个 `token` 事件后切到答案渲染
   - 进度显示用 `getLoadingSteps(mode)` 已有的步骤文案

4. **流式 Markdown 渲染**（关键）：
   - 当前 `ReactMarkdown` 在不完整 markdown 上会有渲染问题（比如 ``` 没闭合）
   - 解决：用 `react-markdown` + 容错插件，或者每次 token 到达时做轻量"补全"（自动补 ``` 之类）

### 验收
- [ ] 后端：单条 SSE 帧延迟 < 50ms（用 `curl` 测试）
- [ ] 前端：首 token 渲染时间 < 1.5s（用 Performance API 测）
- [ ] 流式过程中 markdown 不闪烁、不报错
- [ ] 用户能在生成中途滚动 / 复制部分内容

### 风险
- React 频繁 re-render 可能掉帧 → 用 React DevTools Profiler 验证
- 不要破坏 `done` 事件附带的 `sources` / `timings_ms` 渲染

### 估时
5-7 天

---

## P0-3：Cross-encoder Reranker（最高 ROI 的检索改进）

### 背景
当前 RRF 融合后 top-5 直接进 prompt。但 RRF 本质是基于排名的启发式融合，没有真正"理解"query 和 doc 的语义相关性。
**加一层 cross-encoder rerank**（对 query-doc 对做 BERT-style 打分）是工业界公认的最稳的 hack，预期 Recall@5: 88% → 93-95%。

### 涉及文件
- 新增：`rag/reranker.py`
- 改：`rag/retriever.py`（在 `retrieve_hybrid` 之后插入 rerank 阶段）
- 改：`rag/strategies.py`（5 个 strategy 都接 rerank）
- 配置：`configs/settings.py` 加 `RERANKER_ENABLED`、`RERANKER_MODEL`、`RERANKER_TOP_K_BEFORE`、`RERANKER_TOP_K_AFTER`

### 实现步骤
1. **选型**（先调研再决定）：
   - 选项 A：本地 `BAAI/bge-reranker-v2-m3`（200ms 推理、零成本）— 推荐
   - 选项 B：Cohere `rerank-3.5`（150ms、$0.0003/query）
   - 选项 C：Voyage `rerank-2`（200ms、$0.0001/query）
   - 默认走 A；保留 B/C 作为 fallback（配置切换）

2. **新增 `rag/reranker.py`**：
   ```python
   class Reranker:
       def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
           # lazy load on first call
           ...

       def rerank(
           self,
           query: str,
           candidates: List[RetrievedChunk],
           top_k: int = 5,
       ) -> List[RetrievedChunk]:
           """对每个 (query, candidate) 对打分，返回按分数降序的 top_k。"""
           ...
   ```
   - 用 `sentence-transformers` 的 `CrossEncoder` API
   - **支持批处理**：一次 forward 算所有候选对的分数（不要循环单次推理）
   - 单例：reranker 模型在进程内只 load 一次

3. **集成到 `retrieve_hybrid`**：
   - 现在：向量召回 top-K + BM25 top-K → RRF 融合 → 返回 top-5
   - 改为：向量 top-30 + BM25 top-30 → RRF 融合 top-20 → **Reranker 重排 top-5**
   - 配置：`RERANKER_TOP_K_BEFORE=20`、`RERANKER_TOP_K_AFTER=5`

4. **降级链**：
   - Reranker 加载失败 / 超时 → fallback 到原 RRF top-5
   - 用 `try/except` 包住，错误进日志但不阻塞回答
   - 加 `RERANKER_ENABLED` 开关，便于灰度

5. **时间预算**：
   - rerank 加 ~200ms
   - 端到端总延迟预算：复合 query P95 < 6.5s（原 6s + 0.5s 允许）
   - 在 `timings_ms` 加 `rerank` 字段，便于监控

### 验收
- [ ] 评测集（`evals/` 下）跑出 Recall@5 ≥ 93%（baseline 88%）
- [ ] 单次 rerank 耗时 P95 < 250ms
- [ ] Reranker 模型加载失败时降级到 RRF，不影响接口
- [ ] `timings_ms` 含 `rerank` 字段
- [ ] `RERANKER_ENABLED=false` 时回到原行为（用于 A/B）

### 风险
- 本地模型加载需要 ~1GB 显存 / 内存 — 部署时确认资源
- 第一次推理冷启动慢（首次 ~3s）— 服务启动时主动 warm up

### 估时
1 周

---

# P1 任务（中等 ROI，下个月做）

## P1-4：HyDE 查询扩展

### 背景
用户的短 query（"NVIDIA 减排做得怎么样"）和 ESG 报告的措辞（"NVIDIA FY2024 报告披露 Scope 1 排放为 X 万吨..."）在 embedding 空间距离远。
HyDE（Hypothetical Document Embedding）让 LLM 先生成一段"假想答案"，用它的 embedding 去检索 —— 对长尾 / 模糊 query 提升明显。

### 涉及文件
- 新增：`rag/hyde.py`
- 改：`rag/strategies.py`（在 `VectorOnlyStrategy` / `HybridStrategy` 里加 HyDE 选项）
- 配置：`configs/settings.py` 加 `HYDE_ENABLED`、`HYDE_MAX_TOKENS`

### 实现步骤
1. **新增 `rag/hyde.py`**：
   ```python
   async def generate_hypothetical_doc(query: str, context: str = "") -> str:
       """让 LLM 基于 query 生成一段假想的 ESG 报告片段。"""
       prompt = f"""You are an ESG analyst. Write a short, factual-sounding
       passage (3-4 sentences) that would directly answer this question.
       Don't say 'I don't know' — just produce a plausible report excerpt.

       Question: {query}

       Passage:"""
       return await call_llm(prompt, max_tokens=200, model="gpt-5.4-mini")
   ```

2. **集成到检索流程**：
   - 用 HyDE 文本的 embedding **替代** query 的 embedding 去检索
   - 注意：BM25 仍用原 query（HyDE 文本是 LLM 生成的，词频信号反而干扰 BM25）

3. **触发条件**（避免对简单 query 浪费 LLM 调用）：
   - 仅在 `strategy = layered / decomposition` 时启用
   - 或者：query 长度 < 10 token 时启用（说明 query 太短可能 underspecified）
   - 加 LRU 缓存（同 query 的 HyDE 结果可复用）

4. **降级**：
   - LLM 调用失败 → 用原 query embedding
   - HyDE 文本生成内容过短（< 50 字符）→ 用原 query embedding

### 验收
- [ ] 评测集上 Recall@5 再提 +3pp（93% → 96%）
- [ ] HyDE 调用增加的延迟 P95 < 300ms
- [ ] LRU 缓存命中率 ≥ 30%
- [ ] `HYDE_ENABLED=false` 时回到原行为

### 风险
- LLM 生成的"假想答案"如果离谱（比如编造公司名），反而会污染检索
- 缓解：HyDE 文本只用于 embedding，**不进入最终 prompt**（用户看不到）

### 估时
1 周

---

## P1-5：结构化输出 + 强制 citation

### 背景
当前 prompt 里写 "请引用 sources"，但模型有时候忘了 / 引用错位 / 引用了不相关的 chunk。
用 function calling 强制输出 schema，每个 claim 都关联 chunk_id —— Citation Precision 从 93% → 98%+。

### 涉及文件
- 改：`rag/openai_answering.py`
- 改：`rag/prediction.py`（PredictionAnswer 已经是结构化的，可参考其 schema 风格）
- 改：`frontend/src/components/PredictionAnswer.tsx`（统一渲染）
- 改：`frontend/src/types/api.ts` 加 `StructuredAnswer` 类型

### 实现步骤
1. **定义 schema**：
   ```python
   structured_answer_schema = {
     "type": "object",
     "properties": {
       "summary": {"type": "string", "description": "One-paragraph overall answer."},
       "claims": {
         "type": "array",
         "items": {
           "type": "object",
           "properties": {
             "text": {"type": "string"},
             "citations": {"type": "array", "items": {"type": "string"}},  # chunk_id list
             "confidence": {"type": "string", "enum": ["high", "medium", "low"]}
           },
           "required": ["text", "citations"]
         }
       }
     },
     "required": ["summary", "claims"]
   }
   ```

2. **改 `openai_answering.py`**：
   - 用 OpenAI structured outputs / Claude tool use 强制输出 schema
   - prompt 里明确：每个 claim 必须至少 cite 1 个 chunk；如果 claim 是常识 / 无法 cite，confidence 标 'low'

3. **后端校验**：
   - 解析模型输出后，校验所有 cited `chunk_id` 都在本次 sources 列表里
   - 不在 → 删除该 citation 并标记 warning（不阻塞返回）

4. **前端渲染**：
   - 把 `summary` 渲染为主答案
   - 每个 `claim` 的 citation 渲染为可点击 chip（点击高亮对应 source）
   - `confidence=low` 的 claim 用浅灰 + 标签提示

5. **流式适配**：
   - structured output 也支持流式，但需要 partial JSON 解析
   - 用 `json-stream` / `jsonpartial` 库逐 token 解析

### 验收
- [ ] 评测集上 Citation Precision ≥ 98%（每条 citation 都能在 sources 里找到 + 真的相关）
- [ ] 前端 claim-citation 跳转能工作
- [ ] 流式渲染过程中 partial JSON 不报错
- [ ] 答案的 "Faithfulness" 指标（人工抽检 50 条）≥ 95%

### 风险
- 结构化输出可能让模型"省略"自由发挥的部分 — 监控用户点踩率有没有上升
- 流式 partial JSON 解析容易踩坑 — 加超时 + 兜底渲染

### 估时
1-2 周

---

## P1-6：Bad Case 自动评测集闭环

### 背景
评测集 200 条是冷启动手工标的，覆盖不到真实用户的长尾问题。
建立 "点踩 → staging → review → 正式评测集" 的闭环，让评测集滚动扩充到 1000+ 条。

### 涉及文件
- 后端：`evals/` 新增 `evals/staging.py`、`evals/promote.py`
- 后端：`scripts/ingest_feedback_to_staging.py`（定时任务）
- 前端：`frontend/src/pages/Admin.tsx` 加"Pending Feedback Review"区
- 数据：`evals/eval_set_v2.jsonl`（升级版评测集）

### 实现步骤
1. **Schema 设计**：
   ```jsonl
   {"query": "...", "ground_truth_chunks": ["chunk_id_1", "chunk_id_2"], "ground_truth_answer": "...", "tags": ["scope-1", "comparison"], "source": "user_feedback" | "manual"}
   ```

2. **流程**：
   - 每天定时跑 `ingest_feedback_to_staging.py`：把昨天的 👎 反馈 + answer 写到 `evals/staging.jsonl`
   - Admin 在 Web 后台看到 staging 列表，逐条 review：
     - 标 ground truth chunks（从当时返回的 sources 里选 + 可手动添加）
     - 标 ground truth answer（可改写当时的回答）
     - 标 tags
     - 一键 "Promote to eval set" → 写入 `eval_set_v2.jsonl`

3. **后端 API**：
   - `GET /admin/feedback/staging?status=pending`：返回待 review 的反馈
   - `POST /admin/feedback/staging/:id/promote`：标注完成后晋级到正式评测集
   - `POST /admin/feedback/staging/:id/discard`：丢弃（low-quality 反馈）

4. **评测脚本升级**：
   - `evals/run_eval.py`（如果还没有就新建）：跑整个评测集，输出 Recall@5、Citation Precision、Faithfulness
   - 每次发版前 CI 自动跑 → 退化超过 2pp 阻断合并

### 验收
- [ ] Admin UI 能浏览 staging、标注 ground truth、晋级
- [ ] `eval_set_v2.jsonl` 滚动扩充（1 个月后 ≥ 500 条）
- [ ] `evals/run_eval.py` 一键跑出主指标
- [ ] CI hook 接入（每次 PR 跑评测）

### 风险
- 标注质量：可能需要培训 + 双标。先单标 + 抽样复标，标注一致率 < 90% 则重培训
- 评测集污染：测试集和训练集（如果做 fine-tuning）必须严格分离

### 估时
2 周

---

# P2 任务（长期，3-6 个月）

## P2-7：多模态扩展（表格 + 图表）

### 背景
ESG 报告 30-40% 的关键数据在**表格和图表**里（排放数据表、董事会结构图、能源结构饼图）。当前 ingestion pipeline **只处理文本**，这部分数据完全丢失。

### 涉及文件
- `document_processing/`：新增 `table_extractor.py`、`figure_extractor.py`
- `ai_service/extractor.py`：扩展支持表格输入
- `graph/neo4j_store.py`：表格里的 (metric, value, year) 三元组也要进图谱
- `pipeline_runtime.py`：ingestion 流程加 vision 阶段

### 实现步骤
1. **表格检测**：
   - PDF 用 `camelot` / `pdfplumber` / `unstructured.io` 提取表格区域
   - 输出结构化的 `pandas.DataFrame`

2. **表格语义化**：
   - 让 Vision LLM（Gemini 2 / GPT-5 vision）看表格图 + 上下文标题
   - 输出：`{"metric": "Scope 1 emissions", "values": [{"year": 2023, "value": "X", "unit": "tCO2e"}, ...]}`

3. **图表（饼图/柱状图）处理**：
   - 类似流程：vision model 输出结构化数据
   - 难点：图表注解可能在图外面（图例、文字说明） — 需要 layout-aware 处理

4. **入库**：
   - 表格 / 图表数据进入两个地方：
     - **向量库**：作为特殊 chunk（带 `type=table` metadata）— 用户问"NVIDIA 2023 排放数字"时能召回
     - **知识图谱**：(NVIDIA, scope1_emissions_2023, X tCO2e) 三元组 — 用户做对比时直接 graph query

### 验收
- [ ] 表格 chunk 占比 ≥ 20%（说明真的处理了）
- [ ] 评测集中"数字类查询"的 Recall@5 提升 +10pp
- [ ] 图谱里 (entity, metric, value, year) 关系数量 + 50%

### 风险
- Vision API 成本高（$0.01-0.05 / 页）— 仅在 ingestion 阶段算一次，缓存结果
- 表格 OCR 错误率高 — 重要表格人工 review

### 估时
1.5-2 月

---

## P2-8：领域微调专门的 ESG QA 生成器（可选）

### 背景
通用大模型生成的答案风格不够"ESG 报告"。如果有充足的高质量 QA 对（≥ 500 条），可以微调一个专门的 generator。
但**这不是必须做的**——通用模型 + 好的 prompt 已经够用。仅在 P1 全做完后还想压榨质量再考虑。

### 涉及文件
- 训练脚本：`esg_qlora_adapter/`（已有 ESG 抽取的微调，可参考）
- 推理：`ai_service/model_loader.py` 加载新 adapter

### 实现步骤
1. 从 `evals/eval_set_v2.jsonl` 抽 ≥ 500 条高质量 QA 对作训练集
2. QLoRA 微调 Qwen2.5-7B-Instruct（参考已有的 `esg_qlora_adapter/`）
3. 推理时：简单 query → 微调小模型，复杂 query → 仍走 GPT/Claude
4. A/B 对比微调版 vs 通用版的 user satisfaction

### 验收
- [ ] 微调版在评测集上 Faithfulness ≥ 95%
- [ ] 推理延迟 ≤ 通用模型（本地推理更快）
- [ ] 用户点赞率不显著下降（A/B 验证）

### 风险
- 微调可能让模型在 ESG 外的话题能力下降 — 保留 fallback 路径
- 训练数据偏差会被放大 — 评测集要严格分离

### 估时
1-2 月

---

# ⛔ 不要做的事

| 看起来要做的 | 为什么先不做 |
|---|---|
| 多 Agent 协作（researcher / writer / critic） | 5-15× 成本，当前任务不需要这种复杂度。详见 `docs/INTERVIEW_SCRIPT.md` 的"为什么不做 multi-agent" |
| 自训练 embedding 模型 | bge-m3 已经够好，自训练成本极高、收益不明 |
| 接 100 个外部工具（计算器 / 网络搜索 / API） | 用户场景是封闭文档查询，扩工具是扩 scope，不是优化 |
| 知识图谱上 GNN embedding | 当前 Cypher 多跳查询已经满足需求 |
| 把所有模型本地化 | bge-m3、reranker 本地是 OK 的，但生成器仍用商用大模型——本地 7B 质量差 10× |

---

# 实施顺序总览

```
Week 1-2   : P0-1 用户反馈循环   (前端 + 后端 + DB)
Week 2-3   : P0-2 流式输出优化   (主要前端)
Week 3-4   : P0-3 Reranker      (后端 + 模型)

Month 2 W1 : P1-4 HyDE
Month 2 W2 : P1-5 结构化 citation
Month 2 W3-4: P1-6 Bad case 评测闭环

Month 3+   : P2-7 多模态  (大工程)
Month 4+   : P2-8 微调   (可选)
```

每个 P0 任务完成后**必须跑评测集**，确认指标改善而不是退化。

---

# 验收的硬指标

| 指标 | 当前基线 | 目标（3 个月后） |
|---|---|---|
| Recall@5 | 88% | **96%** |
| Citation Precision | 93% | **98%** |
| Faithfulness（抽样） | 90% | **95%** |
| 复合 query P95 延迟 | 6s | **5.5s**（即使加了 rerank） |
| 首 token 时间 | 4s | **<1.5s** |
| 评测集规模 | 200 条 | **1000+ 条** |
| 用户反馈数据 | 0 条 | **每周 50+ 条** |

---

# 约束 / 不变量

所有改动必须遵守：

1. **不破坏现有 SSE 接口契约**（前端依赖 `meta` / `token` / `done` 事件）
2. **保留 `timings_ms` 埋点**，每个新阶段加新字段
3. **不删除现有路由策略**（vector_only / hybrid / layered / decomposition / graph_first）
4. **所有新增功能加 feature flag**（`*_ENABLED` 配置），便于 A/B 和回滚
5. **不引入 multi-agent 框架**（CrewAI / AutoGen / LangGraph supervisor）—— 项目当前阶段不需要
6. **跑通 `tests/`**：`python -m pytest tests/ -x` 通过
7. **每个任务的 PR 描述里贴出评测集前后对比**

---

# 参考

- Anthropic, *Building Effective Agents*（2024）— 区分 workflow 和 multi-agent
- Anthropic, *Building Multi-Agent Research System*（2024）— multi-agent 成本数据点（5-15×）
- Microsoft, *RAGAS: Automated Evaluation of Retrieval Augmented Generation*（2023）— 评测方法论
- BAAI bge-reranker-v2: <https://huggingface.co/BAAI/bge-reranker-v2-m3>
- HyDE 原论文: *Precise Zero-Shot Dense Retrieval without Relevance Labels*（Gao et al. 2022）
- 项目内已有的 RAG 设计文档：`RAG_LATENCY_OPTIMIZATION.md`、`docs/INTERVIEW_SCRIPT.md`
