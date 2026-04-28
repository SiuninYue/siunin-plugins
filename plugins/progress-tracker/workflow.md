# Prog 工作流文档

> 最后更新: 2026-04-28
> 覆盖版本: feature-implement v3.2.0, feature-complete v2.2.0, bug-fix v1.0.0

---

## 目录

- [一、易读概览](#一易读概览)
  - [1.1 一张图看完整个流程](#11-一张图看完整个流程)
  - [1.2 核心概念速查](#12-核心概念速查)
  - [1.3 状态机速查](#13-状态机速查)
  - [1.4 复杂度分桶与路由](#14-复杂度分桶与路由)
  - [1.5 用户交互点汇总](#15-用户交互点汇总)
- [二、超级详细版](#二超级详细版)
  - [2.1 项目初始化阶段](#21-项目初始化阶段)
  - [2.2 功能实现阶段 /prog next](#22-功能实现阶段-prog-next)
  - [2.3 功能完成阶段 /prog done](#23-功能完成阶段-prog-done)
  - [2.4 Bug 修复流程 /prog-fix](#24-bug-修复流程-prog-fix)
  - [2.5 管理操作](#25-管理操作)
  - [2.6 恢复与断点续跑](#26-恢复与断点续跑)
  - [2.7 完整 CLI 命令参考](#27-完整-cli-命令参考)
  - [2.8 skill 调用关系图](#28-skill-调用关系图)
  - [2.9 progress.json 数据结构](#29-progressjson-数据结构)
  - [2.10 质量门禁体系](#210-质量门禁体系)

---

# 一、易读概览

## 1.1 一张图看完整个流程

```
                        ┌──────────────────────────┐
                        │   /prog init <goal>       │
                        │   feature-breakdown       │
                        │   拆分为 5-10 个 feature   │
                        └────────────┬─────────────┘
                                     │
                        ┌────────────▼─────────────┐
                        │   /prog plan (可选)        │
                        │   architectural-planning   │
                        │   生成 architecture.md     │
                        └────────────┬─────────────┘
                                     │
              ┌──────────────────────▼──────────────────────┐
              │            /prog next  循环                  │
              │  ┌──────────────────────────────────────┐   │
              │  │        feature-implement              │   │
              │  │                                      │   │
              │  │  复杂度评分 ──▶ 路由到三条路径之一    │   │
              │  │    │            │            │       │   │
              │  │  simple     standard     complex     │   │
              │  │  (0-15)     (16-25)      (26-40)    │   │
              │  │  haiku      sonnet        opus      │   │
              │  │    │            │            │       │   │
              │  │    ▼            ▼            ▼       │   │
              │  │  TDD      规划→TDD    头脑风暴→     │   │
              │  │            →审查      规划→TDD      │   │
              │  │            →验证      →审查→验证    │   │
              │  │    │            │            │       │   │
              │  │    └────────────┼────────────┘       │   │
              │  │                 ▼                    │   │
              │  │       execution_complete             │   │
              │  └──────────────────────────────────────┘   │
              │                    │                        │
              │                    ▼                        │
              │  ┌──────────────────────────────────────┐   │
              │  │         /prog done                    │   │
              │  │         feature-complete              │   │
              │  │                                      │   │
              │  │  验收测试 → 评估器 → 最终审查        │   │
              │  │  → git closeout → 归档 → 清理状态   │   │
              │  └──────────────────────────────────────┘   │
              │                    │                        │
              │   还有下一个 feature? ──Yes──▶ 回到顶部     │
              │                    │                        │
              │                   No                        │
              └────────────────────┬───────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │   项目完成! 🎉   │
                          └─────────────────┘
```

### 旁路: Bug 修复

```
报告 bug ──▶ 快速验证(30s) ──▶ 用户选择 ──▶ 排期 ──▶ 系统调试 ──▶ TDD 修复 ──▶ 审查
```

### 旁路: 管理

```
/prog undo  ──▶ 回滚最近 feature (git revert + 状态回滚)
/prog reset ──▶ 清空所有进度 (归档后重置)
```

---

## 1.2 核心概念速查

| 概念 | 说明 | 存储位置 |
|------|------|---------|
| **Feature** | 一个可独立完成、提交、验收的功能单元 | `progress.json → features[]` |
| **复杂度分桶** | simple/standard/complex 三级，决定执行路径和模型 | 评分后写入 `ai_metrics.complexity_bucket` |
| **Workflow State** | 顶层 `workflow_state.phase`，驱动断点续跑 | `progress.json → workflow_state` |
| **Sprint Contract** | 功能的 scope/done_criteria/test_plan | `feature.sprint_contract` |
| **Quality Gates** | evaluator + reviews + ship_check 三道门禁 | `feature.quality_gates` |
| **Plan** | 实现计划文档，位于 `docs/plans/YYYY-MM-DD-*.md` | `feature.plan_path` / `workflow_state.plan_path` |
| **Handoff Block** | 传递到新 session 的上下文块，含 inline context | skill 输出末尾 |
| **inline context** | Handoff 块中预加载的状态行，跳过重复读取 | `Feature:`, `Phase:`, `Plan:` 等行 |
| **Sprint Ledger** | 追加不可变的 sprint 产物记录 (JSONL) | `state/sprint_ledger.jsonl` |

---

## 1.3 状态机速查

### workflow_state.phase 完整状态列表

```
                        ┌─────────────┐
                        │  (未设置)    │  新 feature，还未进入规划
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │  planning   │  开始规划（旧版兼容值）
                        └──────┬──────┘
                               │
                   ┌───────────┼───────────┐
                   │           │           │
            ┌──────▼──┐  ┌─────▼───┐  ┌────▼──────┐
            │planning:│  │planning:│  │planning:   │
            │clarifying│  │ draft   │  │ approved   │
            └──────┬──┘  └─────┬───┘  └────┬───────┘
                   │           │           │
                   │    用户审批          │ 直接路由执行
                   │           │           │
                   └───────────┼───────────┘
                               │
                   ┌───────────▼───────────┐
                   │   planning:review     │  计划审查（planning:draft/clarifying 的归一化目标）
                   └───────────┬───────────┘
                               │
                   ┌───────────▼───────────┐
                   │  design_complete      │  complex 路径：头脑风暴完成，进入规划
                   └───────────┬───────────┘
                               │
                   ┌───────────▼───────────┐
                   │  planning_complete    │  计划完成，等待执行
                   └───────────┬───────────┘
                               │
                   ┌───────────▼───────────┐
                   │     execution         │  正在实现
                   └───────────┬───────────┘
                               │
                   ┌───────────▼───────────┐
                   │  execution_complete   │  实现完成，等待 /prog done
                   └───────────────────────┘
```

### wf_state_machine.py 动作映射

| phase | compute_next_action() 返回值 |
|-------|---------------------------|
| `None` / 不存在 | `None` — 正常启动 |
| `planning` | `restart_from_planning` |
| `planning:clarifying` | `resume_planning_draft` (归一化) |
| `planning:draft` | `resume_planning_draft` |
| `planning:review` | `resume_planning_draft` |
| `planning:approved` | `execute_approved_plan` |
| `planning_complete` | `execute_approved_plan` |
| `design_complete` | `restart_from_planning` |
| `design` | `restart_from_planning` (防御性) |
| `execution` + 任务未完 | `continue_execution` |
| `execution` + 任务全完 | `run_prog_done` |
| `execution_complete` | `run_prog_done` |

### sprint_ledger 阶段 (VALID_PHASES)

```
plan → implementation → evaluation → handoff
```

注意：sprint_ledger 的阶段 (`plan/implementation/evaluation/handoff`) 与 workflow_state.phase 是**两套独立系统**。前者追踪 sprint 产物，后者驱动 session 恢复。

---

## 1.4 复杂度分桶与路由

### 评分维度 (每个 0-10 分，满分 40)

| 维度 | 说明 | 低(2分) | 中(5分) | 高(8分) | 极高(10分) |
|------|------|---------|---------|---------|-----------|
| File Impact | 预计修改文件数 | 1-2 文件 | 3-5 文件 | 6-10 文件 | 10+ 文件 |
| Test Complexity | 测试步骤数 | <3 步 | 3-5 步 | 6-8 步 | >8 步 |
| Design Decisions | 设计决策难度 | 无 | 小模式选择 | 模块/API 设计 | 架构级决策 |
| Pattern Familiarity | 模式熟悉度 | 完全一致 | 相似存在 | 新但标准 | 全新无先例 |

### 分桶与路由

```
分数范围    桶        模型      执行路径                   委托 skill
──────────────────────────────────────────────────────────────────────
 0-15      simple     haiku     direct_tdd                 feature-implement-simple
16-25      standard   sonnet    plan_execute               本 coordinator 内执行
26-40      complex    opus      full_design_plan_execute   feature-implement-complex
```

### 强制覆写规则

- **强制 complex**: 显式架构重设计 / 核心子系统重构且依赖未知 / 跨模块横切变更
- **强制 simple**: 已知修复方案的单小 bug / 无架构设计决策 / 最小测试面

---

## 1.5 用户交互点汇总

一个 feature 从开始到完成，用户需要参与的交互点：

| 序号 | 阶段 | 交互类型 | 说明 |
|------|------|---------|------|
| 1 | `planning:clarifying` | 回答问题 | 回答 2-4 个设计决策问题 |
| 2 | `planning:draft` | 审批计划 | 审阅计划文档，确认或修改 |
| 3 | `execution_complete` | 执行命令 | 运行 `/prog done` |

**各复杂度路径的实际交互次数：**

| 路径 | 规划交互 | done 交互 | 总计 |
|------|---------|----------|------|
| simple | 0 (跳过规划) | 1 | **1** |
| standard | 2 (clarifying + draft) | 1 | **3** |
| complex | 2 (clarifying + draft) | 1 | **3** |

> 注：inline context fast path 可以跳过交互点 1 和 2（直接从 `planning:approved` 开始执行）。

---

# 二、超级详细版

## 2.1 项目初始化阶段

### 2.1.1 `/prog init <goal>` — 功能拆解

**触发 skill**: `progress-tracker:feature-breakdown` (model: opus)

**完整步骤:**

1. 分析用户目标，理解项目范围和约束
2. **检查架构文档**: 读取 `docs/progress-tracker/architecture/architecture.md`
   - 若存在：提取技术栈、架构模式、Execution Constraints (CONSTRAINT-*)
   - 若不存在且项目复杂：建议先跑 `/prog plan`
3. 按 **1-2 小时可完成** 的粒度拆解 feature
4. 按依赖关系排序：数据模型 → 后端逻辑 → 外部接口 → 前端 → 集成
5. 为每个 feature 生成 **2-4 个可执行测试步骤**
6. 调用 CLI 持久化:
   ```bash
   plugins/progress-tracker/prog init "<project_name>"
   plugins/progress-tracker/prog add-feature "<name>" "<step1>" "<step2>" ...
   ```
7. 验证 `progress.json` 和 `progress.md` 已创建

### 2.1.2 `/prog plan` — 架构规划

**触发 skill**: `progress-tracker:architectural-planning` (model: opus)

**完整步骤:**

1. **Phase 1: 需求分析** — 询问项目上下文、技术约束、团队情况
2. **Phase 2: 技术选型** — 为每项技术决策输出决策模板
3. **Phase 3: 架构设计** — 系统结构、数据流、组件边界
4. **Phase 4: 决策文档** — 生成 `docs/progress-tracker/architecture/architecture.md`

**architecture.md 必须包含的 8 个章节:**
1. `## Goals`
2. `## Scope Boundaries`
3. `## Interface Contracts`
4. `## State Flow`
5. `## Failure Handling`
6. `## Acceptance Criteria`
7. `## Key Architectural Decisions (ADR)`
8. `## Execution Constraints` — 机器可消费格式:
   ```markdown
   - [CONSTRAINT-001] <规则简述>
     - Applies to: <作用范围>
     - Must: <确定性要求>
     - Validation: <验证方式>
   ```

---

## 2.2 功能实现阶段 `/prog next`

**触发 skill**: `progress-tracker:feature-implement` (model: sonnet, coordinator)

### 完整入口流程

```
用户输入 /prog next
        │
        ▼
┌──────────────────────────────────────┐
│  Inline Context Fast Path            │  优先检查！
│  若有 Feature:/Phase:/Plan: 等行     │
│  → 跳过 Step 1-2.5，直接按 Phase 路由 │
└──────────────────────────────────────┘
        │ (无 inline context)
        ▼
┌──────────────────────────────────────┐
│  Step 1: 验证当前状态                 │
│  - 读 progress.json                  │
│  - 无文件 → 提示 /prog init          │
│  - 全完成 → 显示完成信息，停止        │
│  - current_feature_id 已设置 →        │
│    按顶层 workflow_state.phase 判断:  │
│    · execution_complete → 提示 done  │
│    · execution/planning_complete →   │
│      从 plan_path 续跑                │
│    · planning/未设置 → 正常继续       │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 2: 选择并锁定 Feature           │
│  prog next-feature --json            │
│  prog set-current <feature_id>       │
│  (set-current 自动将 feature 转入    │
│   development_stage: developing)     │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 2.4: 项目内存重叠检查           │
│  prog memory read                    │
│  - 仅首次启动时运行（非续跑）         │
│  - 关键词匹配 → 仅明确碰撞时警告      │
│  - 永远不阻塞 /prog next             │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 2.5: Git 自动预检              │
│  prog git-auto-preflight --json      │
│  三种决策:                           │
│  · ALLOW_IN_PLACE → 继续             │
│  · REQUIRE_WORKTREE →                │
│    Skill("superpowers:using-git-     │
│          worktrees")                 │
│  · DELEGATE_GIT_AUTO →               │
│    Skill("progress-tracker:git-auto")│
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 3: 规划子阶段                   │
│  (详见下方 2.2.1)                    │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 4: 按复杂度路由                 │
│  (详见下方 2.2.2 / 2.2.3 / 2.2.4)   │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 5-6: 持久化 + 输出 Handoff     │
│  - set-workflow-state 更新 phase     │
│  - 输出 Context Handoff Block        │
└──────────────────────────────────────┘
```

### 2.2.1 Step 3: 规划子阶段 (三个子阶段)

#### 子阶段 A: `planning:clarifying`

```
复杂度评分 (参考 complexity-assessment.md)
        │
        ▼
prog set-feature-ai-metrics <id> \
  --complexity-score <score> \
  --selected-model <haiku|sonnet|opus> \
  --workflow-path <direct_tdd|plan_execute|full_design_plan_execute>
        │
        ▼
分析 feature，识别 2-4 个设计决策问题
(跳过显而易见的)
        │
        ▼
prog set-workflow-state --phase "planning:clarifying"
        │
        ▼
输出 planning:clarifying handoff block
        │
        ▼
直接向用户提问 ──▶ STOP 等待用户回答
```

#### 子阶段 B: `planning:draft`

```
用 writing-plans skill (含用户答案) 生成计划
        │
        ▼
生成 PlanSummary (单行, 分号分隔, 3-5 要点)
        │
        ▼
prog set-workflow-state \
  --phase "planning:draft" \
  --plan-path <path>
        │
        ▼
展示完整计划 + planning:draft handoff block
        │
        ▼
STOP 等待用户审批
```

#### 子阶段 C: `planning:approved`

```
prog set-workflow-state \
  --phase "planning:approved" \
  --plan-path <path>
        │
        ▼
输出 planning:approved handoff block
        │
        ▼
立即按 bucket 路由执行 (同 session，不断开)
```

### 2.2.2 路径 A: Simple (0-15 分)

**委托 skill**: `progress-tracker:feature-implement-simple` (model: haiku, user-invocable: false)

**完整步骤：**

```
Step 1: 验证复杂度 bucket == simple
Step 2: 生成执行记录 (幂等):
        prog generate-direct-tdd-note
        → 从 feature 元数据创建最小执行记录
        → 收敛 workflow_state → phase=execution, next_action=direct_tdd
        → 设置 plan_path
Step 3: 显示执行 banner (feature + haiku 模型)
Step 4: Skill("superpowers:test-driven-development",
               args="<feature_name>: <one_line_description>")
        → RED → GREEN → REFACTOR 循环
Step 5: 填充 sprint contract:
        prog set-sprint-contract \
          --feature-id <id> \
          --scope "..." \
          --done-criteria "..." "..." \
          --test-plan "..." "..."
Step 6: Skill("superpowers:requesting-code-review",
               args="Review simple feature: <name>")
Step 7: Skill("superpowers:verification-before-completion",
               args="Verify tests for <name>")
Step 8: prog set-workflow-state --phase "execution_complete" \
          --next-action "verify_and_complete"
        prog set-feature-ai-metrics <id> \
          --complexity-score <score> \
          --selected-model haiku \
          --workflow-path direct_tdd
Step 9: 提示用户运行 /prog done
```

**涉及的质量门禁 (共 3 层):**
1. TDD (superpowers:test-driven-development)
2. Code Review (superpowers:requesting-code-review)
3. Verification (superpowers:verification-before-completion)

### 2.2.3 路径 B: Standard (16-25 分)

**在当前 coordinator 中执行 (model: sonnet)**

**完整步骤：**

```
Step 4B.1: Skill("superpowers:brainstorming", ...)
           (仅当行为/设计决策仍开放时)

Step 4B.2: Skill("superpowers:writing-plans",
                  args="创建可执行任务计划")
           → 产出 docs/plans/YYYY-MM-DD-<slug>.md

Step 4B.2.5: prog set-sprint-contract \
               --feature-id <id> \
               --scope "..." \
               --done-criteria "..." \
               --test-plan "..."

Step 4B.3: Skill("superpowers:subagent-driven-development",
                  args="plan:<path>")
           → 用 TDD 执行计划中的所有 task

Step 4B.4: Skill("superpowers:requesting-code-review",
                  args="最终 diff 验证")

Step 4B.5: Skill("superpowers:verification-before-completion",
                  args="转向 execution_complete 前的验证")

阶段推进:
  prog set-workflow-state --phase "planning_complete" --plan-path <path>
  prog set-workflow-state --phase "execution" --plan-path <path>
  所有审查验证通过后:
  prog set-workflow-state --phase "execution_complete" \
    --next-action "verify_and_complete"
```

**重要兼容规则:**
- 在 `/prog next` 流程中，"代码 + 验证就绪" 即为实现结束
- **不运行** 分支收尾动作
- Feature 完成由 `/prog done` 独立处理

**涉及的质量门禁 (共 4 层):**
1. TDD (内嵌在 subagent-driven-development)
2. Spec Review (内嵌在 subagent-driven-development)
3. Code Review (superpowers:requesting-code-review)
4. Verification (superpowers:verification-before-completion)

### 2.2.4 路径 C: Complex (26-40 分)

**委托 skill**: `progress-tracker:feature-implement-complex` (model: opus, user-invocable: false)

**完整步骤：**

```
Step 1: 验证复杂度 bucket == complex
Step 2: 显示 complex-mode banner + 理由
Step 3: 统一预检:
        prog git-auto-preflight --json
        · REQUIRE_WORKTREE →
          Skill("superpowers:using-git-worktrees",
                args="Set up isolated workspace for feature-<id>")
        · DELEGATE_GIT_AUTO →
          Skill("progress-tracker:git-auto",
                args="Resolve workspace/git preflight blockers")
        · ALLOW_IN_PLACE → 继续
Step 4: Skill("superpowers:brainstorming",
               args="<name>: architecture and approach")
        若有 architecture.md → 包含 Execution Constraints
Step 5: prog set-workflow-state \
          --phase "design_complete" \
          --next-action "planning"
Step 6: Skill("superpowers:writing-plans",
               args="<name>: create implementation plan\n
                     Architecture constraints:\n- <CONSTRAINT-...>")
Step 6.5: prog set-sprint-contract \
            --feature-id <id> \
            --scope "..." --done-criteria "..." --test-plan "..."
Step 7: prog set-workflow-state \
          --phase "planning_complete" \
          --plan-path "<plan_path>" \
          --next-action "execution"
Step 8: Skill("superpowers:subagent-driven-development",
               args="plan:<plan_path>")
Step 9: Skill("superpowers:requesting-code-review",
               args="Review complex feature: <name>")
        Skill("superpowers:verification-before-completion",
               args="Verify complex feature evidence for <name>")
Step 10: prog set-workflow-state \
           --phase "execution_complete" \
           --next-action "verify_and_complete"
         prog set-feature-ai-metrics <id> \
           --complexity-score <score> \
           --selected-model opus \
           --workflow-path full_design_plan_execute
Step 11: 提示用户运行 /prog done
```

**涉及的质量门禁 (共 4 层 + 额外 brainstorming):**
1. 头脑风暴 (superpowers:brainstorming) — 架构探索
2. TDD (内嵌在 subagent-driven-development)
3. Spec Review (内嵌在 subagent-driven-development)
4. Code Review (superpowers:requesting-code-review)
5. Verification (superpowers:verification-before-completion)

### 2.2.5 兜底规则

若 simple 或 complex 路径委托失败 → 回退到 standard coordinator 路径，用 sonnet 继续，在 `next_action` 中记录回退。

---

## 2.3 功能完成阶段 `/prog done`

**触发 skill**: `progress-tracker:feature-complete` (model: sonnet)

### 完整执行流程

```
用户输入 /prog done
        │
        ▼
┌──────────────────────────────────────┐
│  Inline Context Fast Path            │
│  若有 Feature:/Phase:/Plan: 等行     │
│  → 跳过 Step 1-2                    │
│  → 直接进入 Step 3                  │
│  → 验证 Branch 匹配，必要时自动切换  │
└──────────────────────────────────────┘
        │ (无 inline context)
        ▼
┌──────────────────────────────────────┐
│  Step 1: 加载活跃 Feature            │
│  - 读 progress.json                 │
│  - 定位 current_feature_id          │
│  - 无活跃 feature → 引导 /prog next │
│  - 已完成 → 显示状态，停止           │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 2: 验证工作流状态              │
│  - 检查顶层 workflow_state.phase    │
│  - 必须是 execution_complete        │
│  - 检查上下文对齐 (branch/worktree) │
│  - 不对齐 → 自动切换或停止          │
│  - 若不满足 → 输出诊断信息:         │
│    · 当前 phase 值                  │
│    · 缺少什么                        │
│    · 上下文不匹配详情                │
│    · 如何继续                        │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 3: 验证计划合约                │
│  prog validate-plan                 │
│  - 检查 plan_path 存在且有效         │
│  - 验证计划结构 (Tasks + 其他必需项) │
│  - 失败 → 要求重建计划               │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 4: 运行验收验证                │
│  - 遍历 feature.test_steps          │
│  - 执行基于命令的检查                │
│  - 收集每个步骤的 PASS/FAIL 证据    │
│  - 手动检查收集显式证据              │
│  - 调用:                            │
│    Skill("superpowers:              │
│           verification-before-      │
│           completion",              │
│           args="Verify acceptance   │
│                 evidence for        │
│                 feature <id>")      │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 4.5: 评估器门禁 (ADR-009)     │
│  ┌────────────────────────────────┐ │
│  │ 启动全新的独立 subagent:        │ │
│  │ Agent(                          │ │
│  │   subagent_type=                │ │
│  │   "superpowers:code-reviewer",  │ │
│  │   prompt="Run evaluator_gate.   │ │
│  │     assess() for feature <id>." │ │
│  │ )                               │ │
│  │                                 │ │
│  │ 隔离要求: generator/evaluator   │ │
│  │ 必须在不同的 context 中运行     │ │
│  └────────────────────────────────┘ │
│                                     │
│  三种结果:                          │
│  · status=pass → 继续 Step 5       │
│  · status=retry → 修复阻断缺陷     │
│  · status=required_reviews →       │
│    升级到人工审查通道               │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Step 5: 处理验证结果                │
│                                      │
│  ┌─ 通过路径 ─────────────────────┐ │
│  │ 5.1: 确认所有检查通过           │ │
│  │ 5.2: 最终代码审查               │ │
│  │   Skill("superpowers:           │ │
│  │     requesting-code-review",    │ │
│  │     args="Final review before   │ │
│  │       marking feature <id>")    │ │
│  │ 5.3: 确保无未解决的严重问题     │ │
│  │ 5.4: Git 自动收尾:              │ │
│  │   Skill("progress-tracker:      │ │
│  │     git-auto",                  │ │
│  │     args="git auto done —       │ │
│  │       feature <id> closeout")   │ │
│  │   → 解析 Execution Result Block │ │
│  │   → 提取 CommitHash             │ │
│  │ 5.5: prog complete <id>         │ │
│  │        --commit <CommitHash>    │ │
│  │   → 移动 plan 到 archive/       │ │
│  │   → 重命名为 feature-N-*.md     │ │
│  │ 5.6: prog memory append         │ │
│  │        --payload-json '<...>'   │ │
│  │   → 非阻塞，失败仅警告          │ │
│  │ 5.7: prog complete-feature-     │ │
│  │        ai-metrics <id>          │ │
│  │ 5.8: prog clear-workflow-state  │ │
│  │ 5.9: 显示摘要 + 下一个 feature  │ │
│  │       预览 + Handoff Block      │ │
│  │ 5.10: 合并优先收尾策略          │ │
│  │   → 默认 commit_push_pr_merge   │ │
│  │   → git-auto 是合并门禁的唯一   │ │
│  │     权威                         │ │
│  └────────────────────────────────┘ │
│                                      │
│  ┌─ 失败路径 ─────────────────────┐ │
│  │ - feature 保持在 in_progress   │ │
│  │ - 输出失败检查项和症状          │ │
│  │ - 推荐 /prog-fix "<issue>"     │ │
│  └────────────────────────────────┘ │
│                                      │
│  Step 6: 可选 — 技术债务捕获        │
│  prog add-bug \                     │
│    --description "<债务项>" \       │
│    --status pending_investigation \ │
│    --priority medium \              │
│    --category technical_debt        │
└──────────────────────────────────────┘
```

### `/prog done` Handoff Block 格式

**有待处理 feature 时:**
```text
/progress-tracker:prog-next

Project: <done>/<total> features done | F<id> "<name>" ✓ just completed
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-selects and starts next pending feature.
```

**全部完成时:**
输出项目完成摘要，无需 handoff block。

---

## 2.4 Bug 修复流程 `/prog-fix`

**触发 skill**: `progress-tracker:bug-fix` (model: sonnet)

### Bug 生命周期

```
pending_investigation → investigating → confirmed → fixing → fixed
                      ↓
                   false_positive
```

### 场景 1: 无参数 — 显示 Bug 待办

```
/prog-fix (无参数)
        │
        ▼
读取 progress.json → bugs[]
        │
        ▼
按优先级分组显示:
  🔴 高优先级 → 待深入调查 / 已确认
  🟡 中优先级
  🟢 低优先级
        │
        ▼
提供选项: 1) 修复最高优先级 2) 按 ID 选择 3) 报告新 bug
```

### 场景 2: 报告新 Bug — 三阶段流程

```
用户: /prog-fix "<描述>"
        │
        ▼
┌──────────────────────────────────────┐
│  Phase 1: 快速验证 (<30 秒)          │
│  Step 1: Grep 搜索相关代码          │
│  Step 2: 对比已有 bugs[]            │
│  Step 3: 评估可复现性               │
│  输出: 相关代码、已知相似问题、可复现│
│        性评级 + 初步评估             │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│  Phase 2: 用户确认                   │
│  选项:                               │
│  [1] 排入计划 (推荐)                 │
│  [2] 立即调查 (系统调试+TDD)        │
│  [3] 取消                            │
└──────────────────────────────────────┘
        │
   [1]  │       [2]  │       [3] 退出
        ▼              ▼
┌──────────────────┐  ┌──────────────────────┐
│  Phase 3: 智能排期│  │  Skill("superpowers: │
│  - 影响评估       │  │    systematic-        │
│  - 关联 feature   │  │    debugging",        │
│  - 优先级计算     │  │    args="<描述>")     │
│  - 插入点建议     │  │  → 确认后 TDD 修复   │
│  - 用户确认       │  │  → code-review       │
│  - 更新 JSON/MD   │  └──────────────────────┘
└──────────────────┘
```

### 场景 3: 修复已记录的 Bug

```
按 bug 当前状态分支:
  pending_investigation → systematic-debugging
  investigating         → 续跑调查
  confirmed             → TDD (已知根因) → fix
  fixing                → 续跑修复

修复流程:
  Skill("superpowers:systematic-debugging", args="<bug>")
  → prog update-bug --bug-id "BUG-XXX" --status "confirmed"
  → Skill("superpowers:test-driven-development",
           args="Fix <bug>: <description>")
  → prog update-bug --bug-id "BUG-XXX" --status "fixed"
  → Skill("progress-tracker:git-auto", args="auto")
  → prog update-bug --bug-id "BUG-XXX"
      --fix-summary "Fix applied (commit: <hash>)"
  → Skill("superpowers:requesting-code-review",
           args="Verify bug fix for: <bug>")
```

---

## 2.5 管理操作

### 2.5.1 `/prog undo` — 撤销最近 feature

**触发 skill**: `progress-tracker:progress-management`

```
Step 1: 安全检查
        git status --porcelain
        → 不干净 → STOP，提示先提交或 stash
Step 2: 执行撤销
        prog undo
        → git revert (保留历史，非 git reset)
        → 状态回滚
Step 3: 报告结果 + 输出 Handoff Block
```

### 2.5.2 `/prog reset` — 重置项目进度

```
Step 1: 确认意图（除非用户带了 force/yes）
Step 2: prog reset --force
        → 归档旧快照
        → 清空 progress.json / progress.md / checkpoints.json
Step 3: 报告 + 输出 Handoff Block (引导 /prog init)
```

---

## 2.6 恢复与断点续跑

### 2.6.1 Inline Context Fast Path（核心机制）

当用户粘贴 Handoff Block 到新 session 时，skill 解析 inline context 行，跳过大部分初始步骤直接路由到正确阶段。

**Inline context 字段完整列表:**

| 字段 | 含义 | 示例 |
|------|------|------|
| `Feature:` | feature ID 和名称 | `F7 "Enforce PROG command docs..."` |
| `Phase:` | workflow_state.phase | `planning:approved` |
| `Plan:` | plan 文件路径 | `docs/plans/2026-04-28-f7-docs-parity.md` |
| `PlanSummary:` | 计划摘要（分号分隔） | `生成;校验;同步` |
| `Tasks:` | 完成/总数 | `2/5 done` |
| `Next:` | 下一个 task ID 和标题 | `T3 — 验证同步` |
| `Branch:` | git 分支名 | `feat/f7-docs-parity` |
| `Worktree:` | worktree 路径 | `/tmp/worktrees/...` |
| `Bucket:` | 复杂度分桶 | `standard` |
| `Questions:` | 待澄清问题（\| 分隔） | `格式A还是B?\|需要CI吗?` |
| `ProjectRoot:` | 项目根绝对路径 | `/Users/.../Claude-Plugins` |
| `Project:` | 项目名 + 进度 | `MyApp \| 3/8 completed` |

### 2.6.2 Resume Matrix (session-playbook.md)

| 检测到的状态 | 条件 | 动作 |
|-------------|------|------|
| 准备完成 | `phase=execution_complete` | 引导到 `/prog done` |
| 执行中途 | `phase=execution` 且 plan 有效 | 从下一个未完成 task 续跑 |
| 计划丢失 | `phase in {planning_complete, execution}` 且 plan 无效 | 重建 plan，然后继续 |
| 锁不一致 | `current_feature_id` 指向不存在的 feature | 先跑恢复流程 |
| `planning:clarifying` | Questions 存在 | 重新提问，回答后进入 draft |
| `planning:draft` | Plan + PlanSummary 存在 | 显示摘要等审批，不重跑 brainstorming |
| `planning:approved` | Phase=planning:approved | 读取 bucket 直接路由执行 |

### 2.6.3 计划重建触发条件

**仅在以下三者同时满足时重建:**
1. `workflow_state.plan_path` 已设置
2. plan 文件不存在 或 `validate-plan` 返回非零
3. phase 是 `planning_complete` 或 `execution`

**不重建的情况:**
- plan_path 不存在因为全新启动（正常）
- 用户显式指定了 plan 路径（信任用户）
- `execution_context` 匹配当前 branch/worktree（正常续跑）

### 2.6.4 规划子阶段恢复规则

- `planning:draft` 且 plan 文件丢失 → 用 PlanSummary 重建，不重跑 brainstorming
- `planning:approved` 新 session → 从 `feature.ai_metrics.complexity_bucket` 读 bucket 路由
- 一旦到达 `planning:draft`，绝不回退到 `planning:clarifying`，始终向前推进

---

## 2.7 完整 CLI 命令参考

### 项目初始化
```bash
prog init "<project_name>"                          # 初始化进度跟踪
prog add-feature "<name>" "<step1>" "<step2>" ...   # 添加 feature
```

### Feature 生命周期
```bash
prog next-feature --json                            # 获取下一个待处理 feature
prog set-current <feature_id>                       # 设为当前活跃 feature (自动进入 developing)
prog complete <feature_id> --commit <hash>          # 标记完成 + 归档文档
prog clear-workflow-state                           # 清除工作流状态
```

### 工作流状态
```bash
prog set-workflow-state \
  --phase <phase> \                                 # planning / planning:clarifying /
                                                    # planning:draft / planning:approved /
                                                    # planning_complete / execution /
                                                    # execution_complete
  --plan-path <path> \                              # plan 文件路径
  --next-action "<描述>"                            # 下一步动作

prog update-workflow-task <task_id> completed       # 标记 task 完成
prog validate-plan                                  # 验证 plan 文件结构
prog auto-checkpoint                                # 创建轻量检查点
```

### AI 指标
```bash
prog set-feature-ai-metrics <feature_id> \
  --complexity-score <0-40> \
  --selected-model <haiku|sonnet|opus> \
  --workflow-path <direct_tdd|plan_execute|full_design_plan_execute>

prog complete-feature-ai-metrics <feature_id>       # 完成时固化指标
```

### Sprint Contract
```bash
prog set-sprint-contract \
  --feature-id <id> \
  --scope "<范围描述>" \
  --done-criteria "<条件1>" "<条件2>" ... \
  --test-plan "<计划1>" "<计划2>" ...
```

### Git 集成
```bash
prog git-sync-check                                  # Git 同步状态检查
prog git-auto-preflight --json                       # 统一预检
```

### Bug 管理
```bash
prog add-bug \
  --description "<描述>" \
  --status pending_investigation \
  --priority <high|medium|low> \
  --category <bug|technical_debt>

prog update-bug --bug-id "BUG-XXX" --status "confirmed"
prog list-bugs
prog remove-bug "BUG-XXX"
```

### 内存/记忆
```bash
prog memory read                                     # 读取项目记忆
prog memory append --payload-json '<json>'           # 追加能力记忆
```

### 管理与恢复
```bash
prog undo                                            # 撤销最近 feature
prog reset --force                                   # 重置进度
prog reconcile-state                                 # 从 audit.log 恢复状态
prog install-git-hooks                               # 安装 Git hooks
prog list-archives                                   # 列出归档快照
prog restore-archive <name>                          # 恢复归档
```

### Monorepo 父级
```bash
prog prioritize <project_code>                       # 将子项目移到队列首位
```

---

## 2.8 Skill 调用关系图

```
                         progress-tracker skills              superpowers skills
                         ══════════════════════              ═════════════════
                                │                                    │
        ┌───────────────────────┼────────────────────────────┬───────┴────────────┬──────────────────┐
        │                       │                            │                    │                  │
        ▼                       ▼                            ▼                    ▼                  ▼
feature-breakdown       feature-implement            brainstorming          writing-plans      test-driven-
(opus)                  (sonnet, coordinator)        (opus, 灵活)          (flexible)         development
        │                       │                                                    (rigid)
        │                       │                            │                    │                  │
        │              ┌────────┼────────┐                   │                    │                  │
        │              │        │        │                   │                    │                  │
        │              ▼        │        ▼                   │                    │                  │
        │   feature-implement   │  feature-implement         │                    │                  │
        │   -simple (haiku)     │  -complex (opus)           │                    │                  │
        │        │              │        │                   │                    │                  │
        │        │              │        │                   │                    │                  │
        │        └──────────────┼────────┘                   │                    │                  │
        │                       │                            │                    │                  │
        │                       │ 都调用这些 superpowers:     │                    │                  │
        │                       ├────────────────────────────┤                    │                  │
        │                       │ test-driven-development ────────────────────────────────────────────
        │                       │ requesting-code-review ─────────────────────────────────────────────
        │                       │ verification-before-     │                    │                  │
        │                       │   completion ──────────────────────────────────────────────────────
        │                       │                            │                    │                  │
        │                       │ standard/complex 额外:     │                    │                  │
        │                       │ brainstorming ────────────┘                    │                  │
        │                       │ writing-plans ─────────────────────────────────┘                  │
        │                       │ subagent-driven-development                                       │
        │                       │                            │                                       │
        │                       │                            │                                       │
        ├───────────────────────┤                            │                                       │
        │                       │                            │                                       │
        ▼                       ▼                            │                                       │
architectural-planning   feature-complete                    │                                       │
(opus)                   (sonnet)                            │                                       │
        │                       │                            │                                       │
        │                       │ 调用:                       │                                       │
        │                       │ verification-before-completion ───────────────────────────────────
        │                       │ requesting-code-review ───────────────────────────────────────────
        │                       │                            │                                       │
        │                       │ 启动独立 subagent:          │                                       │
        │                       │ Agent(superpowers:code-reviewer)                                  │
        │                       │                            │                                       │
        ├───────────────────────┤                            │                                       │
        │                       │                            │                                       │
        ▼                       ▼                            │                                       │
progress-management       bug-fix                            │                                       │
(sonnet)                  (sonnet)                           │                                       │
                                   │                         │                                       │
                                   │ 调用:                    │                                       │
                                   │ systematic-debugging ───────────────────────────────────────────
                                   │ test-driven-development ────────────────────────────────────────
                                   │ requesting-code-review ─────────────────────────────────────────
                                   │ progress-tracker:git-auto                                       │
```

---

## 2.9 progress.json 数据结构

### 顶层结构
```jsonc
{
  "schema_version": "2.1",
  "project_name": "string",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "features": [ /* Feature[] */ ],
  "current_feature_id": null | int,
  "tracker_role": "parent" | "child",
  "project_code": "ROOT" | "PT" | ...,
  "routing_queue": ["ROOT", "PT", ...],
  "linked_projects": [ /* LinkedProject[] */ ],
  "linked_snapshot": { /* snapshot */ },
  "active_routes": [ /* Route[] */ ],
  "updates": [],
  "retrospectives": [],
  "runtime_context": { /* RuntimeContext */ },
  "bugs": [ /* Bug[] */ ],
  "current_bug_id": null | string,
  "parent_project_root": null | string,
  "workflow_state": {                     // 顶层！不要读 features[n].workflow_state
    "phase": "planning:clarifying" | "planning:draft" | "planning:approved"
           | "planning" | "planning_complete" | "execution" | "execution_complete",
    "plan_path": null | string,
    "completed_tasks": [1, 2, ...],       // 已完成 task ID 列表
    "current_task": int,                   // 当前 task ID
    "total_tasks": int,                    // task 总数
    "next_action": null | string,          // 人类可读的下一步动作
    "execution_context": {                 // 运行时上下文
      "branch": "string",
      "worktree_path": null | "string"
    },
    "updated_at": "ISO8601"
  }
}
```

### Feature 对象
```jsonc
{
  "id": int,
  "name": "string",
  "test_steps": ["string", ...],
  "completed": bool,
  "deferred": bool,
  "defer_reason": null | string,
  "deferred_at": null | string,
  "defer_group": null | string,
  "owners": { "architecture": null, "coding": null, "testing": null },
  "lifecycle_state": "approved" | "implementing" | "archived",
  "requirement_ids": ["REQ-001", ...],
  "change_spec": {
    "why": "string",
    "in_scope": ["string", ...],
    "out_of_scope": ["string", ...],
    "risks": ["string", ...],
    "categories": ["cli" | "docs" | ..., ...]
  },
  "acceptance_scenarios": ["Scenario: ...", ...],
  "quality_gates": {
    "evaluator": {
      "status": "pending" | "pass" | "retry" | "required_reviews",
      "score": null | int (0-100),
      "defects": [{ "id": "string", "severity": "string", "description": "string" }],
      "last_run_at": null | "ISO8601",
      "evaluator_model": null | "string"
    },
    "reviews": {
      "required": ["docs", "eng", "qa", "architecture", "devex", ...],
      "passed": ["docs", ...],
      "pending": ["eng", ...]
    },
    "ship_check": {
      "status": "pending" | "pass" | "fail",
      "failures": [],
      "last_run_at": null | "ISO8601"
    }
  },
  "sprint_contract": {
    "scope": "string",
    "done_criteria": ["string", ...],
    "test_plan": ["string", ...],
    "accepted_by": null | string,
    "accepted_at": null | string
  },
  "handoff": {
    "from_phase": null | string,
    "to_phase": null | string,
    "artifact_path": null | string,
    "created_at": null | string
  },
  "ai_metrics": {
    "complexity_score": int (0-40),
    "complexity_bucket": "simple" | "standard" | "complex",
    "selected_model": "haiku" | "sonnet" | "opus",
    "workflow_path": "direct_tdd" | "plan_execute" | "full_design_plan_execute",
    "started_at": "ISO8601",
    "finished_at": "ISO8601",
    "duration_seconds": int
  },
  "development_stage": "developing" | "completed",
  "started_at": "ISO8601",
  "completed_at": null | "ISO8601",
  "integration_status": "merged_and_cleaned",
  "finish_state_resolved_at": null | "ISO8601",
  "commit_hash": null | "string",
  "plan_path": null | "string",
  "archive_info": {
    "archived_at": "ISO8601",
    "files_moved": int,
    "files": [{ "from": "string", "to": "string" }]
  }
}
```

### Bug 对象
```jsonc
{
  "id": "BUG-001",
  "description": "string",
  "status": "pending_investigation" | "investigating" | "confirmed"
          | "fixing" | "fixed" | "false_positive",
  "priority": "high" | "medium" | "low",
  "category": "bug" | "technical_debt",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "root_cause": null | "string",
  "investigation": {
    "root_cause": "string",
    "confirmed_at": "ISO8601"
  },
  "quick_verification": {}
}
```

---

## 2.10 质量门禁体系

### overview

```
quality_gates
├── evaluator:      AI 驱动的自动化质量评估
│   (status: pending | pass | retry | required_reviews)
├── reviews:        人工/AI 审查通道
│   (required[], passed[], pending[])
└── ship_check:     发布前最终检查
    (status: pending | pass | fail)
```

### 四层质量保障 (来自 superpowers-integration.md)

| 层 | 工具 | 时机 | 检查内容 |
|----|------|------|---------|
| 1. TDD | superpowers:test-driven-development | 编码期间 | 单元级正确性 |
| 2. Spec Review | subagent-driven-development 内嵌 | 每个 task 后 | 匹配实现计划 |
| 3. Code Review | superpowers:requesting-code-review | spec 通过后 | 模式、可维护性 |
| 4. Acceptance | `/prog done` 验收测试 | feature 完成时 | 端到端功能 |

### Evaluator Gate 规则 (ADR-009)

- **隔离要求**: Generator (编写代码) 和 Evaluator (评估质量) 必须在不同的 subagent context 中运行
- `status == "pass"` → 继续
- `status == "retry"` → 修复阻断缺陷，重跑评估器，不调 `prog done`
- `status == "required_reviews"` → 升级到人工审查通道，不调 `prog done`
- 若调 `prog done` 时 `evaluator.status != "pass"`，CLI 退出码 6 并阻止归档

### 合并优先收尾策略

- `/prog done` 默认 `commit_push_pr_merge`
- `git-auto` 是合并门禁的唯一权威
- 不在正常的 `/prog done` 流程中自动调用 `finishing-a-development-branch`
- 仅当用户显式请求手动集成路径时才调用

---

## 附录: 关键文件路径

```
plugins/progress-tracker/
├── prog                          # CLI 入口 (Bash 脚本)
├── prog.py                       # Python CLI 调度
├── workflow.md                   # 本文件
├── STANDARDS.md                  # 编码标准
├── skills/
│   ├── feature-breakdown/        # /prog init
│   ├── feature-implement/        # /prog next (coordinator)
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── complexity-assessment.md
│   │       ├── superpowers-integration.md
│   │       └── session-playbook.md
│   ├── feature-implement-simple/ # simple 路径委托
│   ├── feature-implement-complex/# complex 路径委托
│   ├── feature-complete/         # /prog done
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── verification-playbook.md
│   ├── bug-fix/                  # /prog-fix
│   ├── progress-management/      # /prog undo / /prog reset
│   ├── architectural-planning/   # /prog plan
│   ├── progress-status/          # /prog (面板)
│   ├── progress-recovery/        # 恢复流程
│   ├── git-auto/                 # Git 自动化
│   ├── testing-standards/        # 测试标准
│   ├── prog-log/                 # 日志
│   ├── prog-note/                # 笔记
│   └── ui-launcher/              # UI 启动器
├── hooks/
│   └── scripts/
│       ├── progress_manager.py   # 核心状态管理 (~2000+ 行)
│       ├── wf_state_machine.py   # 工作流状态机 (纯函数)
│       ├── sprint_ledger.py      # Sprint 产物账本
│       ├── progress_prompt_builders.py # Handoff prompt 构建器
│       └── progress_ui_server.py # UI 服务
└── tests/
    ├── test_progress_manager.py
    ├── test_workflow_state.py
    ├── test_wf_state_machine.py
    ├── test_sprint_ledger.py
    ├── test_cmd_done_cleanup_integration.py
    └── ...
```
