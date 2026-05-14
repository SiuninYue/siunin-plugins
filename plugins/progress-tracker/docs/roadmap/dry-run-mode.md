# Dry-Run 验证模式

## 目标

在任何阶段支持"仅验证、不写代码"的运行模式。让 AI 走一遍完整流程，在纸面上暴露逻辑漏洞、设计矛盾、依赖缺失。零成本试错。"先编排再开发"的技术实现。

## 当前状态

- ❌ 无 dry-run 概念——所有 skill 默认以"真正执行"模式运行
- ❌ 验证想法只能通过真正跑一遍流程，改错成本高
- ✅ 8 阶段管线架构已定义，每个阶段独立可触发
- ✅ ROADMAP 中已描述"先编排再开发"原则，但无技术支撑

## 方案设计

### Dry-Run 模式的语义

Dry-run 不是"什么都不做"，而是"**只做分析和输出，不做任何持久化变更**"。

| 操作类型 | 正常模式 | Dry-Run 模式 |
|---------|---------|-------------|
| 读取文件 | ✅ | ✅ |
| 分析/推理 | ✅ | ✅ |
| 调用 LLM | ✅ | ✅（但可降级模型节省成本） |
| 写入文件 | ✅ | ❌ → 输出"将写入的内容"预览 |
| git 操作 (commit/push) | ✅ | ❌ → 输出"将执行的 git 命令" |
| 修改配置 | ✅ | ❌ → 输出"将修改的配置项" |
| 安装依赖 | ✅ | ❌ → 输出"将安装的包列表" |
| 运行编译/测试 | ✅ | ⚠️ → 可选（分析层面判断，不实际运行） |
| 生成报告 | ✅ | ✅ → 输出 Dry-Run Report |

### 触发方式

```
触发方式 1：skill 调用时显式声明
  /progress-tracker:feature-implement --dry-run f23
  /progress-tracker:prog-plan --dry-run "新功能描述"

触发方式 2：环境变量
  PROG_DRY_RUN=true
  后续所有操作自动进入 dry-run 模式

触发方式 3：交互式切换
  在任何 skill 运行中，用户说"先用 dry-run 跑一遍"
  AI 切换模式，从头重跑当前步骤
```

### Dry-Run Report 格式

每个阶段完成 dry-run 后输出结构化报告：

```markdown
# Dry-Run Report: feature-implement (f23)

## 执行摘要
- 阶段：05 Dev Builder
- Feature：f23 — 用户反馈仪表盘
- 模式：DRY-RUN（无任何文件被修改）

## 将执行的变更
| 操作 | 详情 | 影响文件 |
|------|------|---------|
| 新建 | DashboardPage.tsx | src/pages/DashboardPage.tsx |
| 修改 | 路由注册 | src/router.ts |
| 新建 | 数据查询 hook | src/hooks/useFeedbackStats.ts |
| 新建 | 测试 | src/pages/__tests__/DashboardPage.test.tsx |

## 发现的问题
1. **[阻塞] 数据源未定义** — useFeedbackStats hook 需要的数据格式未在 feedback-triage 产出中定义
   → 建议：先回 01 Product Spec 补充数据类型定义
2. **[警告] 组件复用** — DashboardPage 和已有 ReportPage 的图表组件 70% 重叠
   → 建议：先提取共享 Chart 组件
3. **[提示] 权限模型** — 仪表盘是否需要按角色过滤数据？AC 未覆盖此场景

## 预计工作量
- 文件数：6
- 复杂度评分：standard (48/100)
- 建议模型：sonnet
- 预计耗时：30-45 min

## 下一步
建议修复问题 1 后再进入正常模式实现。
```

### 在 8 阶段中的使用场景

```
场景 A：新想法快速验证
  用户："我有个想法，加个数据导出功能"
  → 01 Product Spec Builder --dry-run → 产出需求草稿
  → 02 Design Brief Builder --dry-run → 产出设计规范草稿
  → 04 Dev Planner --dry-run → 拆解任务草稿
  → 用户看到完整链路后决策"做/不做/改方向"

场景 B：单阶段深度验证
  用户："这个设计方案先不要做，跑一遍 design review 看看有什么坑"
  → 02 Design Brief Builder 正常产出设计规范
  → plan-design-review --dry-run → 输出评审报告
  → 不写任何代码，发现问题在纸面上修正

场景 C：危险操作预演
  用户："我要重构数据库 schema，先 dry-run 看看影响面"
  → 04 Dev Planner --dry-run → 分析影响范围
  → 列出所有受影响的文件/表/API
  → 评估风险后再决定是否真执行
```

## 实现方式

### Skill 层面的修改

每个 skill 的 SKILL.md 增加 DRY-RUN 模式说明：

```markdown
## Dry-Run 模式

当 `--dry-run` 参数存在或 `PROG_DRY_RUN=true` 时：
1. 正常执行所有分析和推理步骤
2. 任何文件写入、git 操作、配置修改 → 仅输出预览，不实际执行
3. 最终输出 Dry-Run Report（格式见下方模板）
4. 在报告顶部显著标注"**DRY-RUN — 无任何文件被修改**"
```

### 不需要改的 skill

以下 skill 天然只读，无需 dry-run 适配：
- prog（状态查询）
- prog-log（日志查看）
- plan-ceo-review / plan-design-review / plan-devex-review（评审类，本身就是分析）
- bug-fix 的分析阶段（证据收集 + 假设验证）

## 实现步骤

```
Phase 1 — 基础设施
  [ ] 定义 DRY_RUN 标志传递机制（环境变量 + CLI 参数）
  [ ] 编写 Dry-Run Report 模板
  [ ] 选择 1 个 skill 做端到端验证（建议 feature-implement-simple）

Phase 2 — 核心 skill 适配
  [ ] feature-implement 系列适配 dry-run
  [ ] feature-breakdown 适配
  [ ] prog-init 适配
  [ ] git-auto 适配

Phase 3 — 扩展覆盖
  [ ] office-hours / prd 适配（dry-run 时产出草稿而非正式文档）
  [ ] launch 适配
  [ ] 8 阶段全链路 dry-run 集成测试
```

## 影响范围

- **修改**：所有涉及写入操作的 skill SKILL.md（增加 DRY-RUN section）
- **新增**：`.prog/dry-run/` 目录（存放 dry-run 产生的临时报告）
- **修改**：`prog` CLI — 支持 `--dry-run` 全局参数
- **不改**：只读 skill（prog / prog-log / plan-review 系列）

## 成功标准

- [ ] 至少 5 个核心 skill 支持 dry-run 模式
- [ ] dry-run 下确实无任何文件被修改（自动化测试验证）
- [ ] Dry-Run Report 包含问题发现率 ≥80%（即能发现真实存在的问题，人工评估）
- [ ] 正常模式和 dry-run 模式切换延迟 < 1 秒

## 风险与防御

| 风险 | 概率 | 防御 |
|------|------|------|
| AI 在 dry-run 中仍然写文件 | 中 | hook 层拦截所有 Write/Bash(git) 操作 |
| dry-run 结果过于乐观（漏报问题） | 高 | 标注置信度；对比同一 feature 的 dry-run vs 实际结果来校准 |
| 用户忘记自己在 dry-run 模式 | 低 | 每条输出前加 `[DRY-RUN]` 前缀 |

## 待决策

- [ ] dry-run 时是否允许实际运行测试（编译可以，但跑测试套件可能很慢）？
- [ ] dry-run 报告是否持久化（落盘 .prog/dry-run/）还是仅对话中展示？
- [ ] 是否需要 `--dry-run-strict` 模式（连 LLM 调用都用更便宜模型）？
