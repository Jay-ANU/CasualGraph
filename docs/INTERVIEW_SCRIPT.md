# 面试脚本总册：CausalGraph AI / RAG Agent

> 使用方式：这不是逐字背诵稿，而是面试时的“发言骨架”。先背熟第 1、2、3 节，再用第 5、6、7 节应对技术深挖。
>
> 资料边界：本文结合了三类资料：大模型/RAG/Agent 基础资料、个人简历、当前项目代码与项目文档。凡是资料或代码不能证明的内容，本文都会用“可以这样补充”“规划方向”“如果有证据再说”来标注，不把推测写成既成事实。
>
> 面试原则：简历里的量化指标可以讲，但必须能解释“指标定义、基线、怎么测、为什么变好、没有完整数据时怎么兜底”。不要为了显得高级而编线上 A/B、评测集规模、客户数量或生产流量。

---

## 1. 开场自我介绍

### 1.1 30 秒版本

您好，我叫朱城成。本科在悉尼大学读金融，硕士在澳国立读计算机，方向偏机器学习、NLP、信息检索和数据库系统。工程经历上，我一方面做过 Java 后端，主要是秒杀、Redis、Kafka、缓存一致性和限流；另一方面主导做了 CausalGraph AI，一个面向 ESG 报告的 RAG Agent 系统，能把 PDF 报告转成可检索、可引用、可图谱推理的知识库，并支持 Flash / Deep 两种回答模式。

### 1.2 90 秒技术面版本

您好，我叫朱城成。本科是 USYD 金融，成绩前 10%，硕士在 ANU 读计算机相关方向，成绩前 5%，课程覆盖机器学习、深度学习、NLP、数据库系统和信息检索。

我的工程经验主要分两块。第一块是 Java 后端，在世界生活做过 Spring Boot + MySQL + Redis + Kafka 的电商业务，重点处理秒杀超卖、一人一单、消息队列异步下单、未支付订单关闭、热点 Key 击穿、缓存穿透、多级缓存、滑动窗口限流这些问题。第二块是 AI 应用开发，在 CausalGraph AI 做了一个 ESG 报告研究 Agent，前端 React，后端 FastAPI，检索侧是 Pinecone 向量库 + 本地 BM25 + RRF 融合，图谱侧用 Neo4j，短期记忆用 Redis，回答侧用 OpenAI Flash 和 Claude Deep 两条路径；离线抽取侧还有一个基于 Qwen2.5-7B-Instruct 的 ESG QLoRA adapter，用来做实体和关系抽取。

这个项目里我最能讲清楚的部分有三块：第一是 RAG 检索链路，为什么要把向量召回、BM25、RRF 和图谱结合；第二是 Agent 工作流，怎么做意图路由、查询改写、复杂问题拆解和 Flash / Deep 分层；第三是工程落地，怎么处理用户文档隔离、Redis 会话记忆、SSE 流式输出、embedding 降级和无答案 HITL 兜底。

---

## 2. 项目一句话和业务背景

### 2.1 一句话

CausalGraph AI 是一个面向 ESG 研究场景的 RAG Agent：用户上传公司 ESG 报告后，系统可以检索私有文档和全局 ESG 知识库，返回带引用、带证据、可追溯的回答，并在复杂问题中结合图谱关系做推理。

### 2.2 为什么这个项目适合 RAG

ESG 报告有几个特点：

- 内容长：一份报告可能上百页，包含环境、社会、治理、风险、供应链、审计等章节。
- 更新快：公司每年发布新报告，标准和监管口径也会变化。
- 强溯源：回答不能只给结论，必须能指回具体原文片段。
- 专业术语多：Scope 1、Scope 2、GHG、ISSB、TCFD、董事会独立性等术语需要精确命中。
- 多跳问题多：用户经常问“某公司目标变化会对供应链审计有什么影响”这种需要证据和推理的问题。

所以这个项目不能只靠通用 LLM。通用 LLM 有知识冻结和幻觉问题；单纯微调也不适合用来“记住报告内容”，因为报告经常更新，且模型参数里的知识不可追溯。我的定位是：RAG 负责动态知识和引用溯源，LoRA/QLoRA 负责学习 ESG 结构化抽取格式、实体类型和关系类型。也就是说，知识不塞进模型参数，领域抽取能力可以通过微调增强。

### 2.3 项目解决的核心痛点

第一个痛点是查找效率。人工在 PDF 里找 ESG 指标很慢，尤其是跨公司、跨年份对比。RAG 可以先定位证据，再生成摘要。

第二个痛点是可信度。普通聊天机器人回答 ESG 问题容易幻觉，CausalGraph 的回答要求带 chunk 引用、图谱来源和可审查的 evidence trail。

第三个痛点是知识闭环。系统答不出的问题会进入人工兜底流程，后续可以把补充材料或标准答案沉淀回知识库。

---

## 3. 按面试流程讲项目

这一节按第三份资料强调的方式组织：先讲业务问题，再讲整体流程，再讲关键技术，不要上来就堆 Pinecone、Neo4j、RRF。

### 3.0 整体架构图（必背 · 白板可默画）

> 面试官说"画一下你的架构"时，你脑子里应该立刻浮现这张图。建议照着先在纸上默画 5 遍再上场。讲的时候按 **客户端 → API 层 → 数据层 → 模型层** 四块顺序讲，再分别补 **在线问答路径** 和 **离线入库路径** 两条流水线。

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                       客户端 · React 前端 (Vercel)                            │
│                                                                              │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│   │ 登录/会话  │  │ 文档上传   │  │ 聊天对话框 │  │ 图谱可视化 │             │
│   └────────────┘  └────────────┘  └────────────┘  └────────────┘             │
│                                                                              │
│   - Flash / Deep tier 切换         - SSE 流式 token 渲染                     │
│   - Markdown + Math (KaTeX) 渲染   - 引用 chip / source 跳转                 │
└──────────────────────────────────────────────────────────────────────────────┘
                              │  HTTPS / SSE (text/event-stream)
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                   API 层 · FastAPI 后端 (Fly.io / Uvicorn)                    │
│                                                                              │
│  ┌──── 鉴权 & 文档 ─────┐  ┌──── RAG Pipeline ──────────────────────────┐    │
│  │ - JWT auth           │  │                                            │    │
│  │ - document_registry  │  │  query  ──► query_rewriter (LLM)           │    │
│  │ - permissions / 配额 │  │           ──► router (启发式 + LLM 兜底)   │    │
│  └──────────────────────┘  │              │                             │    │
│                            │              ▼                             │    │
│  ┌──── 会话记忆 ────────┐  │   strategy ┌─ vector_only                   │    │
│  │ - Redis sliding win  │  │            ├─ hybrid  (vec + BM25 + RRF)   │    │
│  │ - LLM 摘要压缩       │  │            ├─ layered (Deep 默认)          │    │
│  │ - SQLite 归档        │  │            ├─ decomposition (多跳)         │    │
│  └──────────────────────┘  │            └─ graph_first (实体中心)       │    │
│                            │              │                             │    │
│  ┌──── HITL 兜底 ───────┐  │              ▼                             │    │
│  │ - 无答案 → 邮件通知  │  │   graph_context (Neo4j 1-2 跳扩展)         │    │
│  │ - 运营补答案 → 入库  │  │              │                             │    │
│  └──────────────────────┘  │              ▼                             │    │
│                            │   LLM 生成 ──► Flash : OpenAI gpt-5.4-mini │    │
│                            │              └► Deep  : Anthropic Opus 4.7 │    │
│                            │              │                             │    │
│                            │              ▼                             │    │
│                            │   SSE Stream : meta → token* → done        │    │
│                            └────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
        │              │              │              │              │
        ▼              ▼              ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   SQLite     │ │   Redis      │ │  Pinecone    │ │   Neo4j Aura │ │  外部 LLM    │
│   (本地卷)   │ │   (托管)     │ │  (托管)      │ │   (托管)     │ │  Providers   │
│              │ │              │ │              │ │              │ │              │
│ - 用户       │ │ - 短期会话   │ │ - chunk 向量 │ │ - Entity     │ │ - OpenAI     │
│ - 会话归档   │ │ - 滑窗 list  │ │   (bge-m3    │ │ - Relation   │ │ - Anthropic  │
│ - document   │ │ - 摘要 cache │ │    1024 维)  │ │ - Evidence   │ │ - DeepSeek   │
│   registry   │ │ - 7d TTL     │ │ - metadata   │ │   (chunk_id) │ │   (抽取兜底) │
│ - 通知队列   │ │              │ │   filter     │ │ - 1-2 跳查询 │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

#### 在线问答路径（数据流）

```text
1. Client    : 发起 /rag/ask/stream，带 question + reasoning_mode + session_id
2. Memory    : 从 Redis 加载该 session 最近 6 轮 + 摘要
3. Rewriter  : LLM 把"它/这个"等指代补全成完整问题
4. Router    : 决定 strategy（chitchat / vector_only / hybrid / layered / ...）
5. Retrieval : 并行跑 Pinecone 向量召回 + 本地 BM25
6. Fusion    : RRF (1/(k+rank), k=60) 合并 top-K，去重
7. Graph     : 命中 entity → Neo4j 1-2 跳扩展 → graph_context 字符串
8. LLM       : Flash 走 OpenAI，Deep 走 Claude；prompt 含 sources + graph
9. Stream    : SSE 持续推 token；done 事件附 sources / timings / blocks
10. Memory   : 把本轮 Q/A 异步写回 Redis，超过阈值触发摘要压缩
```

#### 离线入库路径（数据流）

```text
1. Upload    : 用户上传 PDF/Markdown，FastAPI 落到 /data/documents/
2. Registry  : 写 document_registry（owner / visibility / 去重哈希）
3. Parse     : PyPDF / unstructured 解析文本，保留页码 / 章节
4. Clean     : 去页眉页脚、断行修复、噪声段过滤
5. Chunk     : 语义边界优先 + 字符上限兜底 (默认 1500/150 重叠)
6. Embed     : bge-m3 批量向量化 → Pinecone upsert (含 metadata)
7. BM25      : token 化后写入本地 BM25 索引
8. Extract   : LLM（Qwen2.5-7B QLoRA 或 DeepSeek/OpenAI 远程）抽实体/关系
9. Graph     : 三元组归一化后写 Neo4j (节点 + 边带 evidence/confidence)
10. Notify   : 任务完成后写 ingestion_jobs 状态，前端轮询拉取进度
```

#### 部署拓扑（生产规划）

```text
                          ┌──────────────┐
   causalgraph.com ─────► │   Vercel     │  (前端静态)
                          └──────────────┘
                                   │
                                   │  axios / fetch (SSE)
                                   ▼
   api.causalgraph.com ───► ┌──────────────┐
                            │   Fly.io     │  (FastAPI, 512MB-1GB)
                            │  + 持久卷    │  (SQLite / 上传 PDF)
                            └──────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
        Pinecone Starter    Neo4j Aura Free    DeepInfra bge-m3 API
        (向量, 免费档)      (图谱, 免费档)     (托管 embedding)
                                   │
                                   ▼
                         OpenAI + Anthropic API
                         (按调用计费)
```

**白板讲解节奏建议**（3 分钟）：
1. **30 秒**：四层（客户端 / API / 数据 / 模型）大框架 —— "上层是 React 前端，中间 FastAPI 跑 RAG，下层四个存储各管一种数据，外面挂三个 LLM 厂商"。
2. **60 秒**：在线问答路径，按 1-10 步顺着箭头讲 ——"用户问完到模型答完，中间经过 rewriter、router、retrieval、fusion、graph、generation 六个关键节点"。
3. **60 秒**：离线入库路径 —— "上传一份 PDF 同时产出三种资产：向量、BM25、图谱"。
4. **30 秒**：选型逻辑收尾 —— "为什么 SQLite 不上 Postgres、为什么 Pinecone 不自建 Milvus、为什么 Redis 不只用 SQLite，都是 MVP 阶段的运维成本权衡"。

### 3.1 先讲项目背景

推荐话术：

> 我做这个项目的出发点不是“想套一个 RAG 框架”，而是 ESG 报告问答天然有三个矛盾：报告内容长、数据要求准、答案必须能审计。直接把 PDF 塞给大模型会超上下文，而且成本很高；只做全文搜索又不能生成综合答案。所以我设计成离线构建知识库、在线检索证据、最后由模型生成带引用回答的架构。

### 3.2 离线入库流程

推荐话术：

> 离线侧主要做文档结构化。用户上传 PDF 或 Markdown 后，后端解析文本、清洗、按语义边界切 chunk，并给 chunk 打上公司、年份、E/S/G 维度、章节来源、上传用户等元数据。之后有两条支路：一条是用 bge-m3 生成 embedding 写入 Pinecone，另一条是抽取实体和关系写入 Neo4j。BM25 索引也会基于 chunk 文本构建，用来补足精确关键词检索。

完整展开版：

> 如果面试官让我完整讲入库，我会按九步讲。第一步是文件接入，用户上传 PDF 或 Markdown，系统先生成 document_id，并记录 owner、visibility_scope、title、category、source_type 这些 registry 信息。第二步是解析，PDF 先转文本，尽量保留页码、章节和段落边界；如果是 Markdown 就保留标题层级。第三步是清洗，处理页眉页脚、断行、重复空白、乱码和过短噪声段。第四步是 chunking，不是固定硬切，而是先按标题、段落、表格这些自然边界切，再用 token/字符阈值控制大小，默认配置里有 `CHUNK_SIZE=1500`、`CHUNK_OVERLAP=150` 这样的量级。第五步是 metadata 标注，每个 chunk 都带 document_id、chunk_id、owner、公司、年份、章节、E/S/G 维度、source_type 和页码线索，后面检索过滤和引用都靠这些字段。第六步是 embedding，用 bge-m3 对 chunk 文本批量向量化，写入 Pinecone 或本地 FAISS/pickle store，同时保存 metadata snapshot。第七步是 BM25 建索引，把同一批 chunk 的 token 和 metadata 持久化，解决术语、年份、公司名这种精确匹配。第八步是 ESG 抽取，用 Qwen2.5-7B-Instruct + QLoRA adapter 或远程抽取模型把 chunk 里的 Organization、Metric、Value、Target、Standard、Initiative 等实体，以及 reports、measured_in、targets、reduces、affects 等关系抽出来。第九步是图谱落库，把抽取结果归一化后写成 graph JSON，并在配置了 Neo4j 时同步到 Neo4j，供 graph context 和可视化使用。

面试官喜欢听的总结：

> 离线入库不是“存一个 PDF”，而是把一份报告同时变成三种可检索资产：向量资产用于语义召回，BM25 资产用于关键词召回，图谱资产用于实体关系和多跳推理。document registry 则负责权限、去重、删除和后续更新。

注意边界：

- 简历写的是支持 PDF / Markdown，代码也有上传和文档处理流程。不要说支持所有 Office 格式，除非你实际验证过。
- chunk 大小可以说“按语义边界 + token/字符阈值控制”，当前配置层面有 `CHUNK_SIZE=1500`、`CHUNK_OVERLAP=150` 这样的默认量级，但面试中不要说所有文档都严格等长。
- 图谱抽取可以说“实体和关系抽取后写入 Neo4j”，不要夸成完整知识图谱平台。

### 3.3 在线问答流程

推荐话术：

> 在线侧用户发来问题后，系统先加载 Redis 里的近期会话作为短期上下文，然后做 query rewrite，把“它”“这个公司”这类指代补全。接着 router 判断问题类型：简单事实查询走 hybrid 检索，复杂对比或多跳问题走 decomposition / layered 检索，需要关系解释时补 Neo4j graph context。检索结果经过 RRF 融合和去重后，作为 evidence block 给 LLM，最后通过 SSE 流式返回答案、引用和 timings。

可以画成：

```text
User question
  -> Redis short-term history
  -> Query rewrite
  -> Router
  -> Retrieval strategy
       -> vector search: Pinecone + bge-m3
       -> lexical search: BM25
       -> graph context: Neo4j
  -> RRF fusion / filtering
  -> LLM answer generation
  -> SSE stream: meta -> tokens -> done
```

### 3.4 Flash / Deep 怎么讲

推荐话术：

> 我们后来把原来的 Ask / Predict 固定模式改成 Flash / Deep。原因是 Predict 固定 JSON 太死，用户问法一变，模型就被格式限制住。现在 Flash 是快速低成本模式，适合事实问答和普通检索；Deep 是深度模式，会更倾向于 layered retrieval、query decomposition 和 graph context，回答格式则保持自由 Markdown，由模型根据问题决定组织方式。

关键点：

- Flash / Deep 是模型和检索深度的 tier，不是“Ask / Predict”这种输出格式。
- 旧的 Predict JSON 渲染已经废弃或保留为兼容死代码。
- Deep 如果 Claude 未配置，会 fallback 到 Flash，保证可用性。

### 3.5 Agent 还是 Workflow

推荐话术：

> 我不会把这个项目吹成完全自主 Agent。它更准确地说是 agentic workflow：主干流程是可控的，router、query rewrite、decomposition 这些节点有模型决策，但不是让模型无限循环调用工具。这样做的原因是 ESG 问答对可控性、可审计性更重要，不能为了“像 Agent”而牺牲稳定性。

如果被问和 ReAct / Plan-and-Execute 的关系：

> Flash 更像单步 RAG；Deep 更接近简化版 Plan-and-Execute：先判断问题是否复杂，再拆子问题、并行检索、聚合证据，最后统一生成答案。我们没有做完整 ReAct 循环，因为当前工具集合和任务空间都比较明确，用确定性 workflow 更容易评估和上线。

---

## 4. 技术选型和替代方案

这一节是面试重点。不要只说“我用了 Redis / Pinecone / Neo4j”，要说为什么、替代方案是什么、缺点是什么、以后怎么迁移。

### 4.1 后端：FastAPI vs Spring Boot vs Node

当前选择：FastAPI。

为什么选：

- Python 生态更适合 RAG、embedding、LLM SDK、文本处理和实验迭代。
- FastAPI 类型约束和 OpenAPI 支持足够好，适合快速构建 API。
- 项目里大量逻辑在 Python RAG pipeline，避免 Java 和 Python 服务拆分带来的部署复杂度。

替代方案：

- Spring Boot：适合高并发交易系统、权限体系和企业后端；你在世界生活项目中用过。但在 LLM/RAG 快速迭代上，Python 生态更直接。
- Node / NestJS：适合前端团队全栈统一，但 ML/RAG 库成熟度不如 Python。

面试补充：

> 如果是纯交易系统我会选 Spring Boot；但这个项目的核心复杂度在检索、embedding、LLM 调用和文本处理，所以 FastAPI 更合适。

### 4.2 前端：React

当前选择：React。

为什么选：

- 项目本身需要复杂交互：聊天、SSE 流式渲染、文档列表、引用 chips、图谱面板、Flash/Deep 切换。
- React 生态和组件化适合快速迭代。
- 当前代码已经围绕 React 和 TypeScript 构建。

替代方案：

- Vue：上手快，但团队/现有代码不是 Vue。
- Next.js：适合 SSR 和营销站；当前主应用更偏登录后工作台，CRA/Vite + React 足够。生产化可以考虑 Next.js 做首页和 SEO。

### 4.3 向量数据库：Pinecone vs Milvus / Qdrant / pgvector / FAISS

当前选择：Pinecone。

为什么选：

- 托管服务，早期不用维护 HNSW 索引、扩容、备份和运维。
- 支持 metadata filter，适合按用户、文档、公司、年份做过滤。
- 和云端部署匹配，方便快速做 Demo 和上线。

替代方案：

- Milvus：适合大规模自建向量检索，但运维复杂，不适合早期 MVP。
- Qdrant：工程体验好，也适合自部署；如果后续要数据不出境，可以迁移。
- pgvector：适合数据量小、已有 PostgreSQL 的团队；优点是事务和权限一致，缺点是大规模 ANN 能力和调优不如专用向量库。
- FAISS：本地实验很快，但不是完整数据库，没有权限、过滤、服务化和备份能力。

保守话术：

> 当前阶段选 Pinecone 是为了降低运维成本和快速上线，不代表它永远最优。等数据规模、合规要求或成本压力上来，可以迁移到 Qdrant/Milvus，或者在已有 PostgreSQL 体系下用 pgvector。

### 4.4 Embedding：策略、模型候选和选型

当前选择：本地 bge-m3，维度 1024。

完整话术：

> embedding 层我把它当成检索系统的底座，而不是简单换一个模型名。我的策略是：文档入库和用户 query 使用同一个 embedding 空间；向量只负责语义召回，不负责精确词全部命中；公司名、年份、Scope 1/2、标准名这种精确匹配交给 BM25；最后用 RRF 融合，避免单一路径失效。

为什么选 bge-m3：

- bge-m3 对中英文混合和长文本检索比较友好，适合 ESG 报告里英文术语和中文查询混合的场景。
- 本地 embedding 可以减少外部 API 调用和成本，也能降低数据出境风险。
- bge-m3 是 1024 维，和当前 Pinecone dense index 设计匹配；比更高维模型更省存储和传输成本。
- 项目支持本地模型目录 `models/BAAI_bge-m3`，也支持通过环境变量指定 `ESG_EMBEDDING_MODEL_PATH`，第一次部署时可以用 `ESG_EMBEDDING_ALLOW_DOWNLOAD=true` 拉模型。
- 项目里已经对 Pinecone 入口做了保护：如果 bge-m3 加载失败降级到 hash fallback，不再把 384 维废向量写入 Pinecone，而是跳过 vector，走 BM25-only fallback。

替代方案：

- OpenAI text-embedding-3-small / large：服务稳定、无需自己加载模型，适合快速上线；缺点是外部 API 成本、数据出境和供应商依赖。
- Qwen Embedding：中文和通用语义能力强，如果查询以中文为主可以作为候选。
- Jina Embeddings：长文本和多语言场景可以考虑，适合对长上下文召回做对比。
- E5 / BGE-large：经典开源 embedding 候选，适合用业务评测集对比。
- MiniLM / 小模型：速度快、成本低，但 ESG 长文本和专业术语下召回上限可能不够。
- Hash fallback：只能作为开发兜底，不能用于生产向量库。这个点要主动说清楚。

怎么选型：

> 我不会只看 MTEB 榜单，而是拿项目自己的问题集评估。核心指标是 Hit@5、MRR、nDCG、引用支撑率、P95 检索延迟、向量存储成本和是否能本地部署。因为 ESG 的问题很特殊，通用榜单高不代表 Scope 1、FY2023、TCFD 这种检索一定好。

入库时的 embedding 策略：

- 对每个 chunk 的正文做 embedding，不把过多 metadata 拼进去，避免污染语义空间。
- metadata 单独存 Pinecone metadata，用 filter 做 owner、document_id、year、source_type、visibility_scope 过滤。
- 对表格或指标类 chunk，尽量把“指标-数值-单位-年份-公司”线性化成自然语言再 embedding。
- 向量检索 topK 不宜过大，因为 Pinecone 返回 payload 有大小限制；项目里有 topK cap 和 payload too large 降级。
- 如果 embedding backend 降级到 hash fallback，线上不能继续写 Pinecone，只能 BM25-only，避免污染索引。

推荐话术：

> 我不是说 bge-m3 永远最好，而是它在这个项目的约束下比较平衡：中英文、长文本、成本、可本地化、1024 维 Pinecone index 兼容。真正严谨的做法是拿项目问题集评估不同 embedding 的 Hit@5、MRR、延迟和成本，然后再决定是否替换。

被追问：

> 为什么不用 LoRA 微调 embedding？

回答：

> 可以做，但不是第一优先级。embedding 微调需要高质量 query-positive-negative 三元组，比如 query、相关 chunk、不相关 hard negative。当前项目收益更大的路径是先做好 chunk、metadata filter、BM25、RRF 和 rerank。等有足够真实 query log 和点击/人工标注后，再考虑对 embedding 或 reranker 做领域微调。

### 4.5 BM25：为什么还需要关键词检索

当前选择：本地 BM25 索引。

为什么选：

- ESG 问题里很多是精确术语，如 Scope 1、Scope 2、GHG、TCFD、ISO 14001、年份和公司名。
- 向量检索擅长语义相似，但对精确 token 有时不稳定。
- BM25 成本低，作为 lexical recall channel 很适合早期项目。

替代方案：

- Elasticsearch / OpenSearch：更适合大规模生产检索，有分词、过滤、排序和集群能力；当前项目体量未必需要。
- Pinecone sparse vector：可以把稀疏检索和向量检索放在同一个服务里，但当前代码事实是本地 BM25 + Pinecone dense，不要说已经用了 Pinecone sparse。

### 4.6 RRF：为什么用 Reciprocal Rank Fusion

当前选择：RRF 融合向量结果和 BM25 结果，并扩展了 channel weights、term coverage boost、diversity penalty。

公式：

```text
score(d) = sum_i weight_i / (k + rank_i(d))
```

为什么选：

- 向量 cosine 分数和 BM25 分数不是一个尺度，直接加权平均需要归一化和调参。
- RRF 只依赖排名，对异构检索器更鲁棒。
- 如果一个 chunk 在 vector 和 BM25 两路都排得靠前，它会自然得到更高分。

替代方案：

- 加权归一化：可解释，但需要调不同 retriever 的分数尺度。
- Cross-encoder rerank：效果通常更好，但延迟更高，适合 top-20 到 top-5 精排，不适合全量召回。
- Learning-to-rank：需要标注数据和训练成本，当前项目阶段不划算。

### 4.7 Rerank：现在怎么说

简历写了“RRF 融合排序与重排”。如果代码里当前 rerank 还不是独立 cross-encoder，面试时要保守。

稳妥说法：

> 我们当前的“重排”主要指融合后的业务规则排序和过滤，比如 RRF、term coverage boost、document diversity penalty。严格意义上的 cross-encoder reranker 是下一步优化方向，可以接 BGE-reranker 或 Cohere Rerank 做 top-N 精排。

不要这样说：

> 我们已经训练了自己的 rerank 模型。

除非你确实做了。

### 4.8 QLoRA 微调：微调了什么，为什么不和 RAG 冲突

当前事实：

- base model：`Qwen/Qwen2.5-7B-Instruct`。
- adapter：ESG QLoRA adapter，默认目录 `esg_qlora_adapter/`，也会自动识别 `qlora_model/esg-qwen2.5-7b-qlora/` 或 checkpoint。
- 加载方式：`ai_service/model_loader.py` 用 PEFT 的 `PeftModel.from_pretrained` 把 adapter 挂到 base model 上，并做进程级缓存。
- 量化：如果 CUDA 和 bitsandbytes 可用，支持 4-bit NF4 量化加载；否则走普通 dtype。
- 使用位置：主要用于 ESG entity/relation extraction，也可以作为本地 QA fallback，但更推荐把它定位成“抽取模型”，不要夸成比云端大模型更强的通用问答模型。

推荐话术：

> 我们有 LoRA/QLoRA 微调，但它不是用来记住每份 ESG 报告的内容，而是用来学 ESG 抽取格式。具体来说，输入是 chunk 文本，输出是结构化 JSON，包括 entities 和 relations。实体类型包括 Organization、Metric、Value、Target、Initiative、Location、TimePeriod、Standard、ESGTopic；关系包括 reports、measured_in、targets、commits_to、reduces、affects、complies_with 等。这样做的价值是把自由文本稳定转成图谱节点和边，后续才能进 Neo4j。

为什么用 QLoRA：

- 全量微调 7B 模型成本高、显存压力大，不适合个人/小团队快速迭代。
- LoRA 只训练低秩 adapter，参数量小，保存和部署成本低。
- QLoRA 再结合 4-bit 量化，能在更小显存上训练或加载，适合 Colab/单卡环境。
- 抽取任务输出格式稳定，适合 SFT/LoRA 学 schema 和领域标签。

为什么不只靠 prompt：

> 纯 prompt 调云端模型可以跑，但成本、延迟和稳定性都受外部 API 影响，而且输出 JSON 容易不稳定。LoRA 的价值是把 ESG schema、实体类型和关系类型固化到本地模型能力里，减少每次 prompt 里反复解释规则的成本。

为什么不把知识微调进模型：

> 报告内容会更新，用户私有文档也不能混进模型参数。我们微调的是“怎么抽取”，不是“记住某份报告里的数值”。事实知识仍然放在 Pinecone/BM25/Neo4j 里，回答时通过 RAG 取证据。

替代方案：

- 纯 Prompt + OpenAI/Claude：效果好、上线快，但成本高、数据出境、输出格式偶尔不稳定。
- DeepSeek / 其他远程模型抽取：适合兜底或对照，缺点仍是外部依赖。
- 规则/正则抽取：对年份、百分比、Scope 指标有效，但对复杂关系、目标承诺、因果表达覆盖不足。
- spaCy / NER 传统模型：轻量，但 ESG 领域实体和关系类型需要大量定制。
- 全量 fine-tuning：可控但成本高，不适合当前阶段。

被追问：

> LoRA 训练数据怎么来？

稳妥回答：

> 主要来自 ESG 报告 chunk 和已有抽取结果/人工修正样本，目标是让模型输出统一 JSON schema。这里不要夸大数据量；如果没有严格统计，就说“开发阶段的小规模领域样本 + 人工校正”，并强调后续要扩充 hard cases。

被追问：

> LoRA 和 RAG 到底谁更重要？

回答：

> 它们解决的问题不同。RAG 解决动态知识和引用溯源；LoRA 解决结构化抽取和格式稳定。没有 RAG，回答会失去可更新证据；没有 LoRA，图谱抽取会更依赖昂贵云端模型或脆弱规则。

### 4.9 Neo4j：为什么用图数据库

当前选择：Neo4j。

为什么选：

- ESG 问题里有实体关系：公司、指标、年份、政策、供应链、风险、治理结构。
- 多跳关系用关系型表也能做，但表达和查询复杂度高。
- Cypher 对“找某公司相关指标、关系、路径”更自然，也方便可视化。

替代方案：

- 关系型数据库 + join / recursive CTE：适合简单层级，不适合频繁多跳路径探索。
- NetworkX：适合本地算法实验，不是持久化图数据库。
- PostgreSQL 图扩展：可以减少组件，但生态和可视化不如 Neo4j。

面试补充：

> 我没有把所有问题都交给图谱。事实查询还是 RAG 检索更有效；图谱主要用于关系解释、多跳线索和可视化，不替代文本证据。

### 4.10 Redis：为什么做短期记忆

当前选择：Redis 存聊天 session 和近期历史。

为什么选：

- 多轮对话读写频繁，每条消息都可能 append 和读取最近 N 条。
- 会话是典型“近期热、远期冷”数据，适合 TTL。
- Redis list/hash 适合快速维护滑动窗口。
- 断开或重启后，只要 Redis 持久化配置正确，刷新页面可以恢复会话。

替代方案：

- PostgreSQL/MySQL：更适合长期审计和强事务，但作为每次请求都读写的短期上下文会更重。
- 浏览器 localStorage：只能本地可见，不适合跨设备和后端生成上下文。
- 只放在内存：服务重启或多实例部署会丢，不能上线。

推荐话术：

> Redis 在这里不是永久数据库，而是短期记忆层。真正需要长期审计的记录，生产上应该异步落 PostgreSQL 或 MySQL。

### 4.11 SQLite / auth.db：能不能上线

当前选择：SQLite auth.db 用于本地/早期用户、会话、管理和通知相关数据。

为什么现在能用：

- MVP 阶段部署简单，不需要额外数据库服务。
- 开发和 Demo 成本低。
- 对低并发后台管理、用户认证和通知队列表足够。

为什么生产要谨慎：

- SQLite 写并发有限。
- 多实例部署时共享文件和锁会麻烦。
- 备份、迁移、权限和审计能力不如 PostgreSQL/MySQL。

面试推荐话术：

> SQLite 是早期 MVP 和 Demo 的选择，不是我认为的最终生产架构。如果正式上线多用户 SaaS，我会把 auth、document registry、audit、notifications 迁到 PostgreSQL；Redis 继续做短期会话；Pinecone/Neo4j 保持专用存储。这样关系型数据、短期内存、向量和图各司其职。

### 4.12 HITL 通知：邮件、SQLite 队列和 MCP 边界

当前事实更稳的说法：

> 无法回答的问题会进入 HITL 队列，系统可以做去重、聚合和邮件 digest，提醒团队补充材料或答案。补充后的知识再走离线入库流程。

MCP 要谨慎：

- 如果你没有完整实现 MCP 协议层，不要说“已经上线 MCP server”。
- 可以说“设计上预留 MCP / tool 接入方向，目前最小可用版先用邮件 digest 和后台队列闭环”。

### 4.13 SSE：为什么用流式

当前选择：SSE。

为什么选：

- Chat 场景是服务端持续推 token，客户端只需要接收，不需要双向实时通信。
- SSE 比 WebSocket 简单，天然支持 HTTP、代理和重连语义。
- 对用户体验而言，首 token 时间比完整生成时间更重要。

替代方案：

- WebSocket：适合双向实时协作、多人同步、音视频或 tool event 交互；当前问题没有必要。
- 非流式 HTTP：实现简单，但用户会等完整回答，体感慢。

---

## 5. RAG / Agent 八股和项目映射

### 5.1 LLM 和 Agent 的区别

LLM 是被动输入输出；Agent 是在目标驱动下，能使用工具、记忆和规划的系统。

项目映射：

- LLM：OpenAI / Claude 负责问题理解、答案组织、引用表达。
- 工具：向量检索、BM25、Neo4j、Redis、文档 registry。
- 记忆：Redis 短期会话，文档知识库作为长期外部知识。
- 规划：router、query rewrite、decomposition、layered retrieval。

推荐话术：

> 我把这个系统定位成 RAG-based agentic workflow，而不是完全自主 Agent。因为业务要求稳定、可审计，所以主流程可控，只在关键节点让模型决策。

### 5.2 RAG 离线和在线

离线：

```text
Load document -> Clean -> Chunk -> Metadata -> Embedding -> Vector DB
                                   -> BM25 index
                                   -> QLoRA entity/relation extraction -> Neo4j
```

在线：

```text
Question -> Rewrite -> Route -> Retrieve -> Fuse -> Generate -> Cite
```

### 5.3 RAG 和 LoRA / Fine-tune 怎么分工

推荐回答：

> 我不会简单说“不微调”。更准确地说，报告里的事实知识不适合微调进模型参数，因为它更新频繁、需要权限隔离、还必须引用原文；但 ESG 抽取格式、实体类型、关系类型是可以通过 LoRA 学的。所以我们的分工是：RAG 存动态知识和证据，QLoRA 负责把 chunk 结构化成 entities/relations，OpenAI/Claude 负责最终自然语言回答和复杂推理。

如果面试官问“为什么不直接把所有 ESG 报告拿去 SFT”：

> 因为这会把私有文档和过期事实写进模型参数，不好删除、也不好解释来源。比如某公司 2023 年 Scope 2 数据更新了，RAG 只需要删旧 chunk、重建向量和图谱；微调模型则要重新训练，而且回答时仍然不能保证引用到具体页码。

如果面试官问“LoRA 的收益是什么”：

> LoRA 的收益主要在结构化抽取：输出 JSON 更稳定，实体和关系类型更贴合 ESG，后续图谱构建更可靠。它不是为了替代 RAG，也不是为了让本地模型比 GPT/Claude 更会聊天。

### 5.4 Chunking 怎么讲

推荐回答：

> chunk 不能太大，否则检索命中后带入 prompt 的噪声多；也不能太小，否则上下文断裂。我一般按语义段落和 token 上限切，保留一定 overlap，并把 company、year、section、ESG dimension、document_id、owner 等 metadata 作为过滤和引用依据。

追问：

> 如果表格很多怎么办？

回答：

> 表格不能简单按行切碎，最好先转成结构化文本，比如“指标-年份-数值-单位-来源页码”，再作为 chunk 入库。否则向量检索很容易丢单位和年份。

### 5.5 Query Rewrite 怎么讲

推荐回答：

> 多轮对话里用户经常说“它的目标呢”“为什么这样”，直接检索会丢实体。query rewrite 的作用是把当前问题和历史上下文合并成完整检索查询，例如把“它的 Scope 2 呢”改写为“Apple 2023 ESG report Scope 2 emissions target”。生成答案仍然用原始问题，改写只服务检索。

### 5.6 Decomposition 怎么讲

推荐回答：

> decomposition 用在复杂问题，比如“比较 Apple 和 Microsoft 的气候目标，并分析对供应链的影响”。这类问题拆成公司 A 目标、公司 B 目标、供应链影响三个子问题，每个子问题独立检索，最后合并证据生成答案。这样比一次检索更容易覆盖多方面证据。

不要夸大：

- 不要说所有问题都 decomposition，会增加延迟和成本。
- 可以说 Deep 模式更倾向使用 decomposition，Flash 默认尽量少拆。

### 5.7 Hybrid Retrieval 怎么讲

推荐回答：

> 向量检索解决语义相似，BM25 解决精确词和术语命中。ESG 里有很多 Scope 1、GHG、年份、公司名，BM25 非常重要。最后用 RRF 融合，避免向量分数和 BM25 分数不在一个尺度的问题。

### 5.8 Rerank 怎么讲

推荐回答：

> 检索通常分两段：第一段 recall，要把可能相关的内容尽量召回；第二段 rerank，在 top-N 里精排。当前项目已经有融合和规则重排，cross-encoder rerank 是后续更明确的优化点。它会更准，但会增加延迟，所以适合 Deep 模式或 top-20 精排。

### 5.9 Memory 怎么讲

短期记忆：

- Redis 存近期消息和 session。
- 滑动窗口控制 prompt 长度。
- 需要时做摘要压缩。

长期记忆：

- 用户上传文档和全局 ESG 资料在向量库/BM25/图谱里。
- 不把所有历史聊天永久塞 prompt。

推荐回答：

> 记忆不是越多越好。短期记忆解决上下文连续性，长期知识库解决事实来源。两者混在一起会导致 prompt 变长、成本上升和幻觉增加。

### 5.10 MCP 怎么讲

资料里提到 MCP 的核心是把工具、资源、提示词通过标准协议暴露给模型或 Host。

项目稳妥口径：

> 我理解 MCP 的价值是让工具调用标准化，比如把检索、通知、文档管理变成可发现的 tools/resources。但当前项目更偏产品 MVP，已经实现的是工具式后端 API 和 HITL 邮件闭环。如果要继续演进，MCP 可以作为下一步把这些工具标准化的协议层。

---

## 6. 简历量化指标：怎么说、怎么测、怎么防拷打

本节非常关键。下面的数字来自你的简历，可以讲，但不要捏造评测细节。推荐统一前置一句：

> 这些数字来自开发阶段的固定问题集、日志对比和人工抽检，属于项目内评估，不是公开 benchmark 或大规模商业 A/B。我可以讲清楚指标定义和优化原因；如果正式上线，我会把这些指标接入自动化 eval 和 dashboard。

### 6.1 引用溯源准确率 92%，错误引用率 18% -> 7%

推荐说法：

> 我们把“答案中的事实是否能被引用 chunk 支撑”作为引用准确率。早期模型容易在答案末尾堆引用，导致某些句子没有真实依据。后来我做了三点：chunk ID 前置、prompt 要求每个关键事实跟引用、生成后检查引用 marker 是否来自候选 sources。这样错误引用率从约 18% 降到 7%，引用溯源准确率达到约 92%。

怎么测：

- 抽取一批典型 ESG 问题。
- 人工标注或人工复核“答案事实是否被引用 chunk 支撑”。
- 统计错误引用：引用不存在、引用 chunk 不支持该结论、回答中有事实但没有引用。

被追问：

> 你们评测集多少条？

稳妥回答：

> 开发阶段是小规模固定问题集加人工抽检，主要用于对比优化前后差异。它不是公开 benchmark，所以我不会把它包装成大规模 A/B。正式上线前我会扩成覆盖事实问答、指标解释、公司对比、多跳推理的 eval set。

被质疑：

> 92% 是否太高？

回答：

> 这个 92% 不是说答案完全正确率，而是“引用是否能支撑答案中事实陈述”的比例。它衡量的是 grounding，不等同于业务判断完全正确。

### 6.2 Top-5 相关内容命中率约 70% -> 88%

推荐说法：

> 这个指标是检索层 Hit@5，也就是答案需要的关键证据是否出现在前 5 个候选 chunk 里。优化前主要靠向量检索，ESG 术语和年份容易漏；加了 BM25、RRF 融合、query rewrite 和 metadata filter 后，相关内容进入前 5 的比例从约 70% 提升到 88%。

怎么测：

- 不看 LLM，只跑 retriever。
- 对每个问题标注或人工判断关键证据 chunk。
- top-5 里出现关键证据就算命中。

被追问：

> 为什么不用 Recall@K / MRR？

回答：

> 可以用，而且更完整。简历里写 top-5 是因为对 RAG 生成来说，top-5 是否包含关键证据最直观。后续我会同时看 Hit@5、MRR、nDCG 和最终答案准确率。

### 6.3 无效检索请求下降约 32%，无证据回答率下降约 40%

推荐说法：

> 原来所有问题都直接检索，像“你好”“继续说”“为什么”这种问题会触发无效检索。后来加入 router 和 query rewrite：闲聊不检索，指代问题先改写，复杂问题拆解，多跳问题补图谱。这样无效检索请求和无证据回答率都有下降。

怎么测：

- 无效检索：检索结果为空、低分、或明显与问题不相关。
- 无证据回答：系统返回“资料不足以回答”的比例。
- 对比 router 上线前后的日志。

被追问：

> 无效检索阈值怎么定？

回答：

> 开发阶段主要用人工抽检和分数分布经验定阈值。更严谨的生产做法是把是否相关做人工标签，然后调 ROC/PR 曲线找阈值。

### 6.4 外部 API 调用量下降约 45%，月度调用成本下降约 38%

推荐说法：

> 之前 embedding 更依赖外部 API。后来用本地 bge-m3 做文档和查询 embedding，同时 BM25 处理精确词查询，不需要每条路径都调用外部 embedding 服务，所以外部 API 调用量下降约 45%。但总成本不是同比下降 45%，因为回答生成模型仍然占一部分成本，所以月度调用成本下降约 38%。

被追问：

> 本地模型不也有机器成本？

回答：

> 是的，所以这个数字是外部 API 调用成本，不是所有基础设施总成本。开发和 Demo 阶段本地模型边际成本低；如果正式生产，要把模型部署成本、机器内存、并发吞吐一起算。

被追问：

> bge-m3 加载失败怎么办？

回答：

> 现在代码里会检测 embedding backend。如果真实模型失败降级到 hash fallback，就不会把 384 维 hash 向量写进 Pinecone，因为 Pinecone 索引是 1024 维。系统会跳过向量检索，退到 BM25-only，并打 warning。这比悄悄写坏向量安全。

### 6.5 平均输入 token 减少约 35%，长对话 P95 延迟约 8s -> 5s

推荐说法：

> 多轮对话如果把所有历史都塞进 prompt，成本和延迟都会爆。我们用 Redis 存 session，但进入模型时只取近期窗口，旧内容做摘要压缩，检索证据也限制 top sources。这样平均 input token 降了约 35%，长对话 P95 延迟从约 8 秒降到 5 秒。

怎么测：

- 记录每次 LLM 请求的 prompt token 数。
- 记录端到端响应时间或 SSE 首 token 时间。
- 对比摘要压缩/滑动窗口前后的日志。

被追问：

> 5 秒是首 token 还是完整回答？

回答：

> 这里要分清楚。用户体感通常看首 token 或可见响应开始时间；完整回答完成时间还取决于输出长度。面试时我会说明这个指标具体按哪个埋点算，避免把 streaming 体感优化说成模型整体计算速度优化。

### 6.6 月均新增 30+ 知识文档，同类问题复发率下降约 50%

风险提醒：这个指标最容易被追问，因为它依赖真实运营闭环。

稳妥说法：

> 这是 HITL 闭环的目标和试点口径。系统会把无答案问题聚合成待处理项，通过邮件 digest 通知团队补充材料或答案，再把补充内容重新入库。试点阶段观察到类似问题重复触发会明显下降。正式上线后，这个指标需要用通知队列和问题指纹持续统计。

如果没有真实月度运营数据，不要说：

> 我们线上稳定每月新增 30+。

可以说：

> 简历里写的 30+ 是项目试点/开发阶段的统计或目标口径，正式商业上线我会重新用 dashboard 校准。

---

## 7. 高频追问与推荐回答

### 7.1 你这个项目最难的点是什么？

推荐回答：

> 最难的不是调用 LLM，而是让答案可信。具体有三层：第一层是检索要召回正确 evidence，第二层是生成不能离开 evidence 乱编，第三层是用户文档和全局知识库要隔离但又能同时检索。工程上我通过 hybrid retrieval、RRF、metadata filter、引用约束和权限过滤来解决。

### 7.2 为什么用户能搜全局知识库，但不能看别人文档？

推荐回答：

> 我把知识分成 global corpus 和 user-owned documents。检索时会带 owner/global scope filter：用户自己的文档可见，全局知识库可检索，其他用户上传的私有文档不可见。这样既能复用公共 ESG 知识，又不会暴露别人的文件。

追问：

> Pinecone 里怎么隔离？

回答：

> 每个 chunk metadata 里有 owner/document_id/scope 等字段，Pinecone 查询时用 metadata filter。BM25 和 document registry 也要用同样的可访问文档范围，不能只在前端隐藏。

### 7.3 如果 Pinecone 挂了怎么办？

推荐回答：

> 这也是为什么保留 BM25。Pinecone 查询失败或 payload too large 时，系统会降级到更小 topK 重试；仍失败则走 BM25-only。回答质量会下降，但系统不至于完全不可用。

### 7.4 如果 Neo4j 挂了怎么办？

推荐回答：

> Neo4j 是增强上下文，不是主检索唯一来源。Neo4j 不可用时，事实问答仍然可以通过 Pinecone + BM25 返回；只是关系路径、图谱解释和可视化能力降级。

### 7.5 RAG 找不到答案怎么办？

推荐回答：

> 不应该硬答。系统会返回 insufficient context，并把问题进入 HITL 队列。后续人工补充文档或答案，再重新入库。这样“答不出”不是失败，而是发现知识缺口。

### 7.6 你怎么降低幻觉？

推荐回答：

> 我主要从三方面控制：检索层提高 evidence recall，prompt 层要求只基于 sources 回答并内联引用，后处理层检查引用 marker 是否来自候选 sources。对于没有证据的问题，宁可返回资料不足，也不编。

### 7.7 为什么不用 LangChain / LlamaIndex 全套？

推荐回答：

> 这些框架适合快速原型，但项目后期很多逻辑是定制的，比如用户权限过滤、Pinecone payload 降级、RRF 权重、BM25 本地索引、Flash/Deep 路由和 SSE 协议。核心链路自己写更可控，也更容易 debug。必要时可以借鉴框架思想，而不是把主流程完全交给框架。

### 7.8 你们的 router 怎么判断意图？

推荐回答：

> 先用启发式处理明显情况，比如闲聊、短 follow-up、复杂对比词、多跳词、图谱关系词；必要时再用 LLM router 兜底。router 输出的不是最终答案，而是检索策略，比如 no_retrieval、hybrid、multi_query、decomposition、graph_first、layered。

### 7.9 Deep 模式为什么慢？

推荐回答：

> Deep 会做更多工作：可能做查询拆解、layered retrieval、图谱上下文、更多 sources 和更强模型生成。它适合分析型问题，不适合每个简单事实查询。Flash/Deep 的设计就是让用户在成本、速度和推理深度之间选择。

### 7.10 你会怎么继续优化？

推荐回答：

> 我会优先做四件事：第一，补完整离线 eval，包括 Hit@K、MRR、引用准确率和最终答案 judge；第二，上 cross-encoder rerank 但只在 Deep 或 top-N 精排使用；第三，把 SQLite 迁到 PostgreSQL，便于多实例上线；第四，把检索、生成、HITL 的 trace 做成 dashboard，避免靠肉眼看日志。

---

## 8. Java 后端经历怎么和 AI 项目连起来

### 8.1 秒杀超卖和一人一单

推荐回答：

> 秒杀场景的核心是不能让数据库直接扛高并发。我用 Redis 存库存和用户下单状态，用 Lua 把“判断库存、判断是否下过单、扣减库存、记录用户”放在一个原子脚本里执行，避免超卖和一人多单。之后再通过 Kafka 异步生成订单，削峰填谷。

追问：

> 为什么不用 MySQL 乐观锁直接扣？

回答：

> 乐观锁可以防并发冲突，但高并发下大量请求打到 MySQL，会导致数据库成为瓶颈。Redis + Lua 把热点判断前置到内存层，MySQL 只处理已经通过资格校验的订单。

### 8.2 缓存击穿、穿透和一致性

推荐回答：

> 热点 Key 击穿用逻辑过期：缓存不过期删除，而是存逻辑过期时间，过期后一个线程异步重建，其他请求先返回旧值。缓存穿透用缓存空值，避免不存在的数据反复打数据库。缓存一致性上，我采用更新数据库后删除缓存；如果删除失败，走补偿重试和 TTL 兜底。

追问：

> 为什么不是先删缓存再更新数据库？

回答：

> 先删缓存再更新数据库容易出现并发读把旧数据重新写回缓存的问题。更新 DB 后删缓存更稳，但也不是绝对强一致，所以要配合重试和 TTL。

### 8.3 限流

推荐回答：

> 我用 Redis + AOP + 注解做滑动窗口限流。业务方法加 `@RateLimit`，切面拦截后用 Redis ZSet 存时间戳，清理窗口外数据，再用 ZCARD 判断是否超过阈值。维度可以是全局、IP 或用户。

### 8.4 智能客服经历怎么讲

推荐回答：

> 世界生活项目里我接过阿里云百炼平台，用 Redis 做会话记忆，用 Function Calling 查询门店信息和预约。这个经历和 CausalGraph 是连续的：前者是工具调用 + 会话记忆的业务客服，后者是更复杂的 RAG + Agent 工作流。

---

## 9. AI 工具使用怎么讲

推荐回答：

> 我会把 AI 工具当成工程加速器，不当成替代判断的东西。比如用 Codex/Cursor 做代码搜索、重构草稿、测试补全，用 Claude 帮我审 prompt 和解释复杂错误。但核心架构、数据权限、降级逻辑、成本评估必须自己判断。我也会要求 AI 给出可验证的改动，最后通过测试、日志和代码 review 落地。

如果被问“你是不是依赖 AI 写代码”：

> 我依赖 AI 提高速度，但不把它当权威。尤其是 RAG 这种系统，AI 很容易编不存在的接口或夸大效果，所以我会回到代码、日志和评测指标验证。

---

## 10. 面试时可以主动承认的不足

主动承认不足比被追问后硬撑更安全。

可以说：

- 当前 SQLite 适合 MVP，不适合正式多实例生产；生产应迁 PostgreSQL。
- 当前 BM25 是本地索引，数据规模大后应考虑 Elasticsearch/OpenSearch 或托管 sparse retrieval。
- 当前 cross-encoder rerank 不是完整上线能力，后续会优先补。
- 当前 HITL 闭环如果只靠邮件 digest，规模大后要接任务系统和审核流。
- 当前评测如果只是开发阶段固定问题集，还需要自动化 eval 和 dashboard。

不要说：

- 已经完整实现 MCP 协议层，除非你确实实现了。
- 已经训练自研 embedding/reranker，除非你确实训练了。
- 已经大规模线上 A/B，除非你有真实数据。
- 所有指标都是生产环境稳定结论，除非你能展示日志和口径。

---

## 11. 结尾反问

技术面可以问：

> 您团队现在的 AI 应用更偏内部知识库、客服问答，还是偏 Agent 自动化工作流？

> 如果是 RAG 场景，您们现在最头疼的是召回质量、幻觉、权限隔离，还是成本和延迟？

> 对这个岗位来说，您更看重后端工程能力，还是更看重 RAG / Agent 的模型应用能力？

---

## 12. 最短背诵版

如果只背一段，背这一段：

> CausalGraph AI 是一个面向 ESG 报告的 RAG Agent。离线侧把 PDF/Markdown 解析、清洗、chunk、打 metadata，然后写 Pinecone 向量库和 BM25 索引，同时用 Qwen2.5-7B-Instruct + ESG QLoRA adapter 抽取实体关系并同步到 Neo4j；在线侧先用 Redis 取短期上下文，再 query rewrite、router 分发检索策略，简单问题走 Flash hybrid retrieval，复杂问题走 Deep layered / decomposition / graph context，最后用 LLM 生成带引用的 Markdown，并通过 SSE 流式返回。技术上我选 Pinecone 是为了早期托管和 metadata filter，选 bge-m3 是为了中英文和本地成本，选 BM25 是为了 Scope 1/2 这种精确术语，选 RRF 是为了融合不同尺度的检索结果，选 QLoRA 是为了稳定 ESG 结构化抽取，选 Neo4j 是为了多跳关系，选 Redis 是为了低延迟短期记忆。项目里的数字我会按开发阶段评测口径解释，不把它包装成大规模线上 A/B。
