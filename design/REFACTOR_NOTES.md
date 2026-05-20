# MiniMax 风格 UI 重构 — 进度说明

> 本次重构按 `design/DESIGN.md` 的 MiniMax 设计系统对前端做了基础层 + 关键品牌门面页的改造。Agent / Admin 等深业务页是大文件，**没有完全重写结构**，但会自动继承新的设计 token。

---

## ✅ 已完成（核心基础 + 品牌门面）

| 文件 | 改动 | 说明 |
|---|---|---|
| `frontend/tailwind.config.js` | **重写** | 新增 MiniMax 设计 token：DM Sans、`text-hero/display-lg/heading-lg`、brand 色（coral/magenta/blue/purple）、E/S/G/AI domain 色、`rounded-hero` (32px)、section spacing |
| `frontend/src/styles/cg-tokens.css` | **重写** | `--cg-*` 全套 token 切到 MiniMax 配色；`.cg-btn-primary/secondary/tertiary` 改为 pill；新增 `.cg-product-card--coral/magenta/blue/purple/photo`；新增 `.cg-pill-tab/cg-badge-*`；保留 legacy alias（`--cg-domain-environmental` 等）以便深业务页不报错 |
| `frontend/src/index.css` | **重写** | DM Sans 字体加载替换 IBM Plex；`body` 切到纯白 canvas；legacy class（`tech-button`, `app-panel`）映射到新 token，旧页面自动获得新外观 |
| `frontend/src/App.tsx` | 微调 | 背景色 `bg-[#f7f8fa]` → `bg-canvas` |
| `frontend/src/components/Navbar.tsx` | **重写** | 64px 高、白底 + 1px hairline，中间纯文字链接（active 项带 `motion.span` 下划线），右侧 pill 按钮（黑底主 CTA + 白底三级 CTA） |
| `frontend/src/pages/Home.tsx` | **重写** | 80px hero display + dual-CTA → 4-column 产品色卡片矩阵（E coral / S blue / G magenta / AI purple，32px 圆角） → 白底 AI 产品矩阵（24px 圆角）→ 数字 stats strip → coral 促销 CTA |
| `frontend/src/pages/Login.tsx` | **重写** | 移除毛玻璃背景，改为白 canvas + 单列窄表单；输入框 `cg-input` 规范，focus 用 `border-brand-blue-deep`；账号类型切换用 `cg-pill-tab` |
| `frontend/src/pages/About.tsx` | **重写** | 大 hero + 三块 `cg-tile` 原则卡 + 灰底 focus 区 + 三色产品卡（ESG/Graph/RAG）+ 黑底 CTA 区 |

---

## ⏳ 未完全重写（自动继承新 token）

以下文件结构没动，但**所有引用 `--cg-*` 变量 / `app-panel` / `tech-button` / `cg-btn` 的样式会自动切到 MiniMax 风格**。也就是说颜色、字体、按钮形状会立刻变，但布局还是原来的。

| 文件 | 行数 | 状态 |
|---|---|---|
| `frontend/src/pages/Agent.tsx` | 3590 | 自动继承 token（按钮变 pill、字体变 DM Sans、卡片变白底无影） |
| `frontend/src/pages/Admin.tsx` | 531 | 自动继承 token |
| `frontend/src/pages/CausalInference.tsx` | 239 | 自动继承 token |
| `frontend/src/pages/EsgDemo.tsx` | 300 | 自动继承 token |
| `frontend/src/components/GraphVisualizer.tsx` | 373 | domain 颜色已通过 `--cg-domain-*` 切到品牌 coral/blue/magenta/purple |
| `frontend/src/components/KnowledgeGraphView.tsx` | 402 | 同上 |
| `frontend/src/components/PredictionAnswer.tsx` | 251 | 自动继承 token |

---

## 🎨 设计 token 速查（给后续开发用）

### 颜色

```
bg-canvas         → #ffffff  纯白主背景
bg-surface        → #f7f8fa  浅灰节段背景
bg-surface-soft   → #f2f3f5  更浅的灰

text-ink          → #0a0a0a  主文字
text-ink-charcoal → #222222  正文文字
text-ink-steel    → #5f5f5f  次级 / 灰字
text-ink-stone    → #8e8e93  弱化文字

border-hairline   → #e5e7eb  默认边
border-hairline-soft → #eaecf0  更浅的边

bg-brand-coral    → #ff5530  签名色（governance / 主 promo）
bg-brand-blue     → #1456f0  social
bg-brand-magenta  → #ea5ec1  music/governance 变体
bg-brand-purple   → #a855f7  AI / speech

bg-domain-e/s/g/ai → ESG 四领域语义色
```

### 字号

```
text-hero        → 80px / 1.10 / -2px      hero 大字
text-display-lg  → 56px / 1.10 / -1.5px    页面 hero
text-heading-lg  → 40px / 1.20 / -1px      H1
text-heading-md  → 32px / 1.25 / -0.5px    H2
text-heading-sm  → 24px / 1.30             H3
text-card-title  → 20px / 1.40             卡片标题
text-subtitle    → 18px / 1.50             副标题
text-body-md     → 16px / 1.50             正文
text-body-sm     → 14px / 1.50             小字
text-caption     → 13px / 1.70             说明
text-micro       → 12px / 1.50             微标签
```

### 圆角

```
rounded-md       →  8px   输入框、二级按钮、search pill
rounded-lg       → 12px   文档卡
rounded-xl       → 16px   标准白卡
rounded-3xl      → 24px   AI 产品 tile
rounded-hero     → 32px   ⭐ 鲜艳产品卡专属
rounded-full     → ∞      所有按钮、所有 pill tab、所有 badge
```

### 按钮（class）

```
.cg-btn-primary     黑色 pill 主 CTA（最常用）
.cg-btn-secondary   黑边透明 pill（次 CTA）
.cg-btn-tertiary    白底灰边 pill（三级 CTA、退出登录）
.cg-btn-link        无边纯文字链接式按钮
.cg-btn-icon        36×36 圆形 icon 按钮
```

### 卡片

```
.cg-panel              16px 圆角 白底 + hairline 边     标准文档卡
.cg-tile               24px 圆角 白底 + hairline 边     AI 产品 tile
.cg-product-card       32px 圆角 + 品牌色背景           品牌产品卡
  --coral / --magenta / --blue / --purple / --photo
```

### 徽章

```
.cg-badge-success   浅绿 + 深绿字
.cg-badge-new       coral + 白字（"NEW"）
.cg-badge-beta      浅蓝 + 深蓝字（"BETA"）
.cg-badge-code      浅蓝 + 深蓝字 + 6px 圆角（inline code）
```

---

## 🚧 后续工作建议（按优先级）

### P0 — 验证现状

```bash
cd frontend
npm install      # 确认依赖
npm start        # 跑起来看 Home / Login / About / Navbar
```

如果有 lint / typecheck 问题，主要会出现在用了已废弃 token 的地方（应该都已用 alias 兜住，不应该出错）。

### P1 — 深业务页重构（按价值排序）

1. **CausalInference.tsx** (239 行) — 用户最容易看到的"产品"页。重构成：
   - Hero 区用 80px display
   - 知识图谱视觉化部分嵌在 `cg-product-card--photo` 风格的黑底卡里
   - 控件用 `cg-pill-tab` / `cg-btn-tertiary`

2. **EsgDemo.tsx** (300 行) — 类似 CausalInference。

3. **Admin.tsx** (531 行) — 表格用新的 `data-table` 规范：
   - header 灰底 + caption-bold 字
   - row 白底 + body-sm + hairline-soft 分隔
   - 按钮全切 pill

4. **Agent.tsx** (3590 行) — 这是工作区，是真正的产品深页。建议拆分成多个子组件后再分步重构：
   - 顶部 query 输入区 → `cg-search-pill` 风格
   - 答案卡片 → `cg-panel`
   - sources 列表 → `data-table-row`
   - 图谱面板 → `cg-product-card--photo`
   - prediction 答案 → 三段式 Evidence/Reasoning/Prediction，每段用 `cg-tile`

### P2 — 共用组件抽取

目前所有按钮/卡片都靠 CSS class，没抽 React 组件。如果项目要长期维护，建议建 `src/components/ui/`：

```
src/components/ui/
├── Button.tsx          variant: primary | secondary | tertiary | link | icon
├── Card.tsx            variant: panel | tile | product (with color prop)
├── Badge.tsx           variant: success | new | beta | code
├── PillTab.tsx
└── Input.tsx
```

每个组件内部 wrap CSS class，对外提供 TypeScript 类型安全。

### P3 — Promo banner

DESIGN.md 提到 MiniMax 标志性的"黑底促销条"在 nav 之上。当前 App.tsx 没有，可以按需在 `App.tsx` 顶部加：

```tsx
<div className="cg-promo-banner">
  Try the new Prediction mode — Evidence → Reasoning → Prediction
</div>
```

---

## ⚠️ 已知限制

1. **Logo 资产**：`/brand/logo-mark.svg` 是原品牌资产，没换。MiniMax 的 wordmark 不是我们的，所以保留原 logo 是对的。
2. **图表 / 数据可视化**：GraphVisualizer 内部画图的颜色用了 `--cg-domain-*`，已切到品牌色，不需要再改。但如果有内部 hard-code 的 `#xxxxxx`，需要单独排查。
3. **暗色模式**：DESIGN.md 明确说"尚未发布暗色模式 token"。当前实现也只覆盖 light mode。
4. **DM Sans 加载**：通过 Google Fonts CDN 加载。如果项目要求离线 / 自托管，需要把字体文件下载到 `public/fonts/` 并改 `@font-face`。
5. **Animations**：保留了 framer-motion 的入场动画，但没用 MiniMax 那种"层叠交错"的复杂动画。后续可加 staggerChildren。

---

## 验证清单

- [ ] `npm start` 能跑起来不报错
- [ ] Home 页 hero 是 80px 大字（桌面端）
- [ ] Home 页四个产品色卡片是 coral/blue/magenta/purple（不是原来的灰白）
- [ ] Navbar 主 CTA 是黑色 pill，不是圆角矩形
- [ ] Login 页背景是纯白，没有毛玻璃
- [ ] About 页底部三个产品卡是彩色 32px 圆角
- [ ] Agent / Admin 等老页面**按钮自动变成 pill 形**，**字体自动变成 DM Sans**
