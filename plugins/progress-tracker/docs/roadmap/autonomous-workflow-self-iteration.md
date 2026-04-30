# 自主工作流 + 自我迭代

## 目标

让 siunin-plugins 整体成为一套可被 OpenClaw / Claude Code / Codex 自主运行的完整开发/运营管线，并在两个层级上具备自我迭代能力：

- **项目级**（PROG 驱动）— 每个项目在执行中学习，沉淀自己的标准
- **插件级**（siunin-plugins 主项目驱动）— 插件本身从使用数据中进化，越来越好

## 终局架构：四层管线

```
项目中运行的管线：

┌──────────────────────────────────┐
│     slavingia/skills — 经营层     │
│ /find-community /validate-idea   │
│ /first-customers /pricing /mvp   │
│ /marketing-plan /grow-sustainably│
│ /processize /company-values      │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│     SPM（回填 gstack 方法论）     │
│ /idea /persona /interview        │
│ /compete /roadmap /prd /story    │
│ /metrics /prioritize             │
│ /office-hours /plan-ceo-review   │
│ /plan-design-review              │
│ /plan-devex-review               │
│ /launch /retro                   │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│     PROG — 执行追踪 + 项目级迭代   │
│ /prog-init /prog-plan            │
│ /prog-next → implement → done    │
│ /prog-fix /prog-undo /prog-note  │
│                                  │
│ project_memory（生命周期管理）     │
│ promote 闭环（Generator+Evaluator）│
│ sprint_ledger / audit_log        │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│   gstack（裁剪）— 工程质量层      │
│ /review /cso /qa /browse         │
│ /ship /land-and-deploy /canary   │
│ /benchmark /careful /guard       │
└──────────────────────────────────┘
```

四层分工：
- **经营层** — 找到用户、手工交付、获客、定价、可持续增长
- **产品层** — PRD、优先级、指标、preflight review、launch、retro
- **执行层** — 状态机驱动的实现追踪 + 项目级自我迭代
- **质量层** — 浏览器测试、安全审计、性能监控、部署验证

## 两层迭代架构

```
┌─────────────────────────────────────────────────────┐
│            siunin-plugins 主项目（插件级迭代）         │
│                                                     │
│  迭代对象：插件本身的质量                               │
│  ├─ SPM 的 PRD 模板好不好用？                          │
│  ├─ PROG 的复杂度评分准不准？                          │
│  ├─ gstack QA 检查清单要不要改？                       │
│  └─ slavingia 定价 skill 参数对不对？                  │
│                                                     │
│  数据来源：跨项目的使用反馈 + 人工评估 + A/B 测试        │
│  迭代频率：低频（每次发现 → 手动触发改进 session）       │
│  产出：更好的插件版本                                  │
└──────────┬──────────────────────────────────────────┘
           │ 安装
    ┌──────┴──────┬──────────────┐
    ▼             ▼              ▼
┌ 项目 A ───── ┌ 项目 B ───── ┌ 项目 C ─────┐
│ PROG 驱动    │ PROG 驱动    │ PROG 驱动    │
│ 项目级迭代    │ 项目级迭代    │ 项目级迭代    │
│              │              │              │
│ 「SQLite     │ 「Auth 模块  │ 「API 设计    │
│   WAL 模式」 │   要双审」    │   规范」     │
│              │              │              │
│ 产出：       │ 产出：       │ 产出：       │
│ 项目 A 标准  │ 项目 B 标准  │ 项目 C 标准  │
└──────────────┴──────────────┴──────────────┘
```

- **PROG** 安装在项目中 → 迭代**这个项目的**开发标准
- **siunin-plugins 主项目** → 迭代**插件本身**，让插件越来越好

## 项目级迭代（PROG 驱动）

每个项目中 PROG 作为迭代引擎，参考 Hermes Agent 和 OpenClaw 的思路补齐三个能力：

### 1. project_memory 生命周期

现状：project_memory 只增不减，无生命周期管理。

补齐：
- 每条 memory 加 `confidence`（初始 1.0）、`last_used`、`use_count`
- 每次 `/prog-next` 加载某条 memory 时 `use_count += 1`
- 30 天未使用 → `confidence -= 0.05/天`
- `confidence < 0.3` → 标记 stale，提示退役

### 2. 对抗式 promote（利用现有 ADR-009 基础设施）

现状：promote 完全依赖人手动 prog-note。

补齐：
- **Generator agent**（haiku）扫 sprint_ledger + prog-note → 生成候选标准
- **Evaluator agent**（sonnet，独立上下文）对照 checklist 打分
- 评分 ≥ 7/10 → 提交为人审
- 评分 3-6 → 标记「可选」
- 评分 < 3 → 自动丢弃
- 迭代上限 3 次

### 3. 行为信号反馈

现状：需要用户主动打分，无自动反馈。

补齐：
- PreToolUse/PostToolUse hook 捕获交互行为
- 用户手动改掉 AI 生成的标准 → 负面信号
- 标准被加载后用户直接接受 → 正面信号
- 无需手动评分，系统从行为中学习

## 插件级迭代（siunin-plugins 主项目驱动）

参考 OpenClaw 的 skill engineering 思路，插件本身也需要迭代：

- 从多个项目的 PROG 使用数据中分析：哪些 skill 频繁被手动覆盖？哪些模板产出被高频打回？
- A/B 退役测试：禁用某个 SPM skill → eval — 如果通过率没下降，退役
- 迭代频率低得多（不需要实时），每次手动触发改进 session

具体机制待设计（Phase 5+）。

## 执行阶段

```
Phase 1 — 回填 SPM 产品层
  [x] office-hours（已完成）
  [ ] plan-ceo-review
  [ ] plan-design-review
  [ ] plan-devex-review

Phase 2 — PROG 项目级迭代基础
  [ ] project_memory 加 lifecycle 字段（confidence / last_used / use_count）
  [ ] confidence 衰减逻辑
  [ ] stale 检测 + 退役提示

Phase 3 — PROG 对抗式 promote
  [ ] Generator agent（haiku 候选生成）
  [ ] Evaluator agent（sonnet 独立打分 + checklist）
  [ ] 阈值自动决策（≥7 提交 / 3-6 可选 / <3 丢弃）

Phase 4 — 工程质量层集成
  [ ] evaluator gate 接 gstack /review + /cso
  [ ] /prog-done 后接 gstack /qa + /benchmark
  [ ] git-auto → gstack /ship + /land-and-deploy

Phase 5 — 全自动闭环
  [ ] 行为信号反馈替代手动评分（项目级）
  [ ] agent team + 并行开发整合
  [ ] OpenClaw/CC/Codex 运行时适配
  [ ] siunin-plugins 插件级迭代机制设计
```

## UI/UX 设计层（待定）

要在自主管线中产出 8/10 以上界面，三个方案在评估中：

| 方案 | 思路 | 成熟度 |
|------|------|--------|
| 设计系统锁定 | 约束在 shadcn/ui + Radix → 下限 7 分 | 已有实践（v0） |
| 参考库 + 模仿 | 建立顶级产品截图库，AI 模仿风格 | gstack /design-shotgun |
| 可量化指标 | 间距/对比度/响应式/Fitts' Law 自动评分 | 可落地，但感知层不可测 |

核心矛盾：AI 评审 AI 的 UI = 不可靠。感知层（「好看」「专业」）仍然需要人做最终选择。

待探索方向：gstack 的 /design-shotgun + taste memory 机制。

## 影响范围

- **SPM**: 4 个 skill 回填（office-hours ✓ / ceo-review / design-review / devex-review）
- **PROG**: `project_memory.py` 生命周期字段、`feature-complete/SKILL.md` promote 步骤
- **PROG**: 新增 Generator/Evaluator subagent prompt（评估候选标准）
- **PROG**: hook 可能新增 PreToolUse/PostToolUse（Phase 5）
- **gstack**: 裁剪安装，保留 `/qa` `/cso` `/ship` `/land-and-deploy` `/canary` `/benchmark` `/browse`
- **slavingia/skills**: 评估 quality 后决定安装范围
- **siunin-plugins 主项目**：新增插件级迭代机制（Phase 5+）

## 参考项目

| 项目 | 仓库 | 参考什么 |
|------|------|----------|
| **gstack** | <https://github.com/garrytan/gstack> | 规划前审方法论（→ 回填 SPM）、设计管线（/design-shotgun /design-html）、工程质量层（/qa /cso /ship /benchmark /canary） |
| **slavingia/skills** | <https://github.com/slavingia/skills> | 经营层方法论（获客/定价/营销/可持续增长）、processize 手工先于代码 |
| **Trellis** | <https://github.com/mindfold-ai/Trellis> | 上下文管理三层模型（spec/tasks/workspace）、promote 提升循环原始概念 |
| **Hermes Agent** | <https://github.com/NousResearch/hermes-agent> | 自我迭代五大组件（skill 自动创建、用中自优、自我提醒记忆、FTS5 跨会话搜索、Honcho 用户建模） |
| **OpenClaw** | <https://github.com/openclaw/openclaw> | 对抗式 Generator/Evaluator、1-10 量化反馈闭环、置信度衰减、PreToolUse/PostToolUse 观察钩子、33 项结构化评审清单、A/B 退役测试 |

## 待决策

- [ ] Phase 优先级是否需要调整
- [ ] gstack 裁剪安装的具体 skill 清单待确认
- [ ] slavingia/skills 的 skill 质量是否需要逐一评估
- [ ] UI/UX 设计方案选哪个方向
- [ ] 插件级迭代引擎放 siunin-plugins 主项目的什么位置
