# siunin-plugins Roadmap

## 愿景

构建一套完整的 AI-Native 插件生态，让**一个人 + Claude Code** 能运营一家软件公司。

- 每个**插件** = 一个**部门**
- 每个**skill** = 一个**职位/员工**
- 每个**command** = 一个**对外接口/路由**
- AI 承担 **95%** 的执行和分析工作
- 人类承担 **5%**：品味判断、方向选择、最终决策

---

## 版本策略

版本号按**整个公司生态的完整度**定义，不按单个插件走。

| 版本 | 含义 |
|------|------|
| **v0.2** | 地基：产品部 + 幕僚长就位，能写合同、做评审、追踪进度 |
| **v0.3** | CTO 就位：工程架构评审 + ADR + 技术债追踪 |
| **v0.4** | 用户声音回流：feedback → SPM，不再闭门造车 |
| **v0.5** | 公司记忆：跨 session 知识积累，越做越聪明 |
| **v0.6** | 运营大脑：COO + 财务 + 数据管道 |
| **v0.7** | 走向市场：营销 + 社区 + 品牌 + DevRel |
| **v1.0** | 全公司闭环：一人从 idea 到 PMF 到规模化，全流程自动化 |

---

# 零、参考开源项目对照表

三个参考项目，各自贡献不同模块的"原材料"，然后被内化、中文重写、结构压缩。

## 项目总览

| 项目 | GitHub | 类型 | 我们借鉴什么 |
|------|--------|------|-----------|
| **gstack** | `garrytan/gstack` | Claude Code 插件（虚拟工程团队） | Plan Review 四件套的方法论骨架 + autoplan 管道 + Learnings 思路 |
| **Trellis** | `mindfold-ai/Trellis` | 多平台 AI 编码工作流引擎 | 三阶段流程（Plan→Execute→Finish）+ spec 注入 + hook 驱动 + task 生命周期 |
| **slavingia/skills** | `slavingia/skills` | Claude Code 插件（极简创业者） | 商业侧方法论：验证/定价/营销/社区/可持续增长 |

## gstack → siunin-plugins 对照

| gstack 原始模块 | 改善目标 | 放入 siunin-plugins 的位置 | 内化策略 |
|----------------|---------|--------------------------|---------|
| `plan-ceo-review/SKILL.md` | 方法论已内化 ✅ | SPM:`plan-ceo-review` | 保留 4 模式 + premise 挑战；新加五维评审原则 + 影子路径 + Bezos 框架 + 机会点矩阵 + 反谄媚规则 |
| `plan-eng-review/SKILL.md` | **待内化** ← M1 核心 | SPM:`plan-eng-review`（待建） | GStack 原文 ~30K 英文 tokens；中文重写压缩到 ~200 行；评审六维度 + ADR 联动 + 技术债自动提取 |
| `plan-design-review/SKILL.md` | 方法论已内化 ✅ | SPM:`plan-design-review` | 保留 0-10 循环评分 + 7 pass 结构；新加四维加权评分（D×4+P×3+I×2+F×1）+ 6 套框架摘要 + 等级判定 + lane 自动建议 |
| `plan-devex-review/SKILL.md` | 方法论已内化 ✅ | SPM:`plan-devex-review` | 保留 TTHW 基准 + Persona + 8 pass；新加三阶段摩擦检查 + 摩擦分类信号表 + P0/P1/P2 优先级框架 |
| `autoplan/SKILL.md` | **待内化** ← M6 | 编排层:`autoplan`（待建） | GStack 用 auto-decide 6 原则；我们适配中文 + PROG 集成 |
| `office-hours/SKILL.md` | 方法论已内化 ✅ | SPM:`office-hours` | 保留结构化澄清思路；新加"三板斧"+ Pushback Patterns + 产出前自检清单 + 严格的产品-技术边界分离 |
| `plan-tune/` + `question-registry.ts` + `psychographic-signals.ts` | **不内化** | — | 属于 Claude Code 平台层用户偏好，不做成业务插件 |
| Learnings 系统 (`learnings.jsonl` + `gstack-learnings-search`) | **待内化** ← M3 | PROG:`learnings-collector`（待建） | 复用数据模型思路，中文重写，和 PROG 进度系统深度整合 |
| `review/SKILL.md` | **部分内化** | PROG:`code-review`（已有） | GStack review 是 pre-landing diff review；PROG 已有 code-review |
| `ship/SKILL.md` + `land-and-deploy/SKILL.md` | **部分内化** | PROG:`git-auto` + SPM:`launch`（已有） | 发布流程拆分到 git 操作（PROG）和上线策略（SPM）两个插件 |
| `investigate/SKILL.md` | **部分内化** | PROG:`bug-fix`（已有） | 系统化 debug 方法论已融入 bug-fix |
| `qa/SKILL.md` + `qa-only/SKILL.md` | **不内化** | — | QA 工具独立，用户可自行安装 GStack 使用 |
| `design/` (mockup 生成二进制) | **不内化** | — | 设计工具链非 PM/工程核心 |
| `browse/` (headless browser) | **不内化** | — | Browser 自动化非核心需求 |
| `gbrain/` (跨机器同步) | **不内化** | — | M3 Learnings 系统解决跨 session 知识问题，不需要跨机器同步 |

## Trellis → siunin-plugins 对照

| Trellis 原始模块 | 改善目标 | 放入 siunin-plugins 的位置 | 内化策略 |
|-----------------|---------|--------------------------|---------|
| `.trellis/workflow.md` 三阶段流程 | **部分内化** | PROG 整体设计 | Plan→Execute→Finish 范式已体现在 PROG 的 prog-init → implement → prog-done 生命周期中 |
| `trellis-brainstorm/SKILL.md` | **已内化** | SPM:`office-hours` + `idea` + `mvp` | Trellis 的 brainstorming 流程：diverge→converge→PRD，分散到 SPM 的 3 个 skill 中 |
| `.trellis/spec/` spec 注入机制 | **部分内化** | PROG: context injection | PROG 的 session-start hook 已在做类似的事（注入进度状态、git 上下文）|
| hooks: `session-start.py` + `inject-workflow-state.py` | **已内化** | PROG hooks | PROG 已有 session-start + preflight hooks |
| `.trellis/tasks/` task 生命周期 | **已内化** | PROG: `prog-init/done/reset` + breakdown | PROG 的 task 管理 = Trellis task.json + prd.md 的中文版 |
| `trellis-check/SKILL.md` | **已内化** | PROG:`testing-standards` + SPM 子 agent 自审 | 质量验证 = testing-standards + plan review 的 agent 自审循环 |
| `trellis-before-dev/SKILL.md` | **部分内化** | PROG: `prog-next` + context injection | "开发前先读什么"的逻辑在 prog-next 中 |
| `trellis-update-spec/SKILL.md` + `trellis-break-loop/SKILL.md` | **待内化** ← M3 | PROG: learnings 系统 | 学到的教训 → spec 文档 = 我们的 learnings → 自动注入 |
| `trellis-continue` / `trellis-finish-work` | **已内化** | PROG:`progress-recovery` + `prog-done` | 中断恢复 + 完结流程 |
| 多平台支持 (Cursor/OpenCode/Codex/Pi) | **不内化** | — | siunin-plugins 只面向 Claude Code，不跨平台 |
| Monorepo package 管理 | **不内化** | — | 不属于"一人公司"的职责范围 |

## slavingia/skills → siunin-plugins 对照

| slavingia 原始 Skill | 改善目标 | 放入 siunin-plugins 的位置 | 内化策略 |
|---------------------|---------|--------------------------|---------|
| `validate-idea/SKILL.md` | **部分内化** | SPM:`market-validation`（已有）| SPM 已有市场验证 skill |
| `mvp/SKILL.md` | **已内化** ✅ | SPM:`mvp`（已有）| 极简 MVP 思维已融入 |
| `pricing/SKILL.md` | **待内化** ← M4 | COO:`finance-basics`（待建）| 定价策略 → 财务基础的子模块 |
| `marketing-plan/SKILL.md` | **待内化** ← M5 | GTM:`marketing-plan`（待建）| 内容漏斗 + 三层内容策略 |
| `find-community/SKILL.md` | **待内化** ← M5 | GTM:`find-community`（待建）| 社区发现 + 评估框架 |
| `first-customers/SKILL.md` | **待内化** ← M5 | GTM:`first-customers`（待建）| 同心圆模型 + 冷启动模板 |
| `grow-sustainably/SKILL.md` | **待内化** ← M4 | COO:`grow-sustainably`（待建）| 盈利方程 + burn rate + "default alive" |
| `processize/SKILL.md` | **待内化** ← M4 | COO:`processize`（待建）| SOP 标准化 + 自动化评估 |
| `minimalist-review/SKILL.md` | **参考** | SPM:`plan-ceo-review` | 8 条极简原则可用于 CEO review 的补充视角 |
| `company-values/SKILL.md` | **低优** ← M4 | COO:`people-ops`（待建）| 团队扩展到多人时需要。一人公司阶段不重要 |

## 汇总：每个 Milestone 依赖哪些参考项目

| Milestone | 核心交付 | 主要参考 |
|-----------|---------|---------|
| M0 (v0.2) | 产品部 + 幕僚处 | gstack（plan-ceo/design/devex + office-hours）+ Trellis（workflow 三阶段）|
| M1 (v0.3) | CTO Suite | **gstack**（plan-eng-review 方法论 + ADR 思路）|
| M2 (v0.4) | Feedback Loop | 原创为主，参考 Trellis 的 spec 注入机制做反馈→合同映射 |
| M3 (v0.5) | Knowledge Layer | **gstack**（learnings.jsonl 数据模型）+ **Trellis**（trellis-update-spec 思路）|
| M4 (v0.6) | Operations | **slavingia/skills**（processize + grow-sustainably + pricing）|
| M5 (v0.7) | GTM | **slavingia/skills**（marketing-plan + find-community + first-customers）|
| M6 (v1.0) | 全公司就绪 | **gstack**（autoplan + ship pipeline）+ 原创编排层 |

---

# 一、插件/Skill 完整清单

## 1. super-product-manager（产品部 / CPO 办公室）

**插件职责**：定义"做什么"和"为什么"。从模糊想法到可执行的产品合同，
再到被多方评审过的产品计划。不涉及技术实现细节。

### 1.1 0→1 产品定义

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 1 | `office-hours` | **需求澄清顾问** | ✅ v1.0.0 | 用"三板斧"（项目上下文/技术约束/资源边界）追问用户，输出含 Goals/Scope/AC/Risks 四节的**产品合同**。严禁写入任何技术实现路径。粒度控制：每个目标可在一个迭代内独立验证。配备 Pushback Patterns（用户回避时的犀利追问）和产出前自检清单。落盘到 `docs/product-contracts/` |
| 2 | `prd` | **PRD 撰写师** | ✅ 已有 | 生成完整的 Product Requirements Document。输入来自 office-hours 的产品合同 |
| 3  | `mvp` | **MVP 定义顾问** | ✅ 已有 | 从产品合同中切出最小可行版本——"这周末能交付什么？" |
| 4 | `idea` | **Idea 孵化师** | ✅ 已有 | 从一句话想法开始，快速收敛到可进入 office-hours 的清晰产品方向 |

### 1.2 1→100 产品管理

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 5 | `roadmap` | **路线图规划师** | ✅ 已有 | 将多个产品合同编排为时间线，管理优先级和依赖 |
| 6 | `prioritize` | **优先级决策顾问** | ✅ 已有 | 数据驱动的取舍决策——"先做哪个？不做哪个？" |
| 7 | `story` | **用户故事撰写师** | ✅ 已有 | 将产品合同中的 AC 转化为结构化的用户故事 |

### 1.3 用户研究

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 8 | `persona` | **用户画像师** | ✅ 已有 | 构建目标用户画像，定义他们的场景、痛点和期望 |
| 9 | `interview` | **用户访谈主持人** | ✅ 已有 | 设计访谈提纲、分析访谈结果、提取可行动的洞察 |
| 10 | `researcher` | **用户研究专家** | ✅ 已有 | 深入理解用户需求、行为模式和痛点。用于需求挖掘和反馈分析 |

### 1.4 数据分析

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 11 | `analyst` | **数据分析师** | ✅ 已有 | 设计指标体系，解读数据洞察。用于指标设计、A/B 测试、看板设计 |
| 12 | `metrics` | **指标定义顾问** | ✅ 已有 | 定义可追踪的产品指标（北极星指标、健康指标、反指标） |

### 1.5 Plan Review 四件套（产品合同评审管道）

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 13 | `plan-ceo-review` | **CEO 策略顾问** | ✅ v1.0.0 | 从商业合理性审视产品合同。4 种模式（Expansion/Selective/Hold/Reduction）× 五维评审原则（Progressive Disclosure / YAGNI / Decision Records / Flexibility / Pragmatism）。影子路径思维（happy/nil/empty/error）× 单向门/双向门（Bezos 框架）× 机会点评估矩阵。输出 Verdict 三分法：Approved / Approved with Risks / Deferred |
| 14 | `plan-design-review` | **设计总监** | ✅ v1.0.0 | 设计质量评审。四维加权评分（设计决策深度 ×4 + 交互模式熟悉度 ×3 + 集成复杂度 ×2 + 影响面 ×1）。6 套设计框架（Rams 10 原则 / Norman 3 层 / Nielsen 10 启发式 / Krug 法则 / Gestalt 原则 / AI Slop 黑名单）。0-10 循环评分。自动建议 design lane |
| 15 | `plan-devex-review` | **DevEx 专家** | ✅ v1.0.0 | 开发者体验摩擦评审。三阶段摩擦检查（Design/Plan/Execute）× TTHW 基准 × Journey Trace 9 阶段摘要 × DX 第一原则 8 条摘要。摩擦点分类与信号表 + P0/P1/P2 改进优先级框架。自动建议 devex lane |
| 16 | `plan-eng-review` | **CTO / 技术 VP** | ❌ 待建 — M1 | **这是 v0.3 的核心交付**。从技术视角评审产品合同：架构复杂度 / 数据流 / 技术债务风险 / 测试策略 / 性能瓶颈 / 安全边界。输入产品合同，输出工程评审文档 + ADR + 技术债条目。参考 GStack 的 plan-eng-review 重写为中文结构化版本。防惰性 + 子 agent 自审 |

### 1.6 竞争与市场

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 17 | `compete` | **竞品分析师** | ✅ 已有 | 竞品调研、对标分析、差异化定位 |
| 18 | `market-research` | **市场研究员** | ✅ 已有 | 市场规模、趋势分析、机会识别 |
| 19 | `market-validation` | **市场验证顾问** | ✅ 已有 | 验证产品方向是否有真实市场需求 |

### 1.7 上线与增长

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 20 | `launch` | **上线总指挥** | ✅ 已有 | 产品发布全流程策划与执行 |
| 21 | `gtm-planner` | **GTM 策划师** | ✅ 已有 | 产品上市与增长策划，规划发布策略和用户获取 |

### 1.8 支撑角色

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 22 | `dev-translator` | **产品-技术翻译官** | ✅ 已有 | 将业务需求转化为技术任务描述。专门优化给 Claude Code 的任务描述。用于需求→开发任务、与开发沟通、拆解技术任务 |
| 23 | `ux-reviewer` | **UX 评审师** | ✅ 已有 | 用户体验评审，审视产品的可用性和交互体验。用于 UX 评审、可用性分析、交互优化 |
| 24 | `legal-compliance` | **法务合规官** | ✅ 已有 | 法律合规检查（隐私、ToS、GDPR 等） |
| 25 | `stakeholder-comm` | **利益相关者沟通师** | ✅ 已有 | 帮助 PM 与不同利益相关者有效沟通 |

### 1.9 协作与会议

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 26 | `meeting` | **会议主持人** | ✅ 已有 | 结构化会议引导 |
| 27 | `followup` | **会议跟进者** | ✅ 已有 | 会议 follow-up，决议追踪 |
| 28 | `roundtable` | **圆桌讨论引导师** | ✅ 已有 | 多利益相关者圆桌讨论 |
| 29 | `retro` | **复盘引导师** | ✅ 已有 | 迭代回顾和团队复盘 |

### 1.10 战略

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 30 | `strategist` | **产品策略师** | ✅ 已有 | 产品战略规划，定义产品愿景、市场定位和商业模式 |
| 31 | `assign` | **任务分配顾问** | ✅ 已有 | 帮助将产品任务分配给合适的团队成员 |

### 1.11 SPM 内部 Agent（子员工）

| # | Agent 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| A1 | `spec-writer` | **需求撰写专家** | ✅ 已有 | 生成清晰、可执行的产品需求文档。用于 PRD 撰写、用户故事编写、验收标准定义 |
| A2 | `prioritizer` | **优先级分析师** | ✅ 已有 | 数据驱动的优先级决策。用于功能排序、资源分配、取舍决策 |
| A3 | `researcher` | **用户研究员** | ✅ 已有 | 深入理解用户需求、痛点和行为模式 |
| A4 | `analyst` | **数据专家** | ✅ 已有 | 产品数据分析，指标设计，A/B 测试设计 |
| A5 | `strategist` | **战略顾问** | ✅ 已有 | 产品战略规划，商业模式设计，市场分析 |
| A6 | `ux-reviewer` | **UX 审查员** | ✅ 已有 | 用户体验评审，可用性分析和交互优化 |
| A7 | `gtm-planner` | **GTM 策划师** | ✅ 已有 | 产品上市与增长策划 |
| A8 | `dev-translator` | **需求翻译官** | ✅ 已有 | 业务需求→技术任务转化 |

---

## 2. progress-tracker（幕僚处 + 工程营）

**插件职责**：追踪进度、管理工程流程、确保中断可恢复。
让人类和 AI 都知道"做到了哪、下一步是什么、上次聊到了什么"。

### 2.1 进度管理（首席幕僚 / Chief of Staff）

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 32 | `prog` | **首席幕僚** | ✅ 已有 | 查看当前进度状态、下一步行动。prog 系列的主入口 |
| 33 | `prog-log` | **日志记录员** | ✅ 已有 | 记录和查看工作日志 |
| 34 | `prog-next` | **下一步建议师** | ✅ 已有 | 根据当前状态自动建议下一步该做什么 |
| 35 | `prog-init` | **项目初始化师** | ✅ 已有 | 为新项目/新迭代初始化 PROG 追踪结构 |
| 36 | `prog-done` | **完结审核师** | ✅ 已有 | 标记任务完成，触发后续流程（learnings 抽取、ADR 归档等） |
| 37 | `prog-reset` | **重置操作员** | ✅ 已有 | 重置进度状态 |
| 38 | `prog-fix` | **修复操作员** | ✅ 已有 | 修复进度追踪中的异常 |
| 39 | `prog-note` | **笔记追加员** | ✅ 已有 | 向当前进度追加备注 |
| 40 | `prog-undo` | **撤销操作员** | ✅ 已有 | 撤销上一步操作 |
| 41 | `prog-plan` | **计划管理助手** | ✅ 已有 | 管理 planning 阶段的追踪 |
| 42 | `prog-ui` | **UI 启动器** | ✅ 已有 | 启动 PROG 可视化界面 |
| 43 | `help` | **帮助中心** | ✅ 已有 | PROG 使用帮助 |
| 44 | `progress-management` | **进度管家** | ✅ 已有 | 综合进度管理 |
| 45 | `progress-status` | **状态报告员** | ✅ 已有 | 输出详细的进度状态报告 |
| 46 | `progress-recovery` | **中断恢复专家** | ✅ 已有 | **PROG 最重要的能力之一**。session 断开/compaction 后，零信息损耗恢复到中断点。workflow_state + plan_path 保证跨 session 连续性 |
| 47 | `ui-launcher` | **界面启动器** | ✅ 已有 | 启动可视化进度界面 |

### 2.2 工程执行（Tech Lead / 架构师 / 开发者）

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 48 | `architectural-planning` | **架构规划师** | ✅ 已有 | 系统级架构设计规划。决定模块边界、技术选型、数据流 |
| 49 | `feature-breakdown` | **功能拆解师** | ✅ 已有 | 将大功能拆分为可独立交付的小任务。粒度：单任务 15 分钟~2 小时 |
| 50 | `feature-implement` | **功能实现者（标准）** | ✅ 已有 | 按拆解好的任务实现功能。标准复杂度 |
| 51 | `feature-implement-simple` | **功能实现者（简单）** | ✅ 已有 | 简单功能的快速实现 |
| 52 | `feature-implement-complex` | **功能实现者（复杂）** | ✅ 已有 | 复杂功能的分阶段实现 |
| 53 | `feature-complete` | **功能完结审核师** | ✅ 已有 | 功能完成后触发质量门禁和验收 |
| 54 | `bug-fix` | **Bug 修复师** | ✅ 已有 | 结构化 debug：假设驱动 → 证据 → confirm/falsify → fix |
| 55 | `testing-standards` | **测试质量官** | ✅ 已有 | 确保每个交付有对应测试，测试不通过不标记 done |
| 56 | `git-auto` | **Git 自动化操作员** | ✅ 已有 | 自动 commit/PR 管理。checkpoint → ship squash |

### 2.3 待建（v0.3 ~ v0.5）

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 57 | `tech-debt-tracker` | **技术债追踪官** | ❌ M1 | 从 plan-eng-review 自动提取技术债条目。在 prog-log 中暴露 `tech-debt` 类别。支持"用 X% 产能还债"可视化 |
| 58 | `adr-manager` | **ADR 决策记录官** | ❌ M1 | 从 plan-eng-review 产出中自动提取关键决策。落盘 `docs/decisions/ADR-{NNN}-{slug}.md`。追踪"这个决策后来有没有被推翻" |
| 59 | `learnings-collector` | **知识沉淀官** | ❌ M3 | 自动从 prog-done、prog-note、子 agent 审查中抽取 learnings。格式：id / type / key / insight / confidence / source / files / tags。新任务触及相关 tag 时主动注入 |
| 60 | `cross-project-search` | **跨项目知识检索官** | ❌ M3 | 跨项目检索 learnings。用户可控开关（避免客户代码库 cross-contamination） |

---

## 3. ❌ 待建：operations-department（运营部 / COO 办公室）

**插件职责**：确保公司不只是做产品，还能持续运营——流程自动化、
财务健康、数据管道、可持续增长。

### 3.1 流程与自动化（COO）

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 61 | `processize` | **流程标准化师** | ❌ M4 | 将重复性操作标准化→checklist→自动化。一句话："任何做第二次的事都应该有 SOP"。参考 slavingia:processize |
| 62 | `grow-sustainably` | **可持续增长官** | ❌ M4 | 盈利方程 / 成本结构 / burn rate / "default alive or default dead" 检查。每个增长决策评估盈利影响和可逆性。参考 slavingia:grow-sustainably |
| 63 | `finance-basics` | **财务基础官** | ❌ M4 | 收入/支出追踪、定价模型 ROI 评估、跑道估算（"按当前 burn rate 还能撑 X 个月"）。参考 slavingia:pricing + SPM:finance-basics |

### 3.2 数据基础设施

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 64 | `analytics-infra` | **数据管道工程师** | ❌ M4 | 从 SPM:analyst 的指标设计 → 自动生成埋点需求 → 工程师实现。看板（MRR / Churn / TTHW / NPS / DAU）。异常检测："p99 延迟 3x → 触发 investigate" |

### 3.3 人员与合规（扩展）

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 65 | `people-ops` | **人事运营官** | ❌ M4（低优） | 当公司从 1 人扩展到多人时：招聘流程、onboarding、绩效反馈。不在一人公司 MVP 里，但架构上预留 |

---

## 4. ❌ 待建：gtm-department（GTM 部 / CMO 办公室）

**插件职责**：产品做出来后——传播、获客、建立社区、沉淀品牌。

可以并入 SPM，也可以独立成插件。架构决策：**先并入 SPM，规模大了再拆**。

### 4.1 营销与内容

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 66 | `marketing-plan` | **营销策划师** | ❌ M5 | 内容策略 / 漏斗设计 / 投放规划。区分 community vs audience。三层内容（教育/启发/娱乐）。参考 slavingia:marketing-plan |
| 67 | `brand-strategy` | **品牌策略师** | ❌ M5 | 品牌叙事、视觉调性、messaging 一致性。"用户 5 秒内知道你是做什么的吗？" |

### 4.2 社区与销售

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 68 | `find-community` | **社区发现官** | ❌ M5 | 识别用户已经存在的社区。评估标准：是否是真成员、问题痛度、可触达性、niche 大小。参考 slavingia:find-community |
| 69 | `first-customers` | **首批客户获取师** | ❌ M5 | 前 100 个客户策略：同心圆（朋友→社区→陌生人 cold outreach）。参考 slavingia:first-customers |

### 4.3 DevRel（已有基础，需增强）

| # | Skill 名称 | 职位名称 | 状态 | 详细职责 |
|---|-----------|---------|------|---------|
| 70 | `devrel-strategy` | **DevRel 策略师** | ❌ M5 | 基于 plan-devex-review 的发现，策划：onboarding 流程优化、sample app 开发、workshop/教程大纲、开发者社区运营策略 |

---

## 5. 现有辅助插件

### 5.1 note-organizer（笔记助理 / 个人知识库）

| # | Skill 名称 | 职位名称 | 状态 |
|---|-----------|---------|------|
| 71 | `note-enhance` | **笔记增强师** | ✅ |
| 72 | `note-batch` | **笔记批处理师** | ✅ |
| 73 | `note-process` | **笔记流程师** | ✅ |

### 5.2 package-manager（依赖管理员 / 工具链）

| # | Skill 名称 | 职位名称 | 状态 |
|---|-----------|---------|------|
| 74 | `update-global` | **全局依赖更新员** | ✅ |
| 75 | `update-project` | **项目依赖更新员** | ✅ |
| 76 | `update-all` | **全量依赖更新员** | ✅ |
| 77 | `rules-reviewer` | **规则审计员** | ✅ |
| 78 | `codex-plugin-sync` | **Codex 插件同步员** | ✅ |
| 79 | `package-manager` | **包管理总管** | ✅ |

---

## 6. v1.0 编排层（Meta-Plugin）

**不属于任何业务部门**。这是公司的"自动化神经系统"。

| # | Skill/Command | 职位名称 | 状态 | 详细职责 |
|---|--------------|---------|------|---------|
| 80 | `autoplan` | **全自动评审管道** | ❌ M6 | 一键依次调用 `plan-ceo-review` → `plan-design-review` → `plan-eng-review` → `plan-devex-review`，收集全部 verdict，生成综合评审报告。auto-decide mechanical 决策，surfaced taste 决策给人类 |
| 81 | `siunin-loop` | **自治运营循环** | ❌ M6 | 定时触发 routine："每周一跑 prioritization"、"每天早跑 prog-next"、"部署后 1 小时跑 canary check"。基于 `/loop` 机制 + cron |
| 82 | `cross-plugin-router` | **跨插件路由** | ❌ M6 | 标准化插件间 skill 调用。SPM 产出合同后自动触发 PROG 拆解。PROG 完成后自动通知 SPM 更新 status |

---

# 二、插件/Skill 数量统计

| 插件 | 已有 Skill | 已有 Agent | 待建 Skill | 所属部门 |
|------|----------|-----------|----------|---------|
| **super-product-manager** | 31 | 8 | 1 (plan-eng-review) | 产品部 / CPO |
| **progress-tracker** | 24 | 0 | 4 (tech-debt/adr/learnings/cross-project) | 幕僚处 + 工程营 / CTO |
| **note-organizer** | 3 | 0 | 0 | 个人工具 |
| **package-manager** | 6 | 0 | 0 | 个人工具 |
| **operations-department** | 0 | 0 | 5 (COO/finance/data/people) | 运营部 / COO |
| **gtm-department** | 0 | 0 | 5 (marketing/brand/community/sales/devrel) | GTM 部 / CMO |
| **编排层 (meta)** | 0 | 0 | 3 (autoplan/loop/router) | 中枢神经 |
| **合计** | **64** | **8** | **18** | — |

---

# 三、里程碑详细说明

## Milestone 0：Foundation（当前 v0.2）

### 目标
产品能被说清楚，进度不会被丢掉。

### 状态
- 产品部 31 个 skill + 8 个 agent → ✅ 就位
- 幕僚处进度追踪 14 个 skill → ✅ 就位
- 工程师执行 9 个 skill → ✅ 就位
- 辅助工具 9 个 skill → ✅ 就位

### 当前问题
- PROG 混杂了 **Chief of Staff（进度追踪）** 和 **Tech Lead（架构+实现）** 两个角色。v1.0 前需要概念上分开，但不一定拆插件——可以是 `prog` vs `prog-eng` 的命名空间
- 产品合同产出后，到 PROG 拆解执行，链路是人肉的（人类手动调用），不是自动的

---

## Milestone 1：CTO Suite — 工程大脑（v0.3）

### 为什么这是第一个 milestone
CEO review（SPM:plan-ceo-review）评审的是"该不该做"。
但没人管"怎么做才对"。产品合同通过 CEO 评审后，技术方向可能已经埋了坑。
CTO Suite 就是来填这个坑的。

### 交付：plan-eng-review

**放在哪里**：`plugins/super-product-manager/skills/plan-eng-review/SKILL.md`

**为什么放 SPM 不放 PROG**：SPM 的 4 个 plan review 构成完整的"产品合同评审管道"。plan-eng-review 是管道中的第四站（前三站：CEO → Design → DevEx）。它评审的对象依然是"产品合同"，只是从技术视角。所以逻辑上属于产品部。

**Skill 方法论设计**（参考 GStack plan-eng-review，中文重写）：

```
输入：docs/product-contracts/*.md（来自 office-hours）

评审六维度（每维 0-10 循环评分）：
1. 架构复杂度 —— 当前合同的技术复杂度被低估还是高估？
   - 单模块够用还是需要微服务？为什么？
2. 数据流完整性 —— 合同中的核心数据流覆盖四路径了吗？
   - happy path / nil path / empty path / error path
3. 技术债务风险 —— 为快速交付会欠下什么债？
   - 预计利息（每月多少时间还）和本金（未来一次性重写的成本）
4. 测试策略 —— 合同的每条 AC 对应什么测试层级？
   - unit / integration / e2e / manual —— 缺失层级标记
5. 性能瓶颈 —— 合同中隐含的性能假设是什么？
   - "X 操作应该在 Yms 内完成"——X 和 Y 是多少？做不到怎么办？
6. 安全边界 —— 合同涉及的功能触及了哪些信任边界？
   - 认证变更 / 数据暴露面扩大 / 权限模型变化

输出：
- docs/eng-reviews/{topic}-plan-eng-review.md
- 触发 ADR 提取（如果有关键架构决策）
- 触发技术债条目（PROG tech-debt 队列）
- Verdict: Approved / Approved with Risks / Deferred
```

**交互设计**：
- 交互模式：每完成一个维度，AskUserQuestion 确认 → 继续
- 批处理模式：六维度一次性评审，输出汇总 + Verdict
- 反谄媚规则："架构很清晰"→"以下三条数据流路径未覆盖 error case：..."

**子 Agent 自审**：同 SPM 另外三个 plan review 的 pattern

### 交付：ADR 决策记录系统

PROG 新增 `prog` 子命令 `prog adr`。

当 plan-eng-review 产出中包含架构决策时，自动提取：

```markdown
# ADR-001: 选择 SQLite 作为本地存储

## Context
PROG 需要在 session 之间持久化进度状态。
数据量 < 1MB，单用户单机器，不需要网络访问。
备选方案：JSON 文件（当前方案）、PostgreSQL、SQLite。

## Decision
选择 SQLite WAL 模式作为本地持久化方案。

## Alternatives Considered
- JSON 文件：当前在用，但并发写入不安全，多 agent 场景下有 corruption 风险
- PostgreSQL：太重，需要独立部署和维护，不符合"一人公司"的运维成本
- SQLite：零部署、零维护、支持并发读、WAL 模式支持一写多读

## Consequences
- 正面：并发安全、零运维、迁移简单
- 负面：单机限制（如果未来要分布式协作，需要迁移）
- 需要：progress-tracker 脚本改造、json → sqlite 迁移脚本
```

PROG 自动追踪："这个 ADR 后来有没有被后续 review 推翻？"

### 交付：技术债面板

在 `prog` 中新增 `tech-debt` 类别。

每次 plan-eng-review 识别到的技术债：
```json
{
  "id": "TD-042",
  "source": "plan-eng-review:2026-Q3-milestone1",
  "description": "office-hours 产出的合同落盘逻辑散落在 3 个脚本中",
  "estimated_interest": "每新增一个合同模板，需要改 3 个文件",
  "principal_cost": "1 天：抽象统一的合同落盘模块",
  "severity": "medium",
  "status": "acknowledged"
}
```

`prog-log` 中可视化：
```
当前技术债: 7 条（总预计本金: 5 天）
  - high: 1 条（SQLite 迁移）
  - medium: 4 条
  - low: 2 条
建议：下个迭代用 20% 产能还 high + 2 medium
```

---

## Milestone 2：Feedback Loop — 用户的声音（v0.4）

### 为什么重要
没有这个，SPM 的 roadmap 和 prioritize 是闭门造车。
roadmap 说"Q3 做功能 X"——但当 20 个用户在 Q2 末说"Y 是 blocker"时，
feedback-triage 是唯一一个会挑战 roadmap 的声音。

### 交付：feedback-triage

**放在哪里**：`plugins/super-product-manager/skills/feedback-triage/SKILL.md`

**Workflow**：
```
1. 收集：用户指定反馈来源
   - GitHub Issues（gh issue list）
   - 邮件（文本粘贴）
   - Discord/社群帖子（文本粘贴）
   - NPS 自由回复
   - App Store 评论

2. 分类（每条反馈打标签）：
   - bug → 关联到 PROG bug queue
   - feature-request → 关联到已有产品合同？新建 feature proposal？
   - ux-pain → 触发 SPM:ux-reviewer
   - confusion → 触发文档补全 / DevEx review
   - praise → 记录（用于 morale、testimonials）

3. 优先级：
   - "几个用户在说同一件事？"
   - "说的是核心流程还是边缘功能？"
   - "付费用户在说还是免费用户在说？"

4. 闭环追踪：
   - 如果一条反馈催生了 office-hours → 产品合同 → plan review → 实现，
     整个链路可追溯："Feature X 来自 GitHub Issue #342（用户 @foo）"

5. 定期报告（每周/每月）：
   - Top 3 用户痛点
   - 响应率（多少反馈被回复）
   - 闭环率（多少反馈驱动的功能已上线）
```

### Customer Success 仪表盘

```
==========================================
  上周用户声音（2026-W32）
==========================================
  新反馈: 23 条
    bug:        4 条（2 已修, 1 复现中, 1 待复现）
    feature:   12 条（3 进入下迭代, 4 关联已有合同, 5 parked）
    confusion:  7 条（3 已补文档）

  用户最痛的 3 件事:
  1. (报告 8 次) onboard → 首次 API 调用 > 5 分钟
     → plan-devex-review 已标记 TTHW Red Flag
     → docs + sample app 补全中（PROG task #47）
  2. (报告 5 次) 错误码 5003 无文档，Google 搜不到
     → feedback-triage → 文档已补 → 下周验证是否仍有反馈
  3. (报告 4 次) 免费额度不够用一轮完整评估
     → SPM:prioritize → 下迭代讨论是否调整 free tier
==========================================
```

---

## Milestone 3：Knowledge Layer — 公司记忆（v0.5）

### 为什么这是 v0.5 的分水岭
前 4 个 milestone 让公司**能做事**。这个 milestone 让公司**越做越聪明**。

没有 Learnings 系统：
- 每开一个新项目 = 重新踩一遍之前踩过的坑
- 每换一个新 session = PROG 知道"做到哪了"但不知道"我们学到了什么"
- 同样的架构决策讨论在不同项目中反复发生

有了 Learnings 系统：
- prog-done → 自动抽取："这次有什么值得下次记住的？"
- plan-eng-review 的 blocking issues → 自动沉淀为 pitfall
- 新项目开始 → PROG 主动注入相关 learnings："上次做类似功能时，这三个坑你踩过"
- 知识复利：公司积累的经验随项目数量增长

### Learnings 数据模型

```jsonl
{"id":"L001","type":"pitfall","key":"sqlite-multi-agent-corrupt",
 "insight":"SQLite WAL 多 agent 并发写→progress.json 损坏。fix:单 writer+fsync",
 "confidence":9,"source":"observed","date":"2026-04-15",
 "files":[".prog/scripts/sync.py"],"tags":["db","concurrency","prog"]}

{"id":"L002","type":"pattern","key":"plan-review-lane-routing",
 "insight":"4 个 plan review 顺序 CEO→Design→CTO(eng)→DevEx。CTO 前出 design 能减少返工",
 "confidence":8,"source":"inferred","date":"2026-05-20",
 "files":["plugins/super-product-manager/skills/plan-*/SKILL.md"],
 "tags":["process","planning","spm"]}

{"id":"L003","type":"preference","key":"anti-dark-mode-bias",
 "insight":"用户 Siunin 偏好——先做亮色主题，暗色放 backlog。因为目标用户(PM)主要在白天用",
 "confidence":10,"source":"user-stated","date":"2026-03-10",
 "files":[],"tags":["design","preference","siunin"]}
```

### Learnings 注入时机

| 时机 | 触发条件 | 注入方式 |
|------|---------|---------|
| prog-init | 新项目/新迭代开始 | 检索 tags 匹配，显示"该领域的经验教训" |
| feature-breakdown | 拆解功能时 | 该功能相关 tags 的 learnings 注入 PROG context |
| plan-eng-review | CTO 评审时 | 该技术栈/模式的 learnings 注入审查上下文 |
| bug-fix | 修复 bug 时 | 同类 bug 的历史 learnings |
| prog-done | 任务完结时 | 反问："有什么值得沉淀的吗？"→ 自动抽取 |

---

## Milestone 4：Operations — 运营大脑（v0.6）

### 为什么需要独立插件
产品部管"什么"，工程部管"怎么"，没人管"能不能持续"。

COO Suite 做的事，SPM 做太重（SPM 聚焦产品），PROG 做太工程（PROG 聚焦进度）。
这是一个独立的关心领域："公司作为一个系统的健康度"。

### 交付一览

**processize**：每发现有件事被手动做了两次，触发——
1. 记录为重复操作
2. 拆解为步骤
3. 评估哪些步骤可以 AI 自动化
4. 生成 SOP（Standard Operating Procedure）
5. 自动化脚本/checklist

**grow-sustainably**：
- 每次 launch 后 30 天，主动问："来跑一次可持续增长检查？"
- 盈利方程：MRR -（固定成本 + 可变成本）= ?
- 成本结构可视化：人工 / 基础设施 / 工具订阅 / 营销
- "default alive" 检查：在当前 burn rate 下，不新增收入能撑多久？

**finance-basics**：
- P&L 简表（月）
- 按功能/产品线的收入拆分
- 定价模型 ROI："上次涨价 20% 后，churn 涨了吗？net revenue 涨了吗？"
- 跑道 = cash / monthly_burn

---

## Milestone 5：GTM — 走向市场（v0.7）

### 放在哪里
首选方案：**并入 SPM**。
SPM 已经有 `launch`、`gtm-planner`、`compete`。GTM 是产品管理的自然延伸。

只有当 GTM skill > 10 个，且和 PM skill 的调用频率明显分层，才独立成插件。

### 5 个新 skill 概要

**marketing-plan**：
- 内容漏斗：engage → follow → research → consider → buy
- 三层内容策略：教育（教程/指南）、启发（案例/故事）、娱乐（meme/社区文化）
- "最后花钱"哲学：先验证 organic traction，再花钱投放

**find-community**：
- 用户已经在哪些社区？（GitHub Discussions / Discord / Reddit / Twitter/X / V2EX / 即刻）
- 你是真成员还是路过发广告？
- 输出：1-3 个目标社区 + 具体的互动策略

**first-customers**：
- 同心圆模型：朋友 → 社区成员 → 陌生人 cold outreach
- 冷启动话术模板
- 前 100 个客户的获取策略和时间表

**brand-strategy**：
- 品牌叙事："你做什么的？""为什么是你？"
- 视觉调性：和 design review 联动，确保产品 UI 和品牌一致
- 5 秒测试："看你的网站 5 秒，知道你是做什么的吗？"

**devrel-strategy**（增强已有 plan-devex-review）：
- plan-devex-review 现在只做评审（audit/review）
- devrel-strategy 做策划（plan/design）：基于评审发现，设计 onboarding 改进、sample app、workshop 大纲

---

## Milestone 6：v1.0 — 全公司就绪

### v1.0 的定义
一个人带着 Claude Code，能：
1. 从一句话想法 → 产品合同（SPM:office-hours）
2. 合同 → 被 4 个 review 评审通过（CEO/Design/CTO/DevEx）
3. 通过的合同 → 自动拆解为 PROG 任务（feature-breakdown）
4. 任务 → AI 逐个实现（feature-implement）
5. 实现 → 测试 → 上线（testing-standards → git-auto → launch）
6. 上线后 → 用户反馈回流 → 触发下一迭代（feedback-triage → office-hours）
7. 整个过程被 PROG 追踪（prog）
8. 关键经验被 Learnings 记录（learnings）
9. 下一轮时，Learnings 主动注入上下文，避免重复踩坑

### v1.0 Checklist

```
[✓] 产品部 0→1: office-hours / prd / mvp / idea
[✓] 产品部 1→100: roadmap / prioritize / story
[✓] 用户研究: persona / interview / researcher
[✓] 数据分析: analyst / metrics
[✓] CEO  策略评审: plan-ceo-review  (4 模式 + 影子路径 + Bezos 框架)
[✓] 设计 策略评审: plan-design-review (四维加权 + 6 框架)
[✓] DevEx 策略评审: plan-devex-review (三阶段摩擦 + TTHW + P0/P1/P2)
[✓] UX 评审: ux-reviewer
[✓] 竞品: compete / market-research / market-validation
[✓] 上线: launch / gtm-planner
[✓] 法务: legal-compliance
[✓] 翻译: dev-translator
[✓] 幕僚长: prog / recovery / breakdown / init-done-reset
[✓] Git: git-auto
[✓] Bug: bug-fix
[✓] 测试: testing-standards
[✓] 实现: feature-implement (simple/complex)

[ ] plan-eng-review（CTO）           ← Milestone 1
[ ] ADR 系统                         ← Milestone 1
[ ] 技术债面板                        ← Milestone 1
[ ] feedback-triage                  ← Milestone 2
[ ] Customer Success 仪表盘           ← Milestone 2
[ ] Learnings 系统                   ← Milestone 3
[ ] Cross-project 知识                ← Milestone 3
[ ] COO Suite (3 skill)              ← Milestone 4
[ ] Data Pipeline                    ← Milestone 4
[ ] GTM Suite (5 skill)              ← Milestone 5
[ ] autoplan                         ← Milestone 6
[ ] 自治运营循环                       ← Milestone 6
[ ] 跨插件路由标准化                    ← Milestone 6
```

---

# 四、产品 0→1→100 完整工作流

## 0→1 阶段：从 Idea 到 PMF

```
人类: "我有个想法：一个帮助 PM 写产品合同的 AI 工具"
  │
  ▼
SPM:idea ────────── 孵化想法 → 一句话方向
  │
  ▼
SPM:strategist ──── 产品愿景、商业模式雏形
  │
  ▼
SPM:persona ─────── "谁会用它？PM 在日常工作中的痛点是什么？"
SPM:interview ───── 用户访谈提纲 → 验证假设
  │
  ▼
SPM:market-validation ── "有市场吗？"
slavingia:validate-idea ──（参考外部 skill）"有人愿意付钱吗？"
  │
  ▼
SPM:office-hours ── "那我们来写第一版产品合同"──→ docs/product-contracts/
  │ 产出: Goals / Scope / AC / Risks（纯产品，零技术细节）
  │
  ▼
SPM:mvp ─────────── "这个合同中，MVP 是哪几条 AC？"
  │
  ▼
┌─── Plan Review 管道 ───┐
│ SPM:plan-ceo-review     │ ← "MVP 方向对吗？机会有多大？"
│ SPM:plan-design-review  │ ← "MVP 的 UX 够简单吗？AI Slop 风险？"
│ SPM:plan-eng-review     │ ← "MVP 的技术方案是什么？欠什么债？"
│ SPM:plan-devex-review   │ ← "如果是 dev tool，开发者的 TTHW？"
└─────────────────────────┘
  │ 每个 review 输出: 评分 + Verdict + 建议修改
  │
  ▼
SPM:prd ─────────── 汇总所有 review 反馈 → 最终 PRD
  │
  ▼
PROG:prog-init ──── "开始追踪这个项目"
PROG:feature-breakdown ── MVP 拆成 3-5 个 task
  │
  ▼
PROG:feature-implement ── AI 逐个实现 task
PROG:testing-standards ── 每个 task 有测试
PROG:git-auto ─────────── commit / PR
  │
  ▼
SPM:launch ──────── "MVP 上线"
  │
  ▼
=== PMF 验证期 ===
feedback-triage ←── 用户反馈开始回流
  │
  ▼ "PMF 达到？→ 进入 1→100"
```

## 1→100 阶段：从 PMF 到规模化

```
SPM:roadmap ─────── "下 6 个月做什么？"
SPM:prioritize ──── "Q3 先做哪个？不做哪个？"
  │
  ▼
SPM:office-hours ── 每个 roadmap item → 独立产品合同
  │
  ▼
Plan Review 管道 ── 每个合同过 4 个 review
  │
  ▼
PROG:breakdown ──── 拆解 + 实现 + 测试 + PR
  │
  ▼
SPM:analyst ────── "上次 launch 的 feature，数据表现如何？"
SPM:metrics ────── "北极星指标有在涨吗？"
  │
  ▼
feedback-triage ── "用户在用的时候卡在哪？"
  │
  ▼
SPM:compete ────── "竞品这季度做了什么？我们的 differentiation 还在吗？"
  │
  ▼
COO:grow-sustainably ── "burn rate 健康吗？default alive？"
COO:finance-basics ──── "这个定价模型 ROI 是多少？"
  │
  ▼
GTM:marketing-plan ── "我们怎么让更多人知道？"
GTM:find-community ── "目标用户在哪里聚集？"
  │
  ▼
=== 回到 roadmap，下一轮迭代 ===
```

---

# 五、架构决策记录

这些是**今天（2026-04-30）做的关键架构决策**，记录在 roadmap 中防止遗忘。

### ADR-1：插件 = 部门，skill = 职位
- 为什么不做一个超级插件？→ 职责边界清晰，调试成本低，社区复用性好
- 每个插件的 `plugin.json` description 写清楚"这是个什么部门"

### ADR-2：SPM 包含 plan-eng-review，不放 PROG
- 理由：4 个 plan review 构成完整的"合同评审管道"，都在产品合同中运作
- 如果未来 plan-eng-review 膨胀到需要大量工程工具（profiler、build checker），再考虑拆

### ADR-3：GTM 先并入 SPM，不独立建插件
- 理由：SPM 已有 launch/gtm-planner/compete。GTM 是 PM 的自然延伸
- 触发拆分的条件：GTM skill > 10 个，且和 PM skill 调用频率明显分层

### ADR-4：参考 gstack/slavingia/Trellis，但不依赖
- 所有方法论内化后用中文重写。不 require 外部插件作为 dependency
- 用户可以自行安装 gstack 的 plan-eng-review 做对比，但 SPM 必须有自己的版本

### ADR-5：Learnings 放在 PROG 而非独立插件
- PROG 追踪"进度"+"知识"，因为两者是同源的——"我们做到哪了"+"我们学到了什么"

### ADR-6：反谄媚规则是所有 skill 的标配
- GStack 没有显式的反谄媚机制。SPM 原创的这一设计被保留并推广到所有新 skill

---

# 六、不做的事（Scope Guard）

| 事项 | 原因 |
|------|------|
| Design mockup 生成器（GStack design 二进制） | 设计工具链，非 PM/工程核心。可用外部工具替代 |
| Browser 自动化 QA（GStack browse） | 独立 QA 工具。可调用但不需要在 siunin-plugins 中维护 |
| 代码级安全扫描（GStack CSO/OWASP） | plan-eng-review 审查的是架构层安全，不是 SAST |
| plan-tune（问题调优/偏好管理） | 这是 Claude Code 平台层的用户个人设置，不是业务插件 |
| 自研 IDE / 自研浏览器 | 不是 SaaS 公司的职责范围 |
| 代码级 CI/CD pipeline 引擎 | GitHub Actions / GitLab CI 已足够。我们只需要 `ship` orchestration |

---

# 七、里程碑时间线

```
2026 Q2 ──── v0.2 Foundation ──── 当前
  │           产品部 31 skill + 幕僚处 24 skill 可独立运作
  │           4 个 plan review (CEO/Design/DevEx) 已就位
  │
  │~~~ Q3 开始 ~~~
  │
2026 Q3 ──── Milestone 1: CTO Suite (v0.3)
  │           plan-eng-review + ADR + 技术债面板
  │           → 产品合同终于有技术把关了
  │
  │          Milestone 2: Feedback Loop (v0.4)
  │           feedback-triage + CS 仪表盘
  │           → 用户声音能自动回流到 SPM
  │
  │~~~ Q4 开始 ~~~
  │
2026 Q4 ──── Milestone 3: Knowledge Layer (v0.5)
  │           Learnings 系统 + cross-project 知识迁移
  │           → 公司越做越聪明，跨 session 跨项目积累
  │
  │          Milestone 4: Operations (v0.6)
  │           COO Suite + 财务 + 数据管道
  │           → 公司有运营大脑，不只是开发车间
  │
  │~~~ 2027 Q1 ~~~
  │
2027 Q1 ──── Milestone 5: GTM (v0.7)
  │           营销 + 社区 + 品牌 + DevRel
  │           → 产品能卖出去，不只是在做
  │
  │          Milestone 6: 全公司就绪 (v1.0)
  │           autoplan + 自治循环 + 跨插件路由
  │           → 一人公司跑通完整闭环
```

---

# 八、哲学原则（每天提醒自己）

1. **插件 = 部门，skill = 职位。**
   每个插件有清晰的职责边界。拒绝"一个插件什么都能干"。

2. **人类在回路中。**
   AI 95% 执行，人类 5% 品味/方向/最终决策。
   所有 blocking 建议 = AskUserQuestion，从不 auto-apply。

3. **先深度再广度。**
   一个 CTO skill 做到"真的能拦住烂架构"，比 10 个浅薄 skill 更重要。

4. **知识复利。**
   Learnings 系统是 v1.0 的分水岭。有了它，公司随着时间越来越聪明。
   没有它，每开一个新项目 = 从零开始。

5. **中文原生。**
   方法论、反谄媚规则、示例都在中文语境下设计和验证。
   英文社区的精华（gstack / slavingia / Trellis）作为参考，内化后中文重写。

6. **一人公司 = 最低可行复杂度。**
   能用 SQLite 就不用 Postgres。能手动的先手动（processize → 自动化）。
   不为了"架构优雅"而引入额外的运维负担。
