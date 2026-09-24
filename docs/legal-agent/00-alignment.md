# CausalGraph → 法务专用 Agent 产品：改造方向对齐（草案 v0.1）

状态：**草案，等待确认**。本文只对齐方向，不改代码。确认后我会按第 5 节的工作包逐个写任务书、指派子代理执行、由我验收。

日期：2026-09-24　分支：`claude/legal-agent-product-redesign-tuujqu`

---

## 0. 一页结论

现在的 CausalGraph 是一个 **ESG 报告问答产品**（README 原话："open-source ESG intelligence application"）。要把它变成法务 agent 产品，问题不在"换个 prompt、换个皮"，而是几条底层范式已经落后于 2026 年的 agent 产品形态：

| # | 现状范式 | 为什么对法务产品不够用 |
|---|---|---|
| P1 | **"agent" 是脚本化固定流程**，不是模型驱动的 tool use | 计划、反思、重规划全是规则代码，模型只在最后写答案；无法根据合同内容自主决定下一步 |
| P2 | **多层正则/关键词路由**（chitchat → intent → hybrid router） | 路由词表围绕 ESG 写，法务问题会被误判；多层路由叠加后行为难以预测 |
| P3 | **引用只到 chunk 级，PDF 页码在解析时就丢了** | 法务引用必须落到"第几页 / 第几条 / 原文引语"，否则律师无法核对 |
| P4 | **没有"案件/项目（matter）"容器，也没有租户隔离** | 法务文件按案件组织，跨案件可见是保密事故；现在是"用户名下所有文档"一锅粥 |
| P5 | **ESG 硬编码**贯穿 prompt、词表、路由、图谱关系类型、评测集、UI 文案 | 全部需要替换 |
| P6 | **"skills / tasks" 只有前端壳子**，后端不存在 | 法务真正需要的 skill 是"审阅 playbook"，要能被 agent 执行 |
| P7 | **单体**：`app.py` 7113 行，`Agent.tsx` 4545 行 | 子代理并行改动会互相冲突；任何重构都先要拆 |
| P8 | **大量离题功能**：招聘 offer 系统、桌面宠物、ESG demo、因果推断页、图谱 SSR、greenwashing API、QLoRA 本地抽取 | 占代码量约三成，维护成本高，且与法务无关 |
| P9 | **前端工具链 CRA（react-scripts 5）已停止维护**，TS 4.9 | 新依赖装不上、构建慢、无人修漏洞 |
| P10 | **索引层对多文档语料是坏的**：本地模式下向量检索与 BM25 只覆盖**最后一份上传的文档** | 法务 matter 天然是多文档；现在的"跨报告比较"在本地模式下其实只搜了一份，其余靠关键词扫描兜底 |

**建议路线：保基础设施，换内核，删离题。**
- 保留：登录/鉴权、上传→去重→清洗→切分→向量化的流水线骨架与混合检索的融合算法、Redis 会话记忆、长期用户记忆的框架、SSE 流式协议、Vercel + Fly 部署链路、设计 token、119 个后端测试 + 46 个前端测试的基线。（向量/BM25 存储层要重写，见 P10。）
- 重写：agent 内核（原生 tool use 循环）、文档与引用模型（页级/条款级）、matter 工作区与权限、法务 playbook 技能层、产出导出、前端工作台。
- 删除：招聘、桌面宠物端点、ESG 抽取/指标/图谱可视化、legacy 目录、离题页面。

---

## 1. 现状诊断（全部基于代码事实）

### 1.1 产品形态

- 后端 FastAPI 单文件 `app.py`（7113 行）+ `rag/`（约 8k 行）+ `graph/`、`ai_service/`、`metric_extraction/` 等。
- 前端 React 18 + CRA + Tailwind 3，路由（`frontend/src/App.tsx:60-72`）：`/`、`/login`、`/esg-demo`、`/causal-inference`、`/desktop`、`/download`、`/agent`（主工作台）、`/admin`、`/admin/recruitment`、`/offer/:token`、`/about`。
- 模型：默认 DeepSeek V4 Pro（OpenAI 兼容传输），Fast 关思考、Deep 开思考；Anthropic/OpenAI 仅作显式回退（`docs/deepseek-v4-upgrade.md`）。
- 向量：bge-m3（本地或 DeepInfra）→ 本地 FAISS 风格存储或 Pinecone；可选 Neo4j 图谱；可选 Redis。
- 账户：JWT + bcrypt + 图形验证码 + 邮箱验证码 + 邀请码；Free/Pro/Max 只是"每日积分"限流（Free 30 分、Pro 300 分，Fast 1 分、Deep 5 分，Max = admin 无限），无计费。
- 桌面端 `desktop/`：Electron 宠物窗口，调 `/rag/ask`、`/documents/upload-async`、`/desktop/screenshot/summarize`、`/desktop/word/*`。
- 测试基线（我本地已跑通）：后端 `pytest tests` **119 passed**（4.8s，全 mock，不花模型额度）；前端 **46 passed**；`npm run build` 成功（主包 gzip 约 250 kB）。

### 1.2 P1：agent 是脚本，不是模型驱动

`rag/agent_runner.py`：
- `_build_plan()`（297-324 行）：按模式**写死**一组工具调用 —— `search_documents`（hybrid 或 layered）→ `get_graph_context` → `summarize_evidence`。没有任何模型参与规划。
- "reflexion"（326-384 行）：规则检查"问题里提到的实体是否在检索结果里出现"，缺了就针对该实体再搜一次。不是模型自我批评。
- 唯一的模型调用在 `_synthesize_answer()`（529-602 行）：把收集到的 chunk 一次性塞进 prompt 生成答案；模型失败就走 `_extractive_fallback_answer()` 拼句子。
- 预算（756-759 行）：Fast 2 轮 / 20s，Deep 5 轮 / 90s。
- trace 里的 `thought / action / observation` 是为 UI 渲染生成的文案（800-822 行），并非模型思考。
- agent 路径**不流式**：runner 在后台线程跑完后，把整段答案作为一个 `token` 事件一次性发出（`rag/agent_runner.py:525`）；用户在此之前只能看到步骤标题。
- 没有取消：前端无 `AbortController`，后端线程无 cancel 钩子；生成期间输入框直接禁用。
- 全仓库 **没有任何地方**使用 `tools=` / `tool_calls` / `tool_use`（`metric_extraction/agent.py:1` 自己注释："placeholder for real LLM tool_use"）。
- 设计文档 `docs/superpowers/specs/2026-05-24-hybrid-agent-evidence-design.md` 承诺的取消、0.65 置信门槛、独立 `query_neo4j`、坏 JSON 重试，均未落地；`query_neo4j` 只是 `get_graph_context` 的别名（`rag/agent_tools.py:28`）。

工具集（`rag/agent_types.py:20`）是 5 个字面量：`search_documents | read_chunks | query_neo4j | get_graph_context | summarize_evidence`，其中 `read_chunks` 只是原样返回入参，`summarize_evidence` 只是截前 3 段各 24 词。

### 1.3 P2：路由层层叠加、面向 ESG

`rag/hybrid_agent_router.py`：先问 DeepSeek 做 JSON 路由，失败回退到正则；正则里 `_ESG_COMPLEX_PATTERN`（47-56 行）用 `esg|sustainability|climate|scope [123]|net zero|…|环境|社会|治理|排放|气候` 判断"复杂问题"。此外还有 `rag/router.py`、`rag/answer_intent.py`、`rag/chitchat.py`、`app.py` 里的 `_route_request_with_deepseek()`（2982 行）和文档范围解析（2519-2960 行，约 450 行启发式）。同一个问题要过 4-5 层判断。这几个路由器都**直接硬编码 DeepSeek 客户端**、不看 `LLM_PROVIDER`（`answer_intent.py:171-184`、`hybrid_agent_router.py:210-224`、`router.py:183-197`、`app.py:2739-2753, 3026-3040`）；一次提问在开始生成之前最多先打 4 次 DeepSeek，再加查询改写、多查询、分解。积分扣费发生在这些调用之后，被限流的请求也已经花了模型调用。

### 1.4 P3：引用定位能力不足

- `document_processing/pdf_parser.py` 与 `pipeline_runtime.py:633-652`：pypdf 逐页抽文本后 `"\n\n".join(pages)`，**页码在这一步丢失**。
- `document_processing/chunker.py`：章节感知切分，chunk 元数据有 `start/end`（字符偏移）、`section`、`categories`，**没有 page**；而且这几个字段在序列化成前端 `RagSource` 时又被丢掉（`rag/rag_pipeline.py:1638-1656` 只输出 `chunk_id, text, document_id, document_title, source, document_group, source_type, domain, retrieval_scope, relevance_score`）。
- `chunk_id` 按文档内编号（`chunk_1`、`chunk_2`…），两份文档的同名 chunk 在前端无法区分，引用链接会失效（`ragUi.ts:162-198` 只在 id 唯一时才链接）。
- 首页文案里的 "p. 42" 式页码引用是虚构的，代码里不存在端到端的页码数据。
- DOCX 只读段落，不读表格与脚注；`.doc` 会被接受但解析失败（`pipeline_runtime.py:658-663`）；扫描件无 OCR。
- **原始上传文件不保留**：spool 文件在入库后即删除（`app.py:6884-6933`），`data/raw/` 只建目录从不写入。没有原件，就做不了阅读器与高亮。
- chunk 的 `start/end` 偏移是相对**清洗后**文本的，而 `document_processing/text_cleaner.py` 会删掉出现 ≥3 次且短于 80 字符的行。对法律文件里重复出现的条款标题、"Confidential" 页眉、定义项是有风险的，也让偏移无法映射回原件。
- prompt 引用契约（`rag/grounded_prompts.py`）：`[chunk_N]`、`[prior_N]`、`[reg_N]`、`[G_N]`；答案后没有"引语是否真的在原文里"的校验。
- 前端有 `pdfjs-dist`、`mammoth` 依赖（用于上传时客户端抽文本），但没有"点击引用 → 跳到 PDF 第 N 页高亮"的阅读器。

### 1.5 P4：无 matter 容器、无租户

- 文档注册表 `document_registry.py` 是一个带文件锁的 JSON 文件；权限规则在 `app.py:4021-4083`：admin 看全部、`global_kb` 全员可检索、其余按 `owner_user_id` 归属。没有组织、没有案件、没有成员关系、没有审计日志（`admin_audit.py` 记录的是上传/删除等运维事件）。
- 会话（Redis `ChatMemoryService`）和文档之间只有"会话选了哪些 document_ids"这层弱关联，且会话只存一个 `selected_document_id`。
- 会话保留策略是消费级的：7 天不活动过期、每会话最多 20 条消息（更早的折叠成 2400 字符的摘要后删除）、列表最多 30 个会话（`configs/settings.py:232-234`、`chat_memory_service.py:194, 220-240, 288-308`）。法务场景需要按 matter 永久留存并可导出。
- 一次提问最多只能限定 3 份文档（`Agent.tsx:1517, 2921-2928`）。
- 长期记忆（`/memory*`）后端存在并**默认注入 prompt**（`app.py:6495-6496`），但前端没有任何管理入口；法务场景下"跨案件记住用户偏好"需要显式可见可关。
- **隔离有明确漏洞（已核实）**：
  - `owner_user_id` 过滤只在"没解析出 document_ids"时才加（`app.py:3297-3298`）；而 Deep 的 priors / regulatory 两层会把 `document_ids` 弹掉、只按 `domain=academic|regulatory` 搜（`rag/retriever.py:183-196`）。结果：一次限定了文档的 Deep 提问，会在**所有用户**的 academic / regulatory 文档里检索；`domain` 还是上传时用户自填的字段。
  - admin 上传的文档自动进 `global_kb`、对所有用户可检索（`app.py:6865-6867`）。
  - Neo4j 图谱实体全局按名字合并，过滤条件里没有 owner；`/graph/causal/*` 三个端点**无需登录**即可遍历整图含证据文本（`app.py:6258-6288`）。
  - 会话内容由客户端 POST 上来（用户消息和助手消息都由前端写入 `/chat/sessions/{id}/messages`），服务端不自行落库，历史可被伪造。
- 长期记忆的类别里有 `emotional_style`、`relationship_pref`，抽取正则含 "my ideal type is…"（`user_memory_service.py:23-34, 365-410`）。这是桌面宠物时期的遗留，法务产品里必须删。

### 1.6 P5：ESG 硬编码清单

`rag/esg_lexicon.py`（路由词表）、`rag/grounded_prompts.py`（"You are an ESG research analyst…"）、`rag/hybrid_agent_router.py`（路由 prompt "routing controller for an ESG report assistant"）、`graph/causal_taxonomy.py`（因果关系类型）、`ai_service/`（ESG 实体/关系抽取 + QLoRA）、`metric_extraction/` + `data/taxonomy/esg_metrics.yaml`、`evals/cases/rag_baseline.yaml`（要求答案含 "ESG"）、`app.py` Word 审阅的 goal/template（`esg_report`、`sustainability_strategy`…）、前端 `Home/About/Agent` 文案、`.env.example` 变量名前缀 `ESG_*`。

### 1.7 P6：skills / tasks 是壳

- 前端 `Agent.tsx:151-180` 四张写死的"skill 卡"（Evidence Planner、Dynamic Replanner、Reflexion Verifier、Graph Context Reader），描述的就是 runner 已有的固定步骤。
- `agent/skillFiles.ts` 只校验文件名后缀和大小，上传后提示 "staged for validation"，**后端 `app.py` 中 "skill" 一词出现 0 次**。
- "tasks" 是 Cmd+K 面板里对聊天会话的重命名。
- `mcp_tools/email_server.py` 是一个独立 MCP 邮件服务，**没有接进 agent**。

### 1.8 P8：离题功能体量

| 功能 | 代码位置 | 规模 |
|---|---|---|
| 招聘 offer（后端） | `recruitment_offers.py`、`app.py:1281-1775`、`tests/test_recruitment_offers.py` | 约 1.1k + 0.5k + 0.9k 行 |
| 招聘 offer（前端） | `pages/Recruitment.tsx`、`pages/OfferView.tsx`、`pages/offer/*`、`pages/recruitment/*` | 约 1.5k 行 |
| 桌面宠物 | `desktop/`、`app.py` `/desktop/*` 三个端点、`pages/DesktopDownload.tsx` | 独立 Electron 包 |
| ESG demo / 因果推断页 | `pages/EsgDemo.tsx`、`pages/CausalInference.tsx` | 约 570 行 |
| 图谱 SSR 与文本图谱 API | `kg_view/`、`app.py` `/kg-view`、`/api/*`、`/api/greenwashing`、`/public/knowledge-graph`（约 4370-6110 行，含缓存/票据逻辑） | 约 1.7k 行 |
| ESG 抽取与指标 | `ai_service/`、`metric_extraction/`、`/extract`、`/pipeline/pdf` | 约 1.5k 行 |
| 遗留目录 | `backend/`（旧 MVP，含 torch/spacy 依赖）、`text-to-kg-esg/`（旧 Flask） | 未被 `app.py` 引用（待后端审计确认） |
| 过期 CI | 根目录 `ci.yml`、`.backend-tests.yml`（不在 `.github/workflows/`，不会运行） | — |

值得**保留并转化**的一块：`/desktop/word/review` 与 `/desktop/word/export`（`app.py:1976-2370`）已经实现了"解析 DOCX 段落 → 检索证据 → 模型给逐段修改建议 → 回写 DOCX 导出"。这是法务**起草/批注**能力的雏形，应迁进新的 drafting 模块而不是随桌面端一起删。

### 1.9 可直接复用的资产

- 认证与账户（注册/登录/验证码/邀请码/管理员白名单）。
- 上传 → 去重（内容哈希）→ 清洗 → 切分 → 向量化 的流水线骨架；异步 ingestion job 与 worker 池（`ingestion_jobs.py`，需改成持久化队列）。
- 混合检索的融合算法（RRF / 加权，`rag/retriever.py:393-517`）、相关性门控、重排、多查询、HyDE、查询改写（均可开关；存储层本身要重写，见 1.12）。
- `mcp_tools/email_tool.py` 的"白名单 + dry-run + 审计"模式，可作为所有有副作用工具的模板。
- `metric_extraction/` 的"taxonomy YAML → JSON 抽取 → 逐字证据校验 → 版本化存储"模式，正好适合条款抽取；内容整体替换。
- SSE 流式端点、断流恢复、速率限制与积分。
- Redis 短期会话、SQLite + 向量的长期用户记忆。
- DeepSeek 熔断/缓存（`rag/deepseek_resilience.py`）。
- 设计 token（`frontend/src/styles/cg-tokens.css`）与组件视觉体系。
- CI（`upgrade-validation.yml`：后端 pytest + 前端 test/build + Playwright 冒烟）与 Fly 部署工作流。

### 1.10 前端现状补充（来自前端审计，已抽查核实）

- `Agent.tsx` 单组件：61 个 `useState`、26 个 `useEffect`、16 个 `useRef`，所有 fetch 内联；主面板靠 `activeTab` 状态切换而非 URL，会话/文档/页签都不能深链，浏览器后退无效。
- API base 在 8 个文件里各算一遍（AuthContext、Login、Agent、Admin、Recruitment、OfferView、CausalInference、EsgDemo），没有共享 client，响应基本按 `any` 解析。
- SSE 契约（`/rag/ask/stream`）：`meta`（按 `stream_stage` 分 `routing / planning / agent_trace / context_ready`，另有无 stage 的 `fallback_to_flash`）、`token {text}`、`done {payload, quota, routing, long_term_memory, reflexion}`、`error {message}`，空闲 15s 发 `: heartbeat`。前端忽略了 `blocks`、`layered_sources`、`reasoning_trace`、`quota`、`fallback_to_flash`、`plan/round`；后端发的计划与轮次结构在 UI 上完全丢失，trace 只显示最近 6/16 条。
- 引用 UI 现状：`[chunk_N]` → 右侧抽屉里 6 行截断的 chunk 文本；**没有文档阅读器**，也没有任何端点返回文档全文或原文件。`pdfjs-dist`、`mammoth`、`recharts`、`web-vitals` 装了但从未 import。
- 死代码：`PredictionAnswer.tsx`（未被引用，且用了不存在的 CSS 类）、根目录 `main.js`（`desktop/src/main.js` 的旧拷贝）、`Agent.tsx` 内多处未读状态。
- 设计系统：`cg-tokens.css` + `index.css` 组件层约 90% 与领域无关，可直接复用；ESG 痕迹只剩 `--cg-domain-e/s/g/ai` 几个 token、选中色和文案。根目录 `CausalGraph Design System/` 文件夹描述的是 5 月的旧"slate glass"风格，与现在的实现**变量同名但值不同**，会误导，应删除或重新生成。缺少：修订插入/删除色、引用高亮色、风险等级色阶、暗色模式。
- 测试：7 个 Jest 文件全是纯函数测试，没有组件测试；CI 里 `npm run build` 用 `CI=false`，ESLint 警告永不阻断；无 lint/typecheck 脚本。Playwright 冒烟依赖 `.research-model`、`.research-starters` 两个类名（重构时需同步改冒烟脚本）。
- 可删体量：约 5,650 / 13,700 行（招聘约 3,775 行含 1,041 行 CSS；图谱与因果推断约 1,300 行；demo/下载页等）。

### 1.11 必须尽快修的安全与契约问题（与方向无关，已亲自核实）

| 问题 | 位置 | 风险 |
|---|---|---|
| `/documents/rebuild-graph` 接受客户端传入的 `chunks_path / extractions_path / graph_path`，直接按该路径读 JSONL、并把生成的图 **写到该路径**；仅要求登录，不校验 `id` 归属，也不限制路径在数据目录内 | `app.py:3525-3536, 7104-7113`；`pipeline_runtime.py:570-600` | 任意已登录用户可读服务器任意 JSONL、**覆盖任意可写路径**，并把内容同步进 Neo4j |
| `GET /documents`、`GET /documents/{id}` 把服务器文件系统路径（`processed_text_path`、`chunks_path`、`graph_path`、`vector_store_path`…）原样返回给浏览器 | `pipeline_runtime.py:317-336` | 泄露部署布局，为上一条提供现成参数 |
| 权限判断全在客户端（`isAuthenticated = !!token`），服务端虽有二次校验，但 admin 可见全部文档内容 | `AuthContext.tsx:122`；`app.py:4038-4062` | 法务场景不可接受，需 matter 级成员制 |
| `/pipeline/pdf` 让任意已登录用户传 `pdf_path` 让服务器读任意文件；`name` 直接拼进输出路径，可路径穿越 | `app.py:6813-6822`；`scripts/run_pdf_pipeline.py:30-34` | 任意文件读、写到数据目录外 |
| `/extract` **无鉴权**，直接代理到 DeepSeek 抽取 | `app.py:6291-6305` | 匿名消耗模型额度 |
| `/graph/causal/backward\|forward\|path` **无鉴权** | `app.py:6258-6288` | 匿名读取全图与证据片段 |
| Deep 模式 priors / regulatory 层丢弃 owner 过滤（见 1.5） | `app.py:3297-3298`；`rag/retriever.py:183-196` | 跨用户检索 |
| 反馈库路径硬编码为 `backend/causalgraph.db`，`CAUSALGRAPH_DB_PATH` 从未被读取 | `app.py:69` | Fly 每次部署反馈数据丢失 |
| 登录不做邮箱小写化、无登录限速；JWT 24h 不可吊销 | `app.py:1132-1140, 541-556` | 大小写不同即登录失败；暴力破解无阻断 |

建议：前五条不等方向对齐，**立即**修：`rebuild-graph` 改为服务端按 `id` 取路径并校验归属；删除 `/pipeline/pdf` 与 `/extract`；`/graph/causal/*` 加鉴权（或随图谱一起下线）；Deep 各检索层强制保留 owner 过滤；文档 API 去掉路径字段。这是一组独立小改动，我会先出补丁请你过目。

### 1.12 后端现状补充（来自后端审计，已抽查核实）

- **P10 索引层**：`rag/vector_store.py` 每次入库都把 "active manifest" 指向最新文档的存储（143-170 行），`load_vector_store(None)` 只加载这一份（44-60 行）；`rag/bm25_index.py` 同样只加载 active store 的 `bm25.pkl`（57-65 行）。本地模式下更早的文档只能靠 chunk JSONL 的关键词扫描兜底（`rag/retriever.py:313-361`）；Pinecone 模式下向量是全局的、BM25 仍只有最后一份，所谓 hybrid 实际是"全局向量 + 单文档 BM25"。
- Deep 的 primary 层先按 `domain="esg_report"` 过滤再回退（`rag/retriever.py:156-181`）。
- 演示特判：`rag/retriever.py:370-373`、`app.py:2396-2397` 有 "American Airlines" 硬编码；`rag/rag_pipeline.py:187-217` 有写死的"饮料公司 ESG 打分"兜底文案。
- 异步入库队列在进程内存里（`ingestion_jobs.py:24-26`），重启即丢、只能单进程；上传无大小限制。
- 入库必须先跑完每个 chunk 的 ESG 实体/关系抽取（DeepSeek 调用）才能被检索。法务场景应先可问答、结构化抽取异步进行。
- `backend/` 未被 `app.py` import（只剩两个数据库路径字符串指向它）；`text-to-kg-esg/` 是个 import 了不存在模块的坏 Flask 应用，只被借用模板与静态文件（`app.py:985-987, 1055-1056`）。
- `rag/prediction.py` 无人引用；三种 OpenAI 客户端写法并存，且保留着 `openai.ChatCompletion` 旧分支。
- 评测：`evals/cases/rag_baseline.yaml` 只有 8 条关键词断言；`metric_tools.yaml` 引用不存在的 `evals.runner`；没有引用准确性 / 忠实度评测。119 个后端测试里有 31 个在测招聘。

---

## 2. 目标产品定义（需要你确认，见第 6 节）

### 2.1 一句话

> 面向法务团队的 **文件审阅 agent**：把一个案件（matter）的合同/文件放进来，agent 能按 playbook 逐条审阅、回答问题、给出**可定位到页与条款的引用**，并产出审阅表、备忘录和批注版文档。

### 2.2 V1 覆盖的用户旅程

1. 创建 matter（案件/项目），邀请成员。
2. 上传合同/附件（PDF / DOCX / 文本；扫描件 OCR 放 V2）。
3. 提问：单文件或跨文件问答，每条结论带 `[文件名 · 第 N 页]` 引用，点击即在阅读器高亮原文。
4. 审阅：选一个 playbook（如 NDA / 采购合同 / 租赁），agent 逐条款抽取、对照立场、标风险、给修改建议；多文件批量审阅生成对比表。
5. 产出：审阅表（XLSX/CSV）、审阅备忘录（DOCX）、带批注/建议改法的合同（DOCX）。
6. 全程可追溯：agent 每一步工具调用、每条引用、每次导出都进 matter 的审计日志。

### 2.3 V1 明确不做

- 外部法条/判例检索（没有语料与授权；接口预留）。
- 电子签、案件管理（日程、计费）。
- 扫描件 OCR、表格结构化抽取（V2）。
- 桌面端。
- 知识图谱可视化（保留检索侧的图上下文工具，默认关闭）。

---

## 3. 目标架构：六个新范式

### A. 模型驱动的 agent 循环（原生 tool use）

```
用户消息 + matter 上下文 + playbook
   → LLM(system, messages, tools)   ← 模型自己决定调哪个工具
   → harness 执行工具（matter 边界鉴权、超时、审计）
   → tool_result 回填 → 继续，直到 end_turn / 预算耗尽 / 用户取消
   → 答案后处理：引用校验（cite check）、免责、结构化 artifact
```

- Provider 抽象：`core/llm/anthropic.py`（Messages API `tool_use`）与 `core/llm/openai_compat.py`（`tools`/`tool_calls`；DeepSeek、OpenAI 走这条）。统一成 `stream_turn(messages, tools) -> events`。
- 预算以 **工具调用次数 + token + 秒** 三维控制，替代现在的"轮数"。
- 事件协议 v2（SSE）：`session`、`text_delta`、`tool_call`、`tool_result`、`citation`、`artifact`、`usage`、`done`、`error`、`cancelled`。
- 可取消：前端 `AbortController`，后端 cancel token 传进循环与工具。
- 长任务（批量审阅）走异步 job（复用 `ingestion_jobs.py` 的 worker 模式），前端订阅进度。
- 路由收敛为**一层**：小模型/规则只判断"闲聊 vs 需要工具"，其余交给主模型的 tool 选择。

### B. 文档是一等公民，引用可定位

- 解析：PDF 用 PyMuPDF 或 pdfplumber 得到 `page → blocks(text, bbox)`；DOCX 用 python-docx 得到 `paragraph index + 编号（条款号）+ 样式`。统一为 `ParsedDocument{pages[], blocks[]}`。
- chunk 元数据新增：`page_start/page_end`、`char_start/char_end`、`block_ids`、`section_path`、`clause_no`。
- 引用对象：`Citation{document_id, page, quote, char_start, char_end, bbox?}`。模型输出用结构化标记，后端**校验 quote 确实存在于该页原文**，校验失败的引用降级标黄。
- 前端阅读器：PDF（pdfjs 已在依赖）与 DOCX（mammoth 已在依赖）渲染 + 引用高亮跳转。
- 旧索引兼容：缺 page 字段的 chunk 仍可检索，引用退化为"文件级"。

### C. Matter 工作区与租户边界

```
Organization ─┬─ User(role: owner/admin/member)
              └─ Matter ─┬─ MatterMember
                         ├─ Document（绑定 matter；向量 namespace 按 org/matter）
                         ├─ Conversation（替代裸 chat session）
                         ├─ ReviewJob（playbook × 文档集 → 审阅结果）
                         ├─ Artifact（导出物）
                         └─ AuditEvent
```

- 所有检索/读取工具**强制**带 `matter_id` 过滤；跨 matter 不可见；admin 也需是成员才可见内容（可保留"平台管理"看元数据不看内容）。
- 存储沿用 SQLite（Fly volume），但用显式 schema + 迁移脚本，字段设计对 Postgres 友好。
- 现有文档迁入每位用户的"默认 matter"。

### D. 真正的 skills：审阅 playbook

- 文件格式：`SKILL.md`（说明、适用场景）+ `playbook.yaml`：
  - 适用合同类型；条款清单（clause taxonomy）；每条的检查问题；立场（首选 / 可接受 / 不可接受）；风险分级规则；输出模板。
- 后端加载、校验（JSON Schema）、版本化；用户可上传（复用现有 skill 上传 UI，但真正落库）。
- agent 通过工具 `list_playbooks`、`extract_clauses(playbook, document)`、`assess_clause(...)` 执行。
- 内置 3 个起步 playbook：**保密协议（NDA）**、**采购/服务合同**、**租赁合同**，中英双语。

### E. 产出（artifact）而非只聊天

- 审阅表：每条款 → 原文引用 / 发现 / 风险等级 / 建议改法 → XLSX/CSV。
- 审阅备忘录 → DOCX（模板化：背景、关键发现、风险矩阵、建议）。
- 批注/修订版合同 → DOCX（先做"评论 + 建议文本"，tracked changes 视 python-docx 能力评估）。
- 迁移现有 `/desktop/word/*` 的段落级改写逻辑到 `legal/drafting.py`。

### F. 工程结构与护栏

后端目标目录：

```
api/            routers: auth, admin, matters, documents, conversations, agent, reviews, exports, memory
core/           agent_loop.py, events.py, budget.py, llm/{anthropic,openai_compat}.py, tools/registry.py
ingest/         parsers (pdf, docx, text), chunker, embeddings, stores
legal/          playbooks/, clause_taxonomy.py, review.py, drafting.py, prompts.py, citations.py
platform/       auth, tenancy, audit, rate_limit, memory
evals/legal/    样例合同 + 黄金问题 + 指标脚本
```

前端目标：Vite + React 18 + TypeScript 5 + React Router + TanStack Query；页面 `Matters`、`MatterWorkspace`（文档列表 / 对话与审阅 / 阅读器）、`Playbooks`、`Admin`；`Agent.tsx` 拆成组件与 hooks。

护栏：答案默认附"非法律意见"声明；引用校验；敏感字段不进日志；模型供应商可按 org 配置（含"仅私有模型"选项，预留）。

评测：`evals/legal/` 至少 3 份公开合同样本、20+ 黄金问题与条款标注；指标：引用命中率（quote 在正确页上）、条款召回、正确拒答率、幻觉率。CI 只跑 mock；真实模型评测用脚本手动跑。

---

## 4. 需要决策的问题（请逐条回复编号即可）

| # | 问题 | 我的建议默认值 |
|---|---|---|
| D1 | 目标用户是**企业法务（in-house）**还是**律所**？主要司法辖区（中国 / 澳大利亚 / 法域中立）？界面与产出语言？ | 企业法务优先；V1 法域中立（只处理用户自带文件，不做法条库）；中英双语，UI 默认中文 |
| D2 | V1 切入场景 | **合同审阅**（问答 + playbook 审阅 + 批量对比表 + 备忘录/批注导出）。诉讼证据整理、尽调放 V2 |
| D3 | 模型供应商 | provider 层同时支持 Anthropic 与 OpenAI 兼容（DeepSeek）；**默认用哪个由你定**。硬要求：原生 tool use。DeepSeek V4 Pro 在思考模式下的 function calling 需要实测（文档站被本环境网络策略拦截，我没法核实） |
| D4 | 重构深度 | 保留 FastAPI + React + Vercel/Fly；后端拆模块、前端迁 Vite 并拆组件；**不做全新 greenfield** |
| D5 | 离题功能如何处理（招聘 offer、桌面宠物、ESG demo、图谱 SSR、指标抽取、legacy 目录） | **直接删除**（历史在 git 里）。若你想保留招聘功能，建议独立成分支/仓库 |
| D6 | 知识图谱 / Neo4j 去留 | V1 **默认关闭**，保留 `graph_context` 作为可选工具；不再新增投入。V2 再评估"法务实体图"（当事人/义务/定义/交叉引用） |
| D7 | 账户与合规 | V1 保留现有登录 + 积分限流，叠加 org/matter 层；**请明确：客户文件是否允许发往第三方模型 API**（决定是否要私有化模型选项）；桌面端冻结 |
| D8 | 1.11 节的安全问题是否**现在就修**（独立小补丁，不等其余方向） | 是。修完先给你看 diff 再推 |

---

## 5. 分阶段工作包（WP）与验收标准

原则：每个 WP 一个子代理、独立 worktree、有可自动执行的验收命令；我只写任务书、审 diff、跑验收、合并推送。Phase 内 WP 尽量并行，Phase 之间有依赖。

### Phase 0 · 清场与骨架（可 4 路并行）

| WP | 内容 | 验收 |
|---|---|---|
| 0.0 安全热修（见 D8） | `rebuild-graph` 改为服务端按 `id` 取路径并校验归属；删除 `/pipeline/pdf`、`/extract`；`/graph/causal/*` 加鉴权；Deep priors/regulatory 层强制保留 owner 过滤；文档 API 不再返回文件路径；前端只传 `id` | 新增越权 / 路径注入 / 跨租户检索的回归测试；`pytest` 全绿；前端 build 通过 |
| 0.1 后端清场 | 删招聘（`recruitment_offers.py`、相关端点与测试）、`/desktop/screenshot`、图谱 SSR 与 `/api/*` 文本图谱端点、greenwashing、`metric_extraction/`、`ai_service/` 本地 QLoRA 路径、`/extract`、`/pipeline/pdf`、`backend/`、`text-to-kg-esg/`、根目录过期 CI 与 `main.js`；Word 审阅逻辑先移到 `legal/drafting_legacy.py` 保留 | `pytest tests` 全绿；`python -c "import app"` 成功；`grep -ri recruitment\|greenwashing` 无残留；`requirements.txt` 去掉无用依赖；README 更新 |
| 0.2 后端拆分 | `app.py` → `api/` routers + `platform/`；行为零变化；顺手把 `RagSource` 序列化补上 `start/end/section`（为 Phase 1 铺路） | 拆分前后 `openapi.json` 路径集合一致（脚本比对）；`app.py` < 400 行；测试全绿 |
| 0.3 前端清场与拆分 | 删 Recruitment/OfferView/EsgDemo/CausalInference/DesktopDownload/About/KnowledgeGraphView/PredictionAnswer 与路由，删根目录 `CausalGraph Design System/`；`Agent.tsx` 拆成 ≥ 8 个文件并改为 URL 路由；统一 API client（typed）；迁移到 Vite（TS 5）；保留 `.research-model`/`.research-starters` 或同步改冒烟脚本 | `tsc --noEmit` 无错；`npm test` 全绿；`npm run build` 成功；Playwright 冒烟通过；路由只剩 `/`、`/login`、`/app/*`、`/admin` |
| 0.4 CI 与工具链 | 合并成一个 `ci.yml`（所有 PR 触发）：ruff + pytest + tsc + vitest/jest + build + Playwright 冒烟；预提交格式化 | workflow YAML 校验通过；本地能用同样命令复现 |

### Phase 1 · 文档与引用模型（依赖 0.1/0.2）

| WP | 内容 | 验收 |
|---|---|---|
| 1.1 页级解析器 | `ingest/parsers/`：PDF（PyMuPDF/pdfplumber）、DOCX（段落 + 编号 + 表格）、TXT；**保留原始文件**；`ParsedDocument`；chunk 携带 page/char/section/clause，偏移相对原文而非清洗文本；清洗规则改为保守（不删重复行） | 3 个样本文件的单测：每个 chunk 的 page 范围与原文一致；原件可按 document_id 取回；旧 chunk 无 page 时降级不报错 |
| 1.2 引用模型与校验 | `legal/citations.py`：`Citation` 结构、全局唯一的 chunk/引用 id、模型输出标记解析、quote 在页内存在性校验、前端友好序列化 | 单测覆盖命中 / 未命中 / 跨页 / 引语被改写 / 两份文档同名 chunk |
| 1.3 Matter 与租户 | schema + 迁移；`/matters` CRUD 与成员；上传绑定 matter；检索 filter 强制 matter；审计事件表；服务端自行落库会话消息；现有文档迁入默认 matter | 越权访问 403 的测试；迁移脚本幂等；OpenAPI 有 matters 分组 |
| 1.4 索引层重写（P10） | 多文档向量 + BM25 索引，按 org/matter 分 namespace，本地与 Pinecone 同一接口；去掉 active manifest；入库先可检索、结构化抽取异步 | 3 份文档入库后三份都能被向量与 BM25 命中；跨 matter 查询 0 命中；老数据迁移脚本 |

### Phase 2 · Agent 内核（依赖 1.x）

| WP | 内容 | 验收 |
|---|---|---|
| 2.1 Provider 抽象 | `core/llm/`：Anthropic + OpenAI 兼容两个 adapter，统一流式事件与 tool 往返；DeepSeek thinking 模式下 tool 调用实测 | mock 单测两条路径；带真 key 的冒烟脚本（手动） |
| 2.2 Agent 循环 v2 | 预算三维、取消、并行工具、审计、事件协议 v2、替换 `/rag/ask/stream` 为 `/agent/turn` | 单测：预算耗尽给部分答案、取消即停、工具异常不崩、最终答案含引用 |
| 2.3 工具集 v1 | `search_matter`、`read_span`、`list_matter_documents`、`get_document_outline`、`extract_clauses`、`compare_documents`、`cite_check`；每个带 JSON Schema 与 matter 鉴权 | 每个工具单测 + schema 校验；越权调用被拒 |
| 2.4 法务角色与 prompt | 中英 system prompt、引用格式、拒答与免责规则、语言跟随用户 | prompt 快照测试；`evals/legal` 冒烟集通过 |

### Phase 3 · 法务技能与产出（依赖 2.x）

| WP | 内容 | 验收 |
|---|---|---|
| 3.1 Playbook 格式与加载 | `legal/playbooks/`：schema、加载器、版本、上传落库；内置 NDA / 采购 / 租赁 | schema 校验单测；错误 playbook 有明确报错 |
| 3.2 批量审阅 job | matter 内多文档 × playbook → 审阅结果；异步 job 状态机；进度事件 | job 状态机单测；结果每条带引用 |
| 3.3 导出 | XLSX 审阅表、DOCX 备忘录、DOCX 批注版（迁移 word review 逻辑） | 生成文件能被 openpyxl / python-docx 重新读取且字段齐全；产出记入 matter |

### Phase 4 · 前端工作台（4.1 可与 Phase 2 并行）

| WP | 内容 | 验收 |
|---|---|---|
| 4.1 Matter 页 | 列表 / 新建 / 成员 / 文档上传 | 组件测试；Playwright 冒烟 |
| 4.2 工作台 | 左：文档；中：对话与审阅流（事件 v2 渲染，工具调用可折叠）；右：阅读器 + 引用高亮 | Playwright：提问 → 点引用 → 阅读器跳到对应页并高亮 |
| 4.3 审阅与导出 UI | 选 playbook → 运行 → 审阅表视图 → 导出 | Playwright：跑完一次审阅并下载文件 |

### Phase 5 · 评测与发布

| WP | 内容 | 验收 |
|---|---|---|
| 5.1 法务评测集 | 3+ 公开合同、20+ 黄金问题与条款标注、指标脚本 | 引用命中率 ≥ 90%（阈值可议）；报告可复现 |
| 5.2 部署与文档 | `.env.example`、`fly.toml`、README 重写、迁移说明、回滚说明 | CI 绿；staging 手工冒烟清单通过 |

### 执行与验收方式

1. 我为每个 WP 写任务书（目标、边界、输入文件、禁止事项、验收命令），放在 `docs/legal-agent/wp/`。
2. 子代理在独立 worktree 完成 → 我跑验收命令、读 diff、对照标准 → 不达标打回重做 → 达标合并到本分支并推送。
3. 每个 Phase 结束给你一次汇报（改了什么、验收结果、下一步）；Phase 0 结束后先请你看一眼再进 Phase 1。

---

## 6. 你现在要做的事

回复 D1–D7 的选择（默认值可直接说"按建议"）。收到后我立即出 Phase 0 的四份任务书并开工。
