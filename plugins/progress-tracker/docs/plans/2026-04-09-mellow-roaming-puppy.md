# Progress Tracker: Hybrid Phase-1 Full Plugin Update Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成整个 progress-tracker 插件的 Hybrid Phase-1 大更新——在现有 `progress_manager.py` 架构之上落地 generator/evaluator 分离、review 分流、ship 前统一门禁、sprint 契约 + handoff artifact 长跑可恢复四大能力，清理 `/prog-start` 残留语义，并以 **FSM kernel + hook 驱动的 Auto-Driver**（PR-7）把 WF 从"用户每步发指令"升级为"feature 从 approved 一路自动跑到 archived"，对应 GSD V1→V2 那次"主调度从 LLM 移到程序"的根本性更新。

**Architecture:** 保持 `progress_manager.py` 作为状态内核与事实总线（ADR-001），但把“规则判定”“证据产出”“副作用执行”三层明确拆开：`evaluator_gate.py` / `review_router.py` / `ship_check.py` 只负责产出 gate evidence，`wf_state_machine.py` 只负责纯规则判定，`wf_auto_driver.py` 只负责基于判定结果做 hook gate / dispatch 建议，所有持久化仍统一经过 `progress_transaction()` + `_atomic_write_text()`。Schema 保持 `2.1` 并继续沿用 `sprint_contract` / `quality_gates` / `handoff`；`pending` 一类可推导字段按“读模型优先、存储兼容”处理。PR-7 的 FSM kernel 不再以 `compute_next_action(feature)` 为目标形态，而是以 `compute_next_action(rule_context)` 为准，避免只看单个 feature 而丢失 workflow phase、触发源、command intent、active feature 等判定条件。

**Tech Stack:** Python 3（无新增外部依赖）、pytest、argparse CLI（延续现有 `prog` 入口）、Claude Code subagent isolation 作为 generator/evaluator context 隔离机制、Claude Code hooks 作为 WF auto-driver 调度入口。

**Source of Truth:** `docs/progress-tracker/architecture/architecture.md` 第 813-856 行 "Enhancement Blueprint: Hybrid GSD + gstack (2026-04-08)"；所有 ADR 引用均以该文件为准。

**gstack 参考源：** https://github.com/garrytan/gstack （Garry Tan 的 gstack），真实 workflow 为 `Think → Plan → Build → Review → Test → Ship → Reflect`，后文 §gstack 借鉴映射 给出精准对齐。

---

## 2026-04-17 架构审查结论（覆盖性增补）

> 本节是对原计划的架构校准。若与后文分 PR 实施细节冲突，以本节为准。

### 当前仓库状态校准

- `progress_manager.py` 当前已是 `schema 2.1`，不是本计划前文假设的 `2.0`。
- `quality_gates` / `sprint_contract` / `handoff` 默认注入与 `test_schema_2_1_migration.py` 已存在。
- `evaluator_gate.py` 与 `_store_evaluator_result()` 已落地；`review_router.py` / `ship_check.py` / `sprint_ledger.py` / `wf_state_machine.py` / `wf_auto_driver.py` 仍未落地。
- 因此，本计划后续应被视为“从 evaluator gate 已落地状态继续演进”的架构方案，而不是从零开始的七连 PR 剧本。

### 主要架构问题

1. **规则、状态、执行混层**
   - 原方案默认每个模块都可直接写 `progress.json`，会把 `progress_manager.py` 退化成共享事务工具，而不是唯一状态内核。
2. **FSM 输入过窄**
   - `compute_next_action(feature)` 只看 feature 快照，不足以判断 hook source、当前 command、workflow phase、active feature、一致性异常等真正的调度前提。
3. **`quality_gates.reviews` 过度存储派生态**
   - `required` / `passed` / `pending` 三份数据同时落盘，天然存在漂移风险。`pending` 应视为从规则与 evidence 推导出的读模型，而不是事实源。
4. **hook 自动推进缺少幂等约束**
   - 只靠 `additionalContext` 注入 “dispatch X” 容易重复派发 evaluator/review 子任务，也无法稳定区分“建议动作”和“已发出未完成动作”。
5. **gate verdict 与 orchestration intent 耦合**
   - `required_reviews` 既像 evaluator 结论，又像工作流下一步动作。规则引擎应把“事实结论”和“建议执行动作”拆成两个层次。

### 优化后的目标架构

#### 1. Facts Layer: 只有 `progress_manager.py` 持久化

- `progress_manager.py` 继续作为唯一事实写入口。
- 其他模块返回结构化结果，由 `progress_manager.py` 统一写入 feature、workflow_state、audit.log。
- 允许模块内有 `to_payload()` / `to_event()`，不允许模块自己决定生命周期推进。

#### 2. Evidence Layer: 评估模块只产出证据

- `evaluator_gate.py` 输出 evaluator evidence：`status`、`score`、`defects[]`、`evaluator_model`、`last_run_at`。
- `review_router.py` 输出 required lanes 与 review evidence 规范，但不直接驱动状态迁移。
- `ship_check.py` 输出 typed check results；`pass/fail` 是聚合结果，不是唯一有效信息。
- 这三层模块都不直接计算“下一步该 dispatch 谁”，它们只报告事实。
- `progress_manager.py` 应补一个统一的 `_collect_feature_signals(feature_id)` 入口，集中采集 coverage、test results、lint/docs drift 等信号，避免 evaluator 与 ship-check 各自读取不同事实源。

#### 3. Rule Layer: `wf_state_machine.py` 做纯判定

- 目标签名：

```python
compute_next_action(rule_context) -> WorkflowDecision
```

- `rule_context` 至少包含：
  - `feature`
  - `workflow_state`
  - `current_feature_id`
  - `trigger_source` (`pre_tool_use` / `stop` / `user_prompt_submit` / `cli_drive`)
  - `requested_command`
  - `pending_action`
- `WorkflowDecision` 至少区分：
  - `verdict`: `allow` | `block` | `nudge`
  - `action_kind`: `request_sprint_contract` | `dispatch_evaluator` | `dispatch_review_lane` | `run_ship_check` | `complete_done` | `await_user` | `noop`
  - `reason`
  - `idempotency_key`

#### 4. Orchestration Layer: `wf_auto_driver.py` 只解释 decision

- PreToolUse: 只负责 block/allow，不做隐式状态变更。
- Stop/UserPromptSubmit: 只负责发出下一步建议，且必须检查 `pending_action.idempotency_key`，避免重复建议同一动作。
- `wf_auto_driver.py` 不直接“相信” LLM 会完成动作；它只根据事实源检查动作是否已经完成，未完成才再次提示。
- `wf_auto_driver.py` 入口必须全局 `try/except` 并采用 fail-open：若 driver 自身崩溃，记录 `driver_crashed` 审计事件后放行工具，而不是卡死整个 CLI / hook 链。

### 数据契约优化

- `quality_gates.evaluator`
  - 保留当前结构。
  - `status` 只表达 evaluator 结论，不隐含 review dispatch 语义。
- `quality_gates.reviews`
  - 兼容保留 `required/passed/pending`。
  - 但引擎层把 `pending` 视为派生字段，读时由 `required - passed` 重建；后续如需扩展，优先新增 `evidence[]` 而不是继续堆派生列表。
- `quality_gates.ship_check`
  - `failures[]` 应逐步演进成 typed `checks[]`，每项含 `check_id` / `status` / `detail` / `evidence_ref`。
- `workflow_state`
  - 应新增 `pending_action` 作为幂等锚点：

```python
"pending_action": {
  "idempotency_key": None,
  "kind": None,
  "lane": None,
  "issued_at": None,
  "source": None
}
```

- `pending_action.idempotency_key`
  - 不应只由 `feature_id + lifecycle_state + quality_gate_status` 组成。
  - 推荐至少包含：`feature_id`、`action_kind`、`lane`、`trigger_source`、与当前 gate 直接相关的 evidence digest。
  - 目标是“同一事实状态下重复触发，得到同一 decision；事实一旦变化，自动生成新 key”。

### 设计约束

- 规则函数必须纯函数，不做 IO，不读写文件，不直接调 subagent。
- 任何 lifecycle 推进必须由 `progress_manager.py` 根据 evidence + decision 显式落盘。
- 任一 gate 模块只能写“我看到了什么”，不能写“接下来必须调用谁”。
- hook 必须幂等；同一 `idempotency_key` 未消费前不能重复派发相同动作。
- 对 `pending`、`next_action` 这类派生态，优先即时重建，避免把缓存态写成事实源。
- Stop hook 默认应保持静默；仅在 gate 未通过、状态刚变化、或存在明确下一步动作时才注入 `additionalContext`。
- 自动推进的主保护应是 `pending_action` 幂等与事实校验；`trace_id` / `depth` 仅作为辅助熔断，限制单个 feature 在一次自动链路中的连续跳段次数。
- `evaluator_gate` 需要显式检查隔离上下文；若检测到 evaluator 与当前 implementation 使用同类上下文，应至少输出强警告并写审计事件。

### 性能与鲁棒性说明

- **Schema lazy migration**
  - 不建议仅凭 `schema_version == CURRENT_SCHEMA_VERSION` 就直接跳过 `_apply_schema_defaults()`。
  - 当前 backfill 还承担“深度补默认值”和“修复部分缺字段对象”的职责；只看版本号会漏掉手工编辑或旧 fixture。
  - 可接受的优化方向是：增加 cheap-path 检查，仅在结构完整时快速返回；否则仍进入深度补全。

- **Sprint ledger 读路径**
  - `sprint_ledger.jsonl` 继续作为 append-only 审计源。
  - `feature.handoff.artifact_path` 应明确视为 latest artifact 一级缓存；常规 resume 读取这里，只有回溯历史或缓存缺失时才扫描 ledger。

- **UI 渲染**
  - `quality_gates` 紧凑矩阵展示有价值，例如 `[E:✅] [R:⏳] [S:❌]`。
  - 但优先级低于 rule engine、hook 幂等、signal collection；建议作为 PR-5 之后的跟进项，而不是阻塞内核落地。

### 配置扩展策略

- `review_router` 第一阶段仍以代码内显式规则表为主，先把默认 lane discipline 跑稳。
- 项目级 override 值得支持，但应以“可选配置覆盖”方式进入后续阶段，而不是在 PR-4 初版就把路由规则外置到任意 JSON 配置。

### 对后续 PR 的直接影响

- PR-4 `review_router` 可以继续存在，但其职责应收窄为“lane rules + review evidence helper”，不是 workflow driver。
- PR-5 `ship_check` 应先产出 typed check evidence，再由 rule engine 决定是否阻断 `/prog-done`。
- PR-7 的核心不再是“让 LLM 看起来会自动跑完整流程”，而是“让程序稳定判断当前唯一允许的下一步，并保持幂等”。
- PR-7 实现时必须优先完成三项保护：fail-open hook、`pending_action` 幂等锚点、自动链路熔断。

---

## Context

### 问题陈述

当前 progress-tracker 插件已经具备：
- `progress_manager.py` 状态内核（当前已增长，本文不再依赖固定行数估算），含 `progress_transaction()` 原子写、POSIX `fcntl` 锁、`audit.log` append-only 审计、`_apply_schema_defaults()` 向下兼容（schema 2.1）。
- `lifecycle_state_machine.py` 状态转换门。
- `feature-implement`、`feature-complete` 等 skills 覆盖 `/prog-next`、`/prog-done` 全流程。
- `validate_feature_readiness` 只读前置门禁。

但缺失 architecture.md Enhancement Blueprint 明确列出的关键能力：

1. **generator/evaluator 不分离**——当前 `/prog-done` 的验收检查由生成方（feature-implement 同一 subagent 上下文）自判，违反 Anthropic harness `planner/generator/evaluator` 三角中“评估必须独立”的核心纪律。
2. **无 review 分流**——所有 feature 走同一套检查，没有按变更类型选择 review lane。
3. **无统一 ship 门禁**——归档前没有一次性跑完测试覆盖、回归、文档一致性校验。
4. **无 sprint 契约与 handoff artifact**——长跑会话中断后只能依赖对话历史恢复，没有持久化的“本 sprint 的 done 定义在此文件”。
5. **`/prog-start` 语义残留**——`tests/test_command_discovery_contract.py` 仍要求 `prog-start.md` 存在，是首要待清理的契约脏债。
6. **`verified + finish_pending` 无显式解锁入口**——需要 `prog set-finish-state` 作为显式 resolver。
7. **WF 主调度仍在 LLM 手里**——所有阶段推进（dispatch evaluator、跑 ship-check、推进到 archived）都依赖用户/LLM 自由判断"下一步该做什么"。这正是 GSD V1→V2 升级前的状态。GSD V2 把"主调度从 LLM 改为程序+状态机"是该项目 Y Combinator 内部公认的最大可靠性提升。progress-tracker 现在还停留在 V1 形态——状态机已有但没有自动 tick 的 driver。

### 为什么现在做

- architecture.md Phase-1 Scope（line 829-835）明确“2 weeks”窗口，已经给出 6 项可拆 PR 的工作包。
- `/prog-start` 清理是其他 5 个 PR 的前置脏债——test_command_discovery_contract.py 红测阻塞 CI，必须先解。
- schema 2.1 已经落地；后续 PR 的重点不再是 schema bump，而是避免在既有 2.1 数据契约之上继续扩散职责耦合。
- gstack 已经在 Y Combinator 内部验证过 review 分流 + ship 门禁 + docs-sync 的可行性，我们直接借鉴而不是重新设计。

### 预期产出

- 7 个独立可合并的 PR（PR-1 ~ PR-7），按顺序执行。
- Schema 从 2.0 升至 2.1，保持向下兼容。
- 7 个新 Python 模块 + 2 个新 CLI 子命令（`set-finish-state`, `ship-check`, `drive`）+ 8 套测试文件。
- PR-7 把 WF 升级为**自动 tick 模式**：feature 一旦进入 implementing 后，每次 LLM Stop / 用户提交 prompt / 用户尝试跑 `prog done` 时，hook 都会自动判断"下一步该做什么"并通过 additionalContext 注入到 LLM 上下文，强制推进到下一阶段，直到 archived。
- 零破坏性变更：所有现有命令契约（`/prog-init`, `/prog-next`, `/prog-done`, `/prog-update`, `/prog-sync`, `/prog-ui`, `/prog-fix`）保持行为兼容；`PROG_AUTO_DRIVER=0` 环境变量可关闭 PR-7 自动 tick，回退到 PR-6 终态的"半自动"模式。

---

## Scope

### In Scope

- PR-1：清理 `/prog-start` 契约残留，锁定 `/prog-next` 为唯一 start path。
- PR-2：新增 `prog set-finish-state --feature-id <id> --status <state>` CLI 作为 `finish_pending` 显式 resolver。
- PR-3：新增 `evaluator_gate.py` 模块 + `quality_gates.evaluator` 数据契约 + 独立 subagent 调度约束。
- PR-4：新增 `review_router.py` 模块 + `quality_gates.reviews` 数据契约 + 多 lane 路由（eng/qa/docs 强制，design/devex 可选）。
- PR-5：新增 `ship_check.py` 模块 + `quality_gates.ship_check` 数据契约 + docs-sync 子检查。
- PR-6：新增 `sprint_ledger.py` 模块 + `sprint_contract` + `handoff` 数据契约 + append-only sprint artifact 持久化。
- PR-7：新增 `wf_state_machine.py`（纯函数 FSM kernel）+ `wf_auto_driver.py`（hook 入口 thin shell）+ `prog drive` CLI + 注册 PreToolUse / Stop / UserPromptSubmit hook + SKILL.md 加 `wf-auto-instruction` 协议，实现 WF 自动推进。
- Schema 2.1 迁移逻辑（在 `_apply_schema_defaults` 内统一加）。

### Out of Scope

- **不新增 `prog-start.md`**（ADR-008 不可逆决策）。
- **不替换 superpowers 集成**——`feature-implement` 继续调用 `brainstorming` / `writing-plans` / `subagent-driven-development` / `executing-plans`；本次只新增，不替换。
- **不实现 gstack 的 browser handoff / Conductor 并行 10-15 sprint / `/office-hours` 六个 forcing questions 等高级能力**——这些属于 Phase-2+，本次不触碰。
- **不动 `plugins/progress-tracker/docs/progress-tracker/state/*` 历史快照**——state 快照是历史审计记录，改写会破坏 transaction_manager 审计 hash。
- **不动 `architecture.md`**——所有 `/prog-start` 提及都是 ADR/契约文档，属于有意保留。
- **不做 schema 2.1 → 2.2 / 2.3 演进**——本次只升一档。
- **不引入新的外部依赖**（pytest、argparse、json、pathlib 都已经是标准库或已存在）。
- **不改动现有 CI 配置**——所有新测试文件直接被 pytest discovery 发现即可。

---

## gstack 借鉴映射

基于 https://github.com/garrytan/gstack README 的真实 slash command 与工作流阶段。

### gstack 完整工作流

```
Think → Plan → Build → Review → Test → Ship → Reflect
```

| gstack 阶段 | gstack slash command | 功能 | 借鉴到 progress-tracker |
|---|---|---|---|
| Think | `/office-hours` | 6 个 forcing question 在写代码前重构产品理解 | **不做**（Phase-2 候选） |
| Plan (CEO) | `/plan-ceo-review` | 发现隐藏的 10-star product | **不做**（产品侧，非工程纪律） |
| Plan (Eng) | `/plan-eng-review` | 锁定架构、数据流、图、边界、测试 | 已由现有 `/prog-plan` + `architectural-planning` skill 覆盖 |
| Plan (Design) | `/plan-design-review` | 按维度 0-10 评分设计 | → **PR-4** `review_router` 的 `design` lane（可选） |
| Plan (DevEx) | `/plan-devex-review` | 探索 persona、benchmark、friction | → **PR-4** `review_router` 的 `devex` lane（可选） |
| Review | `/review` | 找出 CI 通过但生产爆炸的 bug | → **PR-3** `evaluator_gate`（核心借鉴：staff-engineer 独立审计） |
| Test | `/qa` | 真实浏览器测，原子提交 fix，再验证 | 部分已由现有 `test_steps` + `_run_acceptance_tests` 覆盖；coverage audit 落 **PR-5** |
| Ship | `/ship` | 同步 main、跑测试、coverage audit、push、open PR | → **PR-5** `ship_check`（核心借鉴：统一失败即阻断的 pre-archive 门禁） |
| Deploy | `/land-and-deploy` | 合 PR，等 CI/deploy，验证 prod 健康 | **不做**（部署是业务侧） |
| Document | `/document-release` | 更新所有 project docs 对齐已发布内容；**被 `/ship` 自动调用** | → **PR-5** `ship_check` 的 docs-sync 子检查（自动嵌入） |
| Reflect | `/retro` | 周报 retro、个人 breakdown、shipping streak | 已由现有 `add_retro` 覆盖 |

### 关键借鉴纪律（直接落进对应 PR）

1. **Review 智能路由**（gstack README 原话：“CEO doesn't have to look at infra bug fixes, design review isn't needed for backend changes”）→ **PR-4** `review_router.required_reviews(feature)` 必须读 `change_spec.categories` 决定 lane 集合，而不是对所有 feature 跑所有 lane。
2. **`/ship` 的 coverage audit 强制性**（gstack README：“Every `/ship` run produces a coverage audit”）→ **PR-5** `ship_check` 必须把测试覆盖率结果作为 `failures[]` 中的一项，低于阈值直接阻断。
3. **`/document-release` 被 `/ship` 自动调用**（gstack README：“auto-invoked by `/ship` to catch stale READMEs automatically”）→ **PR-5** 的 docs-sync 不能是独立命令，必须嵌入 `ship_check`；独立跑是绕过门禁。
4. **Skill-to-skill artifact handoff**（gstack README：“Each skill feeds into the next. `/office-hours` writes a design doc that `/plan-ceo-review` reads”）→ **PR-6** `sprint_ledger` 必须用**文件路径**作为 handoff 载体，不是对话历史或内存变量。
5. **Review Readiness Dashboard**（gstack README）→ **PR-4** 要求 `/prog` status 输出渲染 `quality_gates` 矩阵（evaluator / reviews / ship_check 三列），由现有 `/prog-ui` 字段直渲即可，无需独立 dashboard。

---

## 通用 Schema 2.1 契约（所有 PR 共享）

这是 PR-3 到 PR-6 的共同数据底座。PR-1 和 PR-2 不触碰 schema。

### Schema Version 升级

**Modify:** `hooks/scripts/progress_manager.py` line 115 附近

```python
CURRENT_SCHEMA_VERSION = "2.1"   # 从 "2.0" 升级
```

### 新增 feature 级字段

在 `features[]` 中加入：

```python
{
  # --- 原有字段不动 ---
  "id": 1,
  "name": "...",
  "lifecycle_state": "...",
  "change_spec": {...},
  "requirement_ids": [...],
  "acceptance_scenarios": [...],
  # ... 其他原有字段

  # --- PR-6 新增：sprint 契约（done 定义） ---
  "sprint_contract": {
    "scope": "",                       # str, 本 sprint 的边界陈述
    "done_criteria": [],               # list[str], 可验证的完成条件
    "test_plan": [],                   # list[str], 测试计划要点
    "accepted_by": None,               # str | None, 接受人（角色或 agent 名）
    "accepted_at": None                # ISO-8601Z | None
  },

  # --- PR-3/4/5 新增：质量门矩阵 ---
  "quality_gates": {
    "evaluator": {
      "status": "pending",             # pending | pass | retry | required_reviews
      "score": None,                   # int | None, 0-100
      "defects": [],                   # list[{id, severity, description}]
      "last_run_at": None              # ISO-8601Z | None
    },
    "reviews": {
      "required": [],                  # list[str], 从 review_router 计算
      "passed": [],                    # list[str], 已通过的 lane
      "pending": []                    # list[str], 未完成的 lane
    },
    "ship_check": {
      "status": "pending",             # pending | pass | fail
      "failures": [],                  # list[{check_id, detail}]
      "last_run_at": None              # ISO-8601Z | None
    }
  },

  # --- PR-6 新增：phase handoff artifact ---
  "handoff": {
    "from_phase": None,                # str | None
    "to_phase": None,                  # str | None
    "artifact_path": None,             # str | None, 相对 repo 根的路径
    "created_at": None                 # ISO-8601Z | None
  }
}
```

### 向下兼容策略

- **单一 backfill 点**：所有 schema 2.1 新字段的默认值在 `_apply_schema_defaults()`（`progress_manager.py:1284`）中统一注入。
- **旧 progress.json（2.0）首次加载**：自动注入默认值 + 写 schema_version = "2.1"。
- **PROG_DISABLE_V2 逃生门**：若环境变量 `PROG_DISABLE_V2=1`，`_apply_schema_defaults` 按 ADR-002 纪律**不得覆盖**已有更新字段。
- **审计事件**：首次升级时 `audit.log` 追加 `{"event": "schema_migration", "from": "2.0", "to": "2.1"}` 记录。

### 共享迁移测试（所有新字段统一）

**Create:** `plugins/progress-tracker/tests/test_schema_2_1_migration.py`

覆盖：
1. `test_schema_default_is_2_1`
2. `test_legacy_2_0_progress_json_backfills_all_new_fields`
3. `test_prog_disable_v2_env_var_preserves_newer_fields`
4. `test_audit_log_records_schema_migration_event`
5. `test_round_trip_preserves_unknown_fields`

---

## File Structure

### 新增文件

| 路径 | PR | 用途 |
|---|---|---|
| `hooks/scripts/evaluator_gate.py` | PR-3 | 独立质量评估门，调度隔离 subagent 产出 pass/retry/required_reviews |
| `hooks/scripts/review_router.py` | PR-4 | 根据变更类型选 review lane |
| `hooks/scripts/ship_check.py` | PR-5 | 统一 ship 门禁（测试覆盖 + 回归 + docs-sync） |
| `hooks/scripts/sprint_ledger.py` | PR-6 | append-only sprint artifact 记录 |
| `hooks/scripts/wf_state_machine.py` | PR-7 | **纯函数** FSM kernel：`compute_next_action(feature) → Action` |
| `hooks/scripts/wf_auto_driver.py` | PR-7 | hook 入口 thin shell：读 progress.json → call FSM → 输出 hook JSON |
| `tests/test_schema_2_1_migration.py` | 共享 | 共享 schema 迁移契约 |
| `tests/test_set_finish_state_cli.py` | PR-2 | `prog set-finish-state` CLI 契约 |
| `tests/test_evaluator_gate.py` | PR-3 | evaluator_gate 单元 |
| `tests/test_review_router.py` | PR-4 | review_router 单元 |
| `tests/test_ship_check.py` | PR-5 | ship_check 单元 + docs-sync 子检查 |
| `tests/test_sprint_ledger.py` | PR-6 | sprint_ledger + handoff 契约 |
| `tests/test_wf_state_machine.py` | PR-7 | FSM kernel 纯函数单元 |
| `tests/test_wf_auto_driver.py` | PR-7 | hook 入口端到端（subprocess 模拟 hook payload） |

### 修改文件

| 路径 | PR | 修改性质 |
|---|---|---|
| `tests/test_command_discovery_contract.py` | PR-1 | 移除 prog-start.md 期望 + 新增反向断言 |
| `tests/test_feature_contract_readiness.py` | PR-1 | 第 103 行 docstring 措辞对齐 |
| `hooks/scripts/progress_manager.py` | PR-2~PR-7 | schema 2.1 升级 + `_apply_schema_defaults` 扩展 + 新 CLI 子命令（含 `prog drive`） + `/prog-done` 串联 evaluator/review/ship gate |
| `commands/prog-done.md` | PR-3/4/5 | 更新 description 明确需要通过 quality_gates |
| `skills/feature-complete/SKILL.md` | PR-3/4/5/7 | 在 `/prog-done` 流程中新增 evaluator/review/ship 串联步骤 + `wf-auto-instruction` 协议 |
| `skills/feature-implement/SKILL.md` | PR-6/7 | sprint_contract 强制 + `wf-auto-instruction` 协议 |
| `hooks/hooks.json` | PR-7 | 新增 PreToolUse + Stop hook 路由到 wf_auto_driver |
| `hooks/run-hook.sh` | PR-7 | 新增 `wf-tick` / `wf-gate` 子命令路由 |

### 明确不新增/不删除

- 不新增 `prog-start.md`（ADR-008）
- 不新增独立 `transaction_manager.py`（`progress_transaction()` 已在 `progress_manager.py` 内）
- 不新增独立 `finish_gate.py`（finish_pending 逻辑内联在 `complete_feature` + `set_finish_state` CLI 中）
- 不删除任何现有文件

---

## PR-1: Cleanup & Lock `/prog-start` Residue

**Goal:** 清理 `/prog-start` 契约残留，解开 `test_command_discovery_contract.py` 红测，为 PR-2~PR-6 腾出干净起点。

**Files:**
- Modify: `plugins/progress-tracker/tests/test_command_discovery_contract.py`
- Modify: `plugins/progress-tracker/tests/test_feature_contract_readiness.py`

### Task 1.1: 修复 command discovery 契约

- [ ] **Step 1.1.1: 移除 expected_commands 中的 `prog-start.md`**

Edit `tests/test_command_discovery_contract.py`:

```python
def test_core_progress_commands_remain_discoverable():
    expected_commands = {
        "prog.md",
        "prog-init.md",
        "prog-next.md",
        "prog-update.md",
        "prog-done.md",
        "prog-sync.md",
        "prog-ui.md",
        "help.md",
    }

    actual_commands = {path.name for path in COMMANDS_DIR.glob("*.md")}
    assert expected_commands.issubset(actual_commands)
```

- [ ] **Step 1.1.2: 新增反向锁定测试**

在同文件末尾追加：

```python
def test_prog_start_command_is_not_reintroduced():
    """ADR-008: `/prog-next` is the sole feature-start entrypoint; `prog-start.md` must stay removed."""
    assert not (COMMANDS_DIR / "prog-start.md").exists()
```

- [ ] **Step 1.1.3: 运行测试确认通过**

```bash
pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py
```

预期：3 tests passed。

- [ ] **Step 1.1.4: Commit**

```bash
git add plugins/progress-tracker/tests/test_command_discovery_contract.py
git commit -m "test(progress-tracker): lock ADR-008, remove prog-start.md expectation, add reverse guard"
```

### Task 1.2: 同步 readiness 测试 docstring

- [ ] **Step 1.2.1: 更新 docstring**

Edit `tests/test_feature_contract_readiness.py` 第 103 行：

```python
def test_set_development_stage_developing_requires_readiness(temp_dir):
    """`/prog-next` start path must fail if feature readiness contract is invalid (ADR-008)."""
```

- [ ] **Step 1.2.2: 运行 readiness 套件**

```bash
pytest -q plugins/progress-tracker/tests/test_feature_contract_readiness.py
```

预期：全部 pass。

- [ ] **Step 1.2.3: 运行 PR-1 契约 grep 确认残留分类**

```bash
rg -n "/prog-start|prog-start.md" plugins/progress-tracker/docs plugins/progress-tracker/tests docs/progress-tracker/architecture/architecture.md
```

预期残留命中（全部合法）：
- `architecture.md` ADR 段（有意保留）
- `plugins/progress-tracker/docs/progress-tracker/state/*` 历史快照（不是契约）
- `tests/test_command_discovery_contract.py` 新增反向断言行

- [ ] **Step 1.2.4: Commit**

```bash
git add plugins/progress-tracker/tests/test_feature_contract_readiness.py
git commit -m "test(progress-tracker): align readiness docstring with /prog-next start path (ADR-008)"
```

### PR-1 验收

| 检查 | 命令 | 期望 |
|---|---|---|
| command discovery | `pytest -q tests/test_command_discovery_contract.py` | 3 passed |
| readiness | `pytest -q tests/test_feature_contract_readiness.py` | all passed |
| 契约 grep | `rg -n "/prog-start\|prog-start.md" plugins/progress-tracker/docs plugins/progress-tracker/tests docs/progress-tracker/architecture/architecture.md` | 命中仅在允许清单内 |

---

## PR-2: `prog set-finish-state` Resolver CLI

**Goal:** 提供显式 `finish_pending` 解锁入口，让 `verified + finish_pending` 状态可通过命令而非对话指令恢复。

**Files:**
- Modify: `hooks/scripts/progress_manager.py`（新增 `cmd_set_finish_state` + CLI 子命令）
- Create: `tests/test_set_finish_state_cli.py`

### Task 2.1: 写失败测试

- [ ] **Step 2.1.1: 创建测试文件**

Create `plugins/progress-tracker/tests/test_set_finish_state_cli.py`:

```python
#!/usr/bin/env python3
"""CLI contract for `prog set-finish-state` resolver."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
PROGRESS_MANAGER = PLUGIN_ROOT / "hooks" / "scripts" / "progress_manager.py"


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, str(PROGRESS_MANAGER), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_set_finish_state_rejects_unknown_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["init", "Resolver Project"], cwd=tmp_path)
    result = _run(
        ["set-finish-state", "--feature-id", "1", "--status", "bogus"],
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "invalid status" in result.stderr.lower() or "usage" in result.stderr.lower()


def test_set_finish_state_clears_finish_pending_to_merged_and_cleaned(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["init", "Resolver Project"], cwd=tmp_path)
    _run(["add-feature", "Feature A", "--test-steps", "step 1"], cwd=tmp_path)
    # force feature into finish_pending by direct edit of progress.json
    state_path = tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"
    data = json.loads(state_path.read_text())
    feat = data["features"][0]
    feat["lifecycle_state"] = "verified"
    feat["integration_status"] = "finish_pending"
    feat["finish_pending_reason"] = "worktree cleanup required"
    state_path.write_text(json.dumps(data, indent=2))

    result = _run(
        [
            "set-finish-state",
            "--feature-id", "1",
            "--status", "merged_and_cleaned",
            "--reason", "manual resolution",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0

    data = json.loads(state_path.read_text())
    feat = data["features"][0]
    assert feat["integration_status"] == "merged_and_cleaned"
    assert "finish_pending_reason" not in feat


def test_set_finish_state_refuses_when_feature_not_in_finish_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["init", "Resolver Project"], cwd=tmp_path)
    _run(["add-feature", "Feature A", "--test-steps", "step 1"], cwd=tmp_path)

    result = _run(
        ["set-finish-state", "--feature-id", "1", "--status", "merged_and_cleaned"],
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "not in finish_pending" in result.stderr.lower()


def test_set_finish_state_writes_audit_log_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(["init", "Resolver Project"], cwd=tmp_path)
    _run(["add-feature", "Feature A", "--test-steps", "step 1"], cwd=tmp_path)
    state_path = tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"
    data = json.loads(state_path.read_text())
    data["features"][0]["integration_status"] = "finish_pending"
    data["features"][0]["finish_pending_reason"] = "manual"
    state_path.write_text(json.dumps(data, indent=2))

    _run(
        ["set-finish-state", "--feature-id", "1", "--status", "pr_open", "--reason", "PR filed"],
        cwd=tmp_path,
    )

    audit_path = tmp_path / "docs" / "progress-tracker" / "state" / "audit.log"
    assert audit_path.exists()
    log_lines = audit_path.read_text().strip().splitlines()
    assert any("set_finish_state" in line for line in log_lines)
```

- [ ] **Step 2.1.2: 运行测试确认红**

```bash
pytest -q plugins/progress-tracker/tests/test_set_finish_state_cli.py
```

预期：all fail（CLI 尚未实现，argparse 未知子命令）。

### Task 2.2: 实现 CLI

- [ ] **Step 2.2.1: 新增 handler 函数**

在 `progress_manager.py` 的 CLI handlers 区域（`cmd_done` 附近）新增：

```python
VALID_FINISH_STATES = ("merged_and_cleaned", "pr_open", "kept_with_reason")


def cmd_set_finish_state(feature_id: int, status: str, reason: Optional[str] = None) -> int:
    """Explicit resolver for `verified + finish_pending` state (PR-2)."""
    if status not in VALID_FINISH_STATES:
        print(f"invalid status: {status}. expected one of {VALID_FINISH_STATES}", file=sys.stderr)
        return 2

    with progress_transaction() as data:
        feature = _find_feature(data, feature_id)
        if feature is None:
            print(f"feature {feature_id} not found", file=sys.stderr)
            return 3

        current = feature.get("integration_status")
        if current != "finish_pending":
            print(
                f"feature {feature_id} is not in finish_pending (current: {current})",
                file=sys.stderr,
            )
            return 4

        feature["integration_status"] = status
        feature.pop("finish_pending_reason", None)
        feature["finish_state_resolved_at"] = _iso_now()
        feature["finish_state_resolved_reason"] = reason

        _audit_log(
            event="set_finish_state",
            feature_id=feature_id,
            from_status="finish_pending",
            to_status=status,
            reason=reason,
        )

    return 0
```

- [ ] **Step 2.2.2: 挂 CLI 子命令**

在 `main()` argparse 区域（progress_manager.py line 5797+）加子命令：

```python
sp_set_finish = subparsers.add_parser(
    "set-finish-state",
    help="Explicit resolver for verified+finish_pending state",
)
sp_set_finish.add_argument("--feature-id", type=int, required=True)
sp_set_finish.add_argument("--status", choices=VALID_FINISH_STATES, required=True)
sp_set_finish.add_argument("--reason", type=str, default=None)
```

- [ ] **Step 2.2.3: 挂 dispatch**

在 `_dispatch_command` 中加：

```python
elif args.command == "set-finish-state":
    return cmd_set_finish_state(
        feature_id=args.feature_id,
        status=args.status,
        reason=args.reason,
    )
```

- [ ] **Step 2.2.4: 运行测试确认绿**

```bash
pytest -q plugins/progress-tracker/tests/test_set_finish_state_cli.py
```

预期：all passed。

### Task 2.3: 挡 `/prog-next` 前置检查

- [ ] **Step 2.3.1: 写防退化测试**

在 `tests/test_feature_contract_readiness.py` 末尾追加：

```python
def test_prog_next_blocks_when_any_feature_has_finish_pending(temp_dir):
    """PR-2: `/prog-next` must refuse to advance while any feature is in finish_pending."""
    progress_manager.init_tracking("Block Next", force=True)
    progress_manager.add_feature("Feature A", ["step 1"])
    data = progress_manager.load_progress_json()
    data["features"][0]["integration_status"] = "finish_pending"
    data["features"][0]["finish_pending_reason"] = "manual test"
    progress_manager.save_progress_json(data)

    result = progress_manager.next_feature(return_result=True)
    assert result["blocked"] is True
    assert "finish_pending" in result["reason"]
```

- [ ] **Step 2.3.2: 修改 `next_feature` 实现**

在 `next_feature()` 入口加前置检查：

```python
def next_feature(..., return_result: bool = False):
    data = load_progress_json()
    pending = [f for f in data["features"] if f.get("integration_status") == "finish_pending"]
    if pending:
        reason = (
            f"feature {pending[0]['id']} is in finish_pending; "
            f"run `prog set-finish-state --feature-id {pending[0]['id']} --status <...>` first"
        )
        if return_result:
            return {"blocked": True, "reason": reason, "feature_id": pending[0]["id"]}
        print(reason, file=sys.stderr)
        return 5
    # ... 原逻辑
```

- [ ] **Step 2.3.3: Verify + Commit**

```bash
pytest -q plugins/progress-tracker/tests/test_set_finish_state_cli.py plugins/progress-tracker/tests/test_feature_contract_readiness.py
git add -A
git commit -m "feat(progress-tracker): add `prog set-finish-state` resolver and block `/prog-next` on finish_pending (PR-2)"
```

### PR-2 验收

| 检查 | 命令 | 期望 |
|---|---|---|
| resolver CLI | `pytest -q tests/test_set_finish_state_cli.py` | 4 passed |
| next 阻断 | `pytest -q tests/test_feature_contract_readiness.py -k finish_pending` | 1 passed |
| 整体 readiness | `pytest -q tests/test_feature_contract_readiness.py` | all passed |

---

## PR-3: `evaluator_gate` Independent Quality Gate

**Goal:** 落实 Anthropic harness generator/evaluator 分离纪律 + 借鉴 gstack `/review` 的 staff-engineer 审计模式。Generator（`feature-implement` subagent）产出必须由**另一个 fresh subagent**跑 `evaluator_gate.assess()` 独立评分，不过不能推进到 archive-capable 完成态。

**Files:**
- Create: `hooks/scripts/evaluator_gate.py`
- Create: `tests/test_evaluator_gate.py`
- Modify: `hooks/scripts/progress_manager.py`（schema 2.1 升级 + 在 `cmd_done` 中串联 evaluator gate）
- Create: `tests/test_schema_2_1_migration.py`（共享）
- Modify: `skills/feature-complete/SKILL.md`（在 `/prog-done` workflow 中新增 evaluator subagent 步骤）

### Task 3.1: 共享 Schema 2.1 迁移（先于 3.2 之前落地）

- [ ] **Step 3.1.1: 写迁移测试**

Create `tests/test_schema_2_1_migration.py`:

```python
#!/usr/bin/env python3
"""Schema 2.0 -> 2.1 migration contract."""

import json
import os
from pathlib import Path

import pytest

from progress_manager import (
    _apply_schema_defaults,
    CURRENT_SCHEMA_VERSION,
    load_progress_json,
    save_progress_json,
)


def test_schema_default_is_2_1():
    assert CURRENT_SCHEMA_VERSION == "2.1"


def test_legacy_2_0_progress_json_backfills_all_new_fields():
    data = {
        "schema_version": "2.0",
        "features": [
            {
                "id": 1,
                "name": "legacy feature",
                "lifecycle_state": "approved",
                "development_stage": "planning",
            }
        ],
    }
    _apply_schema_defaults(data)
    assert data["schema_version"] == "2.1"
    feat = data["features"][0]
    assert "sprint_contract" in feat
    assert feat["sprint_contract"]["done_criteria"] == []
    assert "quality_gates" in feat
    assert feat["quality_gates"]["evaluator"]["status"] == "pending"
    assert feat["quality_gates"]["reviews"]["required"] == []
    assert feat["quality_gates"]["ship_check"]["status"] == "pending"
    assert "handoff" in feat
    assert feat["handoff"]["from_phase"] is None


def test_prog_disable_v2_env_var_preserves_newer_fields(monkeypatch):
    monkeypatch.setenv("PROG_DISABLE_V2", "1")
    data = {
        "schema_version": "2.0",
        "features": [
            {
                "id": 1,
                "name": "x",
                "lifecycle_state": "approved",
                "quality_gates": {
                    "evaluator": {"status": "pass", "score": 95, "defects": [], "last_run_at": "2026-04-08T00:00:00Z"},
                    "reviews": {"required": ["eng"], "passed": ["eng"], "pending": []},
                    "ship_check": {"status": "pass", "failures": [], "last_run_at": None},
                },
            }
        ],
    }
    _apply_schema_defaults(data)
    # existing fields must not be clobbered even when migrating
    assert data["features"][0]["quality_gates"]["evaluator"]["status"] == "pass"
    assert data["features"][0]["quality_gates"]["reviews"]["required"] == ["eng"]


def test_round_trip_preserves_unknown_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "docs" / "progress-tracker" / "state"
    state.mkdir(parents=True)
    (state / "progress.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "features": [{"id": 1, "name": "x", "experimental_field": "keep me"}],
            }
        )
    )
    data = load_progress_json()
    assert data["features"][0]["experimental_field"] == "keep me"
    save_progress_json(data)
    reloaded = json.loads((state / "progress.json").read_text())
    assert reloaded["features"][0]["experimental_field"] == "keep me"
    assert reloaded["schema_version"] == "2.1"


def test_audit_log_records_schema_migration_event(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "docs" / "progress-tracker" / "state"
    state.mkdir(parents=True)
    (state / "progress.json").write_text(
        json.dumps({"schema_version": "2.0", "features": []})
    )
    load_progress_json()
    audit = state / "audit.log"
    assert audit.exists()
    lines = audit.read_text().strip().splitlines()
    assert any("schema_migration" in line for line in lines)
```

- [ ] **Step 3.1.2: 红测确认**

```bash
pytest -q plugins/progress-tracker/tests/test_schema_2_1_migration.py
```

预期：all fail（schema 还是 2.0，新字段没注入）。

- [ ] **Step 3.1.3: 实施 schema 2.1 升级**

Edit `hooks/scripts/progress_manager.py`:

1. line 115 附近：`CURRENT_SCHEMA_VERSION = "2.1"`
2. 在 `_apply_schema_defaults()` 内加：
   - 读取旧 `schema_version`
   - 若为 "2.0" → 对每个 feature 调用 `_default_quality_gates(feature)`、`_default_sprint_contract(feature)`、`_default_handoff(feature)`
   - 尊重 `PROG_DISABLE_V2=1`：若 feature 已有对应字段则不覆盖
   - 若发生升级：`_audit_log(event="schema_migration", from_version="2.0", to_version="2.1")`
3. 新增 helper：

```python
def _default_sprint_contract(feature: Dict[str, Any]) -> None:
    if os.environ.get("PROG_DISABLE_V2") == "1" and "sprint_contract" in feature:
        return
    feature.setdefault("sprint_contract", {
        "scope": "",
        "done_criteria": [],
        "test_plan": [],
        "accepted_by": None,
        "accepted_at": None,
    })


def _default_quality_gates(feature: Dict[str, Any]) -> None:
    if os.environ.get("PROG_DISABLE_V2") == "1" and "quality_gates" in feature:
        return
    feature.setdefault("quality_gates", {
        "evaluator": {"status": "pending", "score": None, "defects": [], "last_run_at": None},
        "reviews": {"required": [], "passed": [], "pending": []},
        "ship_check": {"status": "pending", "failures": [], "last_run_at": None},
    })


def _default_handoff(feature: Dict[str, Any]) -> None:
    if os.environ.get("PROG_DISABLE_V2") == "1" and "handoff" in feature:
        return
    feature.setdefault("handoff", {
        "from_phase": None,
        "to_phase": None,
        "artifact_path": None,
        "created_at": None,
    })
```

- [ ] **Step 3.1.4: 绿测确认**

```bash
pytest -q plugins/progress-tracker/tests/test_schema_2_1_migration.py
```

预期：all passed。

- [ ] **Step 3.1.5: 回归现有测试**

```bash
pytest -q plugins/progress-tracker/tests/test_feature_contract_readiness.py plugins/progress-tracker/tests/test_progress_manager.py plugins/progress-tracker/tests/test_progress_ui_status.py
```

预期：all passed（新字段不影响旧逻辑）。

- [ ] **Step 3.1.6: Commit**

```bash
git add -A
git commit -m "feat(progress-tracker): bump schema to 2.1 with sprint_contract/quality_gates/handoff defaults (PR-3 prep)"
```

### Task 3.2: 写 evaluator_gate 失败测试

- [ ] **Step 3.2.1: 创建 `test_evaluator_gate.py`**

```python
#!/usr/bin/env python3
"""evaluator_gate contract tests."""

import pytest

from evaluator_gate import assess, EvaluatorResult, EvaluatorDefect


def test_assess_returns_pass_when_no_defects():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={"test_coverage": 0.9, "defects": []},
    )
    assert result.status == "pass"
    assert result.score >= 80
    assert result.defects == []


def test_assess_returns_retry_on_blocking_defect():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={
            "test_coverage": 0.9,
            "defects": [
                {"id": "D1", "severity": "blocking", "description": "memory leak"},
            ],
        },
    )
    assert result.status == "retry"
    assert any(d.severity == "blocking" for d in result.defects)


def test_assess_fails_when_coverage_below_threshold():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={"test_coverage": 0.5, "defects": []},
    )
    assert result.status == "retry"
    assert any("coverage" in d.description.lower() for d in result.defects)


def test_assess_escalates_to_required_reviews_on_security_defect():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={
            "test_coverage": 0.9,
            "defects": [
                {"id": "D1", "severity": "major", "description": "auth bypass possible"},
            ],
        },
    )
    assert result.status == "required_reviews"


def test_assess_result_serializes_to_quality_gates_evaluator_schema():
    result = assess(
        feature={"id": 1, "name": "test"},
        rubric={"test_coverage_min": 0.8, "require_changelog": False},
        signals={"test_coverage": 0.9, "defects": []},
    )
    payload = result.to_quality_gate_payload()
    assert set(payload.keys()) == {"status", "score", "defects", "last_run_at"}
    assert payload["status"] == "pass"
```

- [ ] **Step 3.2.2: 红测**

```bash
pytest -q plugins/progress-tracker/tests/test_evaluator_gate.py
```

预期：`ImportError: evaluator_gate`。

### Task 3.3: 实现 evaluator_gate 模块

- [ ] **Step 3.3.1: 创建 `hooks/scripts/evaluator_gate.py`**

```python
#!/usr/bin/env python3
"""Independent quality evaluator gate (PR-3).

Generator/evaluator separation follows Anthropic harness discipline:
this module is expected to be invoked from a DIFFERENT subagent context
than the one that produced the feature code. The caller is responsible
for enforcing subagent isolation; this module only encodes the scoring
rubric and defect classification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

Status = Literal["pass", "retry", "required_reviews"]


@dataclass
class EvaluatorDefect:
    id: str
    severity: str  # blocking | major | minor | info
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "severity": self.severity, "description": self.description}


@dataclass
class EvaluatorResult:
    status: Status
    score: int
    defects: List[EvaluatorDefect] = field(default_factory=list)
    last_run_at: str = ""

    def to_quality_gate_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "defects": [d.to_dict() for d in self.defects],
            "last_run_at": self.last_run_at,
        }


_SECURITY_KEYWORDS = ("auth bypass", "sql injection", "xss", "rce", "secret leak")


def _classify(defect_dict: Dict[str, Any]) -> EvaluatorDefect:
    return EvaluatorDefect(
        id=defect_dict["id"],
        severity=defect_dict.get("severity", "minor"),
        description=defect_dict.get("description", ""),
    )


def _score_from_signals(signals: Dict[str, Any]) -> int:
    base = 100
    coverage = float(signals.get("test_coverage", 0.0))
    if coverage < 0.6:
        base -= 40
    elif coverage < 0.8:
        base -= 20
    for d in signals.get("defects", []):
        sev = d.get("severity", "minor")
        base -= {"blocking": 30, "major": 15, "minor": 5, "info": 0}.get(sev, 5)
    return max(0, min(100, base))


def assess(
    *,
    feature: Dict[str, Any],
    rubric: Dict[str, Any],
    signals: Dict[str, Any],
) -> EvaluatorResult:
    """Run the evaluator rubric against generator signals.

    Args:
        feature: current feature dict from progress.json
        rubric: {"test_coverage_min": float, "require_changelog": bool, ...}
        signals: {"test_coverage": float, "defects": list[dict], ...}
    """
    defects = [_classify(d) for d in signals.get("defects", [])]
    coverage = float(signals.get("test_coverage", 0.0))
    if coverage < float(rubric.get("test_coverage_min", 0.8)):
        defects.append(
            EvaluatorDefect(
                id=f"COV-{feature['id']}",
                severity="blocking",
                description=f"test coverage {coverage:.0%} below minimum {rubric['test_coverage_min']:.0%}",
            )
        )

    status: Status
    if any(d.severity == "blocking" for d in defects):
        status = "retry"
    elif any(_is_security_defect(d) for d in defects):
        status = "required_reviews"
    else:
        status = "pass"

    return EvaluatorResult(
        status=status,
        score=_score_from_signals(signals),
        defects=defects,
        last_run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _is_security_defect(d: EvaluatorDefect) -> bool:
    desc = d.description.lower()
    return any(kw in desc for kw in _SECURITY_KEYWORDS) or d.severity == "major"
```

- [ ] **Step 3.3.2: 绿测**

```bash
pytest -q plugins/progress-tracker/tests/test_evaluator_gate.py
```

预期：5 passed。

### Task 3.4: 串联 `/prog-done` 流程（写入 quality_gates.evaluator）

- [ ] **Step 3.4.1: 写集成测试**

在 `tests/test_evaluator_gate.py` 末尾追加：

```python
def test_prog_done_writes_evaluator_result_to_quality_gates(tmp_path, monkeypatch):
    import progress_manager
    monkeypatch.chdir(tmp_path)
    progress_manager.init_tracking("Eval Project", force=True)
    progress_manager.add_feature("Feature A", ["pytest dummy"])
    progress_manager.set_current(1)
    # simulate passing acceptance
    progress_manager._store_evaluator_result(
        feature_id=1,
        result=assess(
            feature={"id": 1, "name": "Feature A"},
            rubric={"test_coverage_min": 0.8, "require_changelog": False},
            signals={"test_coverage": 0.95, "defects": []},
        ),
    )
    data = progress_manager.load_progress_json()
    feat = data["features"][0]
    assert feat["quality_gates"]["evaluator"]["status"] == "pass"
    assert feat["quality_gates"]["evaluator"]["score"] >= 80
```

- [ ] **Step 3.4.2: 在 `progress_manager.py` 新增 `_store_evaluator_result`**

```python
def _store_evaluator_result(feature_id: int, result) -> None:
    """PR-3: persist evaluator assessment into quality_gates.evaluator."""
    with progress_transaction() as data:
        feat = _find_feature(data, feature_id)
        if feat is None:
            raise ValueError(f"feature {feature_id} not found")
        feat["quality_gates"]["evaluator"] = result.to_quality_gate_payload()
        _audit_log(
            event="evaluator_assessment",
            feature_id=feature_id,
            status=result.status,
            score=result.score,
        )
```

- [ ] **Step 3.4.3: 在 `cmd_done` 前置门加 evaluator check**

修改 `_validate_done_preconditions` 或 `cmd_done`：

```python
# After acceptance tests succeed
eval_payload = feature.get("quality_gates", {}).get("evaluator", {})
if eval_payload.get("status") != "pass":
    print(
        f"evaluator gate not passed (status={eval_payload.get('status')}). "
        f"Run evaluator subagent and call _store_evaluator_result before /prog-done.",
        file=sys.stderr,
    )
    return 6
```

- [ ] **Step 3.4.4: 更新 `skills/feature-complete/SKILL.md`**

在 `/prog-done` workflow checklist 中加一条（保持不打断现有 step 编号）：

```markdown
### Step X: Run evaluator gate in a fresh subagent

BEFORE calling `prog done`, dispatch a NEW subagent with `subagent_type=code-reviewer` (or security-auditor for security-sensitive features) to run evaluator_gate.assess() against the current feature. Persist the result via `progress_manager._store_evaluator_result(feature_id, result)`. If status != "pass", do NOT proceed with `prog done` — fix defects and re-dispatch.

Rationale: generator/evaluator must run in independent contexts (Anthropic harness discipline, ADR-009).
```

- [ ] **Step 3.4.5: 绿测 + Commit**

```bash
pytest -q plugins/progress-tracker/tests/test_evaluator_gate.py
git add -A
git commit -m "feat(progress-tracker): add evaluator_gate module with quality_gates.evaluator persistence (PR-3)"
```

### PR-3 验收

| 检查 | 命令 | 期望 |
|---|---|---|
| schema 迁移 | `pytest -q tests/test_schema_2_1_migration.py` | 5 passed |
| evaluator 单元 | `pytest -q tests/test_evaluator_gate.py` | 6 passed |
| cmd_done 集成 | 手动端到端走一遍 init→add→set-current→_store_evaluator_result→done | `quality_gates.evaluator.status == "pass"` 才放行 |
| 回归 | `pytest -q tests/` | 全绿 |

---

## PR-4: `review_router` + Multi-Lane Routing

**Goal:** 借鉴 gstack 的“CEO 不审基础设施 bug、design 不审后端” review 智能路由，按变更类型动态决定 required review lanes。

**Files:**
- Create: `hooks/scripts/review_router.py`
- Create: `tests/test_review_router.py`
- Modify: `hooks/scripts/progress_manager.py`（串联到 `cmd_done`）
- Modify: `skills/feature-complete/SKILL.md`

### Task 4.1: 写 review_router 失败测试

- [ ] **Step 4.1.1: 创建 `tests/test_review_router.py`**

```python
#!/usr/bin/env python3
"""review_router contract tests (PR-4, inspired by gstack review routing)."""

import pytest

from review_router import required_reviews, mark_review_passed, ReviewRouterError


def test_backend_feature_requires_eng_and_qa_only():
    feature = {
        "id": 1,
        "name": "refactor auth middleware",
        "change_spec": {"categories": ["backend", "security"]},
    }
    required = required_reviews(feature)
    assert set(required) == {"eng", "qa", "docs"}
    assert "design" not in required
    assert "devex" not in required


def test_frontend_feature_adds_design_lane():
    feature = {
        "id": 2,
        "name": "new landing page",
        "change_spec": {"categories": ["frontend", "ui"]},
    }
    required = required_reviews(feature)
    assert "design" in required
    assert "eng" in required


def test_sdk_feature_adds_devex_lane():
    feature = {
        "id": 3,
        "name": "python sdk v2",
        "change_spec": {"categories": ["sdk", "api"]},
    }
    required = required_reviews(feature)
    assert "devex" in required


def test_docs_only_feature_requires_only_docs_lane():
    feature = {
        "id": 4,
        "name": "readme update",
        "change_spec": {"categories": ["docs"]},
    }
    required = required_reviews(feature)
    assert required == ["docs"]


def test_required_reviews_is_deterministic_and_sorted():
    feature = {
        "id": 5,
        "name": "mixed change",
        "change_spec": {"categories": ["frontend", "backend", "sdk", "docs"]},
    }
    r1 = required_reviews(feature)
    r2 = required_reviews(feature)
    assert r1 == r2
    assert r1 == sorted(r1)


def test_mark_review_passed_moves_lane_from_pending_to_passed():
    feature = {
        "id": 6,
        "name": "test",
        "change_spec": {"categories": ["backend"]},
        "quality_gates": {
            "reviews": {"required": ["eng", "qa", "docs"], "passed": [], "pending": ["eng", "qa", "docs"]},
        },
    }
    mark_review_passed(feature, lane="eng", reviewer="code-reviewer-agent")
    assert "eng" in feature["quality_gates"]["reviews"]["passed"]
    assert "eng" not in feature["quality_gates"]["reviews"]["pending"]


def test_mark_review_passed_rejects_unknown_lane():
    feature = {
        "id": 7,
        "name": "test",
        "change_spec": {"categories": ["backend"]},
        "quality_gates": {"reviews": {"required": ["eng"], "passed": [], "pending": ["eng"]}},
    }
    with pytest.raises(ReviewRouterError):
        mark_review_passed(feature, lane="design", reviewer="x")
```

- [ ] **Step 4.1.2: 红测**

```bash
pytest -q plugins/progress-tracker/tests/test_review_router.py
```

### Task 4.2: 实现 review_router

- [ ] **Step 4.2.1: Create `hooks/scripts/review_router.py`**

```python
#!/usr/bin/env python3
"""Review router: maps feature change categories to required review lanes (PR-4).

Inspired by gstack's "CEO doesn't review infra, design not needed for backend"
routing discipline (see https://github.com/garrytan/gstack).
"""

from __future__ import annotations

from typing import Any, Dict, List


class ReviewRouterError(Exception):
    pass


# Category -> lane set mapping.
# Keep this table small and explicit; grow as categories emerge.
_LANE_RULES = {
    "backend":   {"eng", "qa", "docs"},
    "frontend":  {"eng", "qa", "docs", "design"},
    "ui":        {"eng", "qa", "docs", "design"},
    "security":  {"eng", "qa", "docs"},
    "infra":     {"eng", "qa", "docs"},
    "sdk":       {"eng", "qa", "docs", "devex"},
    "api":       {"eng", "qa", "docs", "devex"},
    "docs":      {"docs"},
    "refactor":  {"eng", "qa"},
    "test":      {"eng", "qa"},
}


def required_reviews(feature: Dict[str, Any]) -> List[str]:
    """Return the sorted list of review lanes required for this feature."""
    cats = feature.get("change_spec", {}).get("categories") or []
    if not cats:
        # fail closed: unknown change type requires full review
        return sorted({"eng", "qa", "docs"})
    lanes: set = set()
    for cat in cats:
        lanes.update(_LANE_RULES.get(cat, {"eng", "qa", "docs"}))
    return sorted(lanes)


def mark_review_passed(feature: Dict[str, Any], *, lane: str, reviewer: str) -> None:
    """Move `lane` from pending to passed. Raises if lane not in required."""
    gates = feature.setdefault("quality_gates", {}).setdefault(
        "reviews", {"required": [], "passed": [], "pending": []}
    )
    if lane not in gates["required"]:
        raise ReviewRouterError(f"lane {lane!r} is not in required lanes {gates['required']}")
    if lane not in gates["passed"]:
        gates["passed"].append(lane)
    if lane in gates["pending"]:
        gates["pending"].remove(lane)


def initialize_reviews(feature: Dict[str, Any]) -> None:
    """Call on feature start: populate required/pending from change_spec."""
    lanes = required_reviews(feature)
    feature.setdefault("quality_gates", {})["reviews"] = {
        "required": lanes,
        "passed": [],
        "pending": list(lanes),
    }
```

- [ ] **Step 4.2.2: 绿测**

```bash
pytest -q plugins/progress-tracker/tests/test_review_router.py
```

### Task 4.3: 在 feature 启动时初始化 reviews

- [ ] **Step 4.3.1: 集成测试**

在 `test_review_router.py` 末尾追加：

```python
def test_set_current_initializes_review_lanes(tmp_path, monkeypatch):
    import progress_manager
    monkeypatch.chdir(tmp_path)
    progress_manager.init_tracking("Review Init Project", force=True)
    progress_manager.add_feature("Feature A", ["step 1"])
    data = progress_manager.load_progress_json()
    data["features"][0]["change_spec"]["categories"] = ["backend", "security"]
    progress_manager.save_progress_json(data)
    progress_manager.set_current(1)
    data = progress_manager.load_progress_json()
    reviews = data["features"][0]["quality_gates"]["reviews"]
    assert set(reviews["required"]) == {"eng", "qa", "docs"}
    assert reviews["pending"] == reviews["required"]
    assert reviews["passed"] == []
```

- [ ] **Step 4.3.2: 在 `set_current()` 内调用 `review_router.initialize_reviews`**

```python
def set_current(feature_id):
    from review_router import initialize_reviews  # lazy import
    # ... existing logic
    if not feature.get("completed", False):
        feature["development_stage"] = "developing"
        feature["lifecycle_state"] = "implementing"
        if not feature.get("started_at"):
            feature["started_at"] = _iso_now()
        initialize_reviews(feature)   # NEW
```

- [ ] **Step 4.3.3: 在 `cmd_done` 前置门加 review check**

```python
reviews = feature["quality_gates"]["reviews"]
if reviews["pending"]:
    print(
        f"required review lanes still pending: {reviews['pending']}",
        file=sys.stderr,
    )
    return 7
```

- [ ] **Step 4.3.4: 更新 `skills/feature-complete/SKILL.md`**

新增 review dispatch 指导：

```markdown
### Step Y: Dispatch required review lanes

Read `feature.quality_gates.reviews.required` and for each lane dispatch a dedicated subagent:
- `eng` → `code-reviewer` agent
- `qa` → `test-automator` agent
- `docs` → `docs-architect` agent
- `design` → design-review agent (optional lane)
- `devex` → `typescript-pro` / `python-pro` (optional lane)

After each review passes, call `review_router.mark_review_passed(feature, lane=..., reviewer=...)` and persist via `save_progress_json`.
```

- [ ] **Step 4.3.5: 绿测 + Commit**

```bash
pytest -q plugins/progress-tracker/tests/test_review_router.py plugins/progress-tracker/tests/test_feature_contract_readiness.py
git add -A
git commit -m "feat(progress-tracker): add review_router with gstack-inspired lane routing (PR-4)"
```

### PR-4 验收

| 检查 | 命令 | 期望 |
|---|---|---|
| review_router 单元 | `pytest -q tests/test_review_router.py` | 8 passed |
| 集成 | `set_current` 自动初始化 lanes | 手动验证 |
| cmd_done 阻断 | pending 非空时 `/prog-done` 返回 7 | 手动验证 |
| 回归 | `pytest -q tests/` | 全绿 |

---

## PR-5: `ship_check` + docs-sync Gate

**Goal:** 借鉴 gstack `/ship`（sync main、跑测试、coverage audit、push、open PR）+ `/document-release`（被 `/ship` 自动调用）的统一 ship 纪律。实现 archive 前的最后一道门禁。

**Files:**
- Create: `hooks/scripts/ship_check.py`
- Create: `tests/test_ship_check.py`
- Modify: `hooks/scripts/progress_manager.py`（在 archive-capable 完成前调用 + 新增 `prog ship-check` CLI）
- Modify: `skills/feature-complete/SKILL.md`

### Task 5.1: 写 ship_check 失败测试

- [ ] **Step 5.1.1: Create `tests/test_ship_check.py`**

```python
#!/usr/bin/env python3
"""ship_check contract tests (PR-5, inspired by gstack /ship + /document-release)."""

import pytest

from ship_check import run_ship_check, ShipCheckResult, ShipFailure


def test_ship_check_passes_when_all_subchecks_clean(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.92,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 20, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "pass"
    assert result.failures == []


def test_ship_check_fails_when_coverage_below_threshold(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.6,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 20, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "coverage" for f in result.failures)


def test_ship_check_fails_when_regression_broken(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.9,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 19, "failed": 1},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "regression" for f in result.failures)


def test_ship_check_fails_when_docs_drift_detected(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.9,
            "test_results": {"passed": 30, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": False, "architecture_refs_valid": True},
            "regression_results": {"passed": 20, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "docs_sync" for f in result.failures)


def test_ship_check_result_serializes_to_quality_gates_schema(tmp_path):
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 0.9,
            "test_results": {"passed": 10, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 10, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    payload = result.to_quality_gate_payload()
    assert set(payload.keys()) == {"status", "failures", "last_run_at"}


def test_ship_check_cli_returns_nonzero_on_failure(tmp_path, monkeypatch):
    import subprocess, sys, json
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    progress_manager = Path(__file__).parent.parent / "hooks" / "scripts" / "progress_manager.py"
    subprocess.run([sys.executable, str(progress_manager), "init", "Ship Test"], cwd=tmp_path)
    subprocess.run([sys.executable, str(progress_manager), "add-feature", "F1", "--test-steps", "echo"], cwd=tmp_path)
    # force pending ship_check state via direct edit
    state = tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"
    data = json.loads(state.read_text())
    data["features"][0]["quality_gates"]["ship_check"] = {
        "status": "fail",
        "failures": [{"check_id": "coverage", "detail": "59%"}],
        "last_run_at": "2026-04-08T00:00:00Z",
    }
    state.write_text(json.dumps(data, indent=2))
    result = subprocess.run(
        [sys.executable, str(progress_manager), "ship-check", "--feature-id", "1"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode != 0
```

- [ ] **Step 5.1.2: 红测**

### Task 5.2: 实现 ship_check 模块

- [ ] **Step 5.2.1: Create `hooks/scripts/ship_check.py`**

```python
#!/usr/bin/env python3
"""ship_check: unified pre-archive gate (PR-5).

Mirrors gstack /ship discipline: "sync main, run tests, audit coverage,
push, open PR" + auto-invoked /document-release for docs-sync.
See https://github.com/garrytan/gstack for the upstream concept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

Status = Literal["pass", "fail"]


@dataclass
class ShipFailure:
    check_id: str
    detail: str

    def to_dict(self) -> Dict[str, str]:
        return {"check_id": self.check_id, "detail": self.detail}


@dataclass
class ShipCheckResult:
    status: Status
    failures: List[ShipFailure] = field(default_factory=list)
    last_run_at: str = ""

    def to_quality_gate_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "failures": [f.to_dict() for f in self.failures],
            "last_run_at": self.last_run_at,
        }


def _check_coverage(inputs: Dict[str, Any], thresholds: Dict[str, Any]) -> List[ShipFailure]:
    cov = float(inputs.get("test_coverage", 0.0))
    minimum = float(thresholds.get("coverage_min", 0.8))
    if cov < minimum:
        return [ShipFailure(check_id="coverage", detail=f"{cov:.0%} < required {minimum:.0%}")]
    return []


def _check_tests(inputs: Dict[str, Any]) -> List[ShipFailure]:
    r = inputs.get("test_results", {})
    if r.get("failed", 0) > 0:
        return [ShipFailure(check_id="tests", detail=f"{r['failed']} test(s) failed")]
    return []


def _check_regression(inputs: Dict[str, Any]) -> List[ShipFailure]:
    r = inputs.get("regression_results", {})
    if r.get("failed", 0) > 0:
        return [ShipFailure(check_id="regression", detail=f"{r['failed']} regression(s) failed")]
    return []


def _check_docs_sync(inputs: Dict[str, Any]) -> List[ShipFailure]:
    """Borrowed from gstack /document-release: auto-check docs drift."""
    docs = inputs.get("docs_sync", {})
    failures = []
    if not docs.get("progress_md_matches_json", True):
        failures.append(ShipFailure(check_id="docs_sync", detail="progress.md out of sync with progress.json"))
    if not docs.get("architecture_refs_valid", True):
        failures.append(ShipFailure(check_id="docs_sync", detail="architecture.md references stale feature IDs"))
    return failures


def run_ship_check(
    *,
    feature_id: int,
    project_root: Path,
    inputs: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> ShipCheckResult:
    failures: List[ShipFailure] = []
    failures += _check_tests(inputs)
    failures += _check_coverage(inputs, thresholds)
    failures += _check_regression(inputs)
    failures += _check_docs_sync(inputs)

    return ShipCheckResult(
        status="fail" if failures else "pass",
        failures=failures,
        last_run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
```

- [ ] **Step 5.2.2: 在 progress_manager 加 `cmd_ship_check` CLI**

```python
def cmd_ship_check(feature_id: int, *, coverage_min: float = 0.8) -> int:
    from ship_check import run_ship_check
    data = load_progress_json()
    feat = _find_feature(data, feature_id)
    if feat is None:
        print(f"feature {feature_id} not found", file=sys.stderr)
        return 3

    # Collect real signals from recent test reports (best effort)
    inputs = _collect_ship_signals(feat)
    result = run_ship_check(
        feature_id=feature_id,
        project_root=Path.cwd(),
        inputs=inputs,
        thresholds={"coverage_min": coverage_min},
    )

    with progress_transaction() as data2:
        feat2 = _find_feature(data2, feature_id)
        feat2["quality_gates"]["ship_check"] = result.to_quality_gate_payload()

    if result.status == "fail":
        for f in result.failures:
            print(f"[{f.check_id}] {f.detail}", file=sys.stderr)
        return 8
    return 0
```

- [ ] **Step 5.2.3: 挂子命令**

```python
sp_ship = subparsers.add_parser("ship-check", help="Run unified pre-archive ship gate")
sp_ship.add_argument("--feature-id", type=int, required=True)
sp_ship.add_argument("--coverage-min", type=float, default=0.8)
```

- [ ] **Step 5.2.4: 在 `cmd_done` 前置门加 ship check**

```python
ship = feature["quality_gates"]["ship_check"]
if ship["status"] != "pass":
    print(
        f"ship_check not passed (status={ship['status']}). "
        f"Run `prog ship-check --feature-id {feature_id}` first.",
        file=sys.stderr,
    )
    return 8
```

- [ ] **Step 5.2.5: 绿测 + Commit**

```bash
pytest -q plugins/progress-tracker/tests/test_ship_check.py
git add -A
git commit -m "feat(progress-tracker): add ship_check with docs-sync gate (PR-5, gstack /ship inspired)"
```

### PR-5 验收

| 检查 | 命令 | 期望 |
|---|---|---|
| ship_check 单元 | `pytest -q tests/test_ship_check.py` | 6 passed |
| CLI 阻断 | `prog ship-check --feature-id N` 失败返回非 0 | 手动验证 |
| cmd_done 阻断 | ship_check 非 pass 时 done 失败 | 手动验证 |
| 回归 | `pytest -q tests/` | 全绿 |

---

## PR-6: `sprint_ledger` + Sprint Contract + Handoff Artifact

**Goal:** 实现 Anthropic harness 的 sprint contract（先定义 done 再做）+ gstack 的 skill-to-skill artifact handoff（文件路径而非对话历史），让长跑 session 中断后可从 artifact 恢复而非依赖对话记忆。

**Files:**
- Create: `hooks/scripts/sprint_ledger.py`
- Create: `tests/test_sprint_ledger.py`
- Modify: `hooks/scripts/progress_manager.py`
- Modify: `skills/feature-complete/SKILL.md`、`skills/feature-implement/SKILL.md`

### Task 6.1: 写 sprint_ledger 失败测试

- [ ] **Step 6.1.1: Create `tests/test_sprint_ledger.py`**

```python
#!/usr/bin/env python3
"""sprint_ledger contract tests (PR-6)."""

import pytest
from pathlib import Path

from sprint_ledger import record, read_latest, list_sprint_records, SprintRecord, SprintLedgerError


def test_record_writes_append_only_jsonl(tmp_path):
    ledger_path = tmp_path / "docs" / "progress-tracker" / "state" / "sprint_ledger.jsonl"
    record(
        feature_id=1,
        phase="plan",
        artifact_path="docs/superpowers/plans/2026-04-08-auth.md",
        metadata={"author": "agent-planner"},
        ledger_path=ledger_path,
    )
    record(
        feature_id=1,
        phase="implementation",
        artifact_path="docs/progress-tracker/state/progress.json",
        metadata={"commit": "abc123"},
        ledger_path=ledger_path,
    )
    lines = ledger_path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_list_sprint_records_filters_by_feature(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    record(feature_id=1, phase="plan", artifact_path="a.md", ledger_path=ledger_path)
    record(feature_id=2, phase="plan", artifact_path="b.md", ledger_path=ledger_path)
    record(feature_id=1, phase="implementation", artifact_path="c.md", ledger_path=ledger_path)
    records = list_sprint_records(feature_id=1, ledger_path=ledger_path)
    assert len(records) == 2
    assert all(r.feature_id == 1 for r in records)


def test_read_latest_returns_most_recent_phase_record(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    record(feature_id=1, phase="plan", artifact_path="a.md", ledger_path=ledger_path)
    record(feature_id=1, phase="plan", artifact_path="a2.md", ledger_path=ledger_path)
    latest = read_latest(feature_id=1, phase="plan", ledger_path=ledger_path)
    assert latest.artifact_path == "a2.md"


def test_record_rejects_unknown_phase(tmp_path):
    with pytest.raises(SprintLedgerError):
        record(feature_id=1, phase="bogus", artifact_path="x", ledger_path=tmp_path / "l.jsonl")


def test_handoff_field_is_updated_when_phase_transitions(tmp_path, monkeypatch):
    import progress_manager
    from sprint_ledger import mark_handoff
    monkeypatch.chdir(tmp_path)
    progress_manager.init_tracking("Handoff Test", force=True)
    progress_manager.add_feature("F1", ["step 1"])
    mark_handoff(feature_id=1, from_phase="plan", to_phase="implementation", artifact_path="plan.md")
    data = progress_manager.load_progress_json()
    feat = data["features"][0]
    assert feat["handoff"]["from_phase"] == "plan"
    assert feat["handoff"]["to_phase"] == "implementation"
    assert feat["handoff"]["artifact_path"] == "plan.md"


def test_sprint_contract_done_criteria_required_before_phase_execution(tmp_path, monkeypatch):
    import progress_manager
    from sprint_ledger import require_sprint_contract
    monkeypatch.chdir(tmp_path)
    progress_manager.init_tracking("Contract Test", force=True)
    progress_manager.add_feature("F1", ["step 1"])
    data = progress_manager.load_progress_json()
    # empty sprint_contract -> should fail
    with pytest.raises(SprintLedgerError):
        require_sprint_contract(data["features"][0])
    data["features"][0]["sprint_contract"] = {
        "scope": "auth middleware rewrite",
        "done_criteria": ["tests pass", "docs updated"],
        "test_plan": ["unit + integration"],
        "accepted_by": "user",
        "accepted_at": "2026-04-08T00:00:00Z",
    }
    require_sprint_contract(data["features"][0])  # must not raise
```

- [ ] **Step 6.1.2: 红测**

### Task 6.2: 实现 sprint_ledger 模块

- [ ] **Step 6.2.1: Create `hooks/scripts/sprint_ledger.py`**

```python
#!/usr/bin/env python3
"""sprint_ledger: append-only sprint artifact persistence (PR-6).

Enables long-running session resumability without relying on chat history.
Mirrors gstack skill-to-skill handoff pattern (file artifacts, not memory).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SprintLedgerError(Exception):
    pass


VALID_PHASES = ("plan", "implementation", "evaluation", "handoff")


@dataclass
class SprintRecord:
    timestamp: str
    feature_id: int
    phase: str
    artifact_path: str
    metadata: Dict[str, Any]

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _default_ledger_path() -> Path:
    return Path.cwd() / "docs" / "progress-tracker" / "state" / "sprint_ledger.jsonl"


def record(
    *,
    feature_id: int,
    phase: str,
    artifact_path: str,
    metadata: Optional[Dict[str, Any]] = None,
    ledger_path: Optional[Path] = None,
) -> SprintRecord:
    if phase not in VALID_PHASES:
        raise SprintLedgerError(f"phase {phase!r} not in {VALID_PHASES}")
    path = ledger_path or _default_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = SprintRecord(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        feature_id=feature_id,
        phase=phase,
        artifact_path=artifact_path,
        metadata=metadata or {},
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(rec.to_json_line() + "\n")
    return rec


def list_sprint_records(
    *,
    feature_id: Optional[int] = None,
    phase: Optional[str] = None,
    ledger_path: Optional[Path] = None,
) -> List[SprintRecord]:
    path = ledger_path or _default_ledger_path()
    if not path.exists():
        return []
    out: List[SprintRecord] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if feature_id is not None and d["feature_id"] != feature_id:
            continue
        if phase is not None and d["phase"] != phase:
            continue
        out.append(SprintRecord(**d))
    return out


def read_latest(
    *,
    feature_id: int,
    phase: str,
    ledger_path: Optional[Path] = None,
) -> Optional[SprintRecord]:
    records = list_sprint_records(feature_id=feature_id, phase=phase, ledger_path=ledger_path)
    return records[-1] if records else None


def require_sprint_contract(feature: Dict[str, Any]) -> None:
    """Raise if sprint_contract is incomplete — must be satisfied before execution."""
    sc = feature.get("sprint_contract", {})
    missing = []
    if not sc.get("scope"):
        missing.append("scope")
    if not sc.get("done_criteria"):
        missing.append("done_criteria")
    if not sc.get("test_plan"):
        missing.append("test_plan")
    if missing:
        raise SprintLedgerError(
            f"sprint_contract incomplete: missing {missing}. "
            "Populate before phase execution (Anthropic harness discipline)."
        )


def mark_handoff(
    *,
    feature_id: int,
    from_phase: str,
    to_phase: str,
    artifact_path: str,
) -> None:
    """Update feature.handoff and append a ledger record in one atomic transaction."""
    import progress_manager  # lazy import to avoid cycle
    with progress_manager.progress_transaction() as data:
        feat = progress_manager._find_feature(data, feature_id)
        if feat is None:
            raise SprintLedgerError(f"feature {feature_id} not found")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        feat["handoff"] = {
            "from_phase": from_phase,
            "to_phase": to_phase,
            "artifact_path": artifact_path,
            "created_at": now,
        }
    record(
        feature_id=feature_id,
        phase="handoff",
        artifact_path=artifact_path,
        metadata={"from": from_phase, "to": to_phase},
    )
```

- [ ] **Step 6.2.2: 在 `feature-implement` skill 的 plan 阶段串联 sprint_contract 与 sprint_ledger**

Modify `skills/feature-implement/SKILL.md` —— 在 “Select and Lock Feature” 步骤之后加：

```markdown
### Step 2.5: Enforce sprint contract and record plan artifact

After `set-current`, read `feature.sprint_contract`. If `scope` / `done_criteria` / `test_plan` are empty, STOP and dispatch the `superpowers:brainstorming` + `superpowers:writing-plans` skills to produce them, then write them into `progress.json` via `save_progress_json`.

Once sprint_contract is populated, call `sprint_ledger.record(feature_id=..., phase="plan", artifact_path=<plan file>, metadata={"author": "planner-agent"})`.

Rationale: Anthropic harness planner/generator/evaluator discipline + gstack skill-to-skill artifact handoff. Plan must exist as a file, not as chat memory, so mid-sprint interruptions can resume from ledger.
```

- [ ] **Step 6.2.3: 绿测**

```bash
pytest -q plugins/progress-tracker/tests/test_sprint_ledger.py
```

### Task 6.3: 在 `cmd_done` 前置门加 sprint_contract check

- [ ] **Step 6.3.1: 集成检查**

```python
try:
    from sprint_ledger import require_sprint_contract
    require_sprint_contract(feature)
except SprintLedgerError as e:
    print(f"sprint_contract incomplete: {e}", file=sys.stderr)
    return 9
```

- [ ] **Step 6.3.2: Commit**

```bash
git add -A
git commit -m "feat(progress-tracker): add sprint_ledger with handoff artifacts and contract enforcement (PR-6)"
```

### PR-6 验收

| 检查 | 命令 | 期望 |
|---|---|---|
| sprint_ledger 单元 | `pytest -q tests/test_sprint_ledger.py` | 6 passed |
| append-only | 手动查 `sprint_ledger.jsonl` 只追不改 | 手动验证 |
| handoff 原子 | `mark_handoff` 写 feature.handoff 和 ledger 在同一事务 | 手动验证 |
| cmd_done 阻断 | sprint_contract 不全 done 失败 | 手动验证 |

---

---

## PR-7: Auto-Driver — FSM Kernel + Hook 驱动的自动 WF

**Goal:** 完成 GSD V1→V2 同款"主调度从 LLM 改为程序+状态机"的根本性更新。引入纯函数 `wf_state_machine.py` 作为 FSM kernel，`wf_auto_driver.py` 作为 hook 入口 thin shell，注册 PreToolUse / Stop / UserPromptSubmit 三类 hook，让 WF 在用户不发任何指令的情况下自动从 implementing → verified → archived。

**Files:**
- Create: `hooks/scripts/wf_state_machine.py`
- Create: `hooks/scripts/wf_auto_driver.py`
- Create: `tests/test_wf_state_machine.py`
- Create: `tests/test_wf_auto_driver.py`
- Modify: `hooks/hooks.json`
- Modify: `hooks/run-hook.sh`
- Modify: `hooks/scripts/progress_manager.py`（新增 `prog drive` CLI）
- Modify: `skills/feature-implement/SKILL.md`、`skills/feature-complete/SKILL.md`（加 wf-auto-instruction 协议）

### 设计原则

1. **FSM kernel 必须是纯函数**——`compute_next_action(feature_dict) → Action`，零副作用、零 IO，方便单元测。所有副作用集中在 `wf_auto_driver.py` 的 hook shell 里。
2. **hook 不直接 spawn subagent**——CC hook 的能力是返回 JSON `{decision, additionalContext}`；hook 通过把"DISPATCH X subagent"指令注入 LLM 上下文，由 LLM 在下一轮自动调用 Task tool 实现"看似自动"的 dispatch。
3. **PreToolUse 是硬门禁，Stop 是软推进**——PreToolUse 对 `Bash(prog done)` 拦截 → 若 FSM 说不能 done → `decision: "block"` 强制走完前置门；Stop hook 软推进 → 在 LLM 准备结束 turn 时注入"还没跑完，继续 dispatch X"指令。
4. **逃生门**：环境变量 `PROG_AUTO_DRIVER=0` 关闭 hook 自动 tick，回退到 PR-6 终态；`prog drive --once` 手动 tick 一次。
5. **测试边界清晰**：FSM kernel 测试只关心输入/输出；hook shell 测试用 subprocess 模拟 hook payload。

### Action 数据契约

```python
@dataclass
class Action:
    kind: str            # request_sprint_contract | dispatch_evaluator | dispatch_review_lane
                         # | run_ship_check | complete_done | await_user | noop
    subagent_type: Optional[str] = None       # 当 kind 是 dispatch_* 时填
    lane: Optional[str] = None                # 当 kind 是 dispatch_review_lane 时填
    prompt: Optional[str] = None              # 给 LLM 的指令模板
    blocked_reason: Optional[str] = None      # 当 kind 是 await_user 时填
    feature_id: int = 0
```

### Task 7.1: 写 FSM kernel 失败测试

- [ ] **Step 7.1.1: Create `tests/test_wf_state_machine.py`**

```python
#!/usr/bin/env python3
"""WF state machine kernel contract tests (PR-7)."""

import pytest

from wf_state_machine import compute_next_action, Action


def _base_feature(**overrides):
    feat = {
        "id": 1,
        "name": "test",
        "lifecycle_state": "implementing",
        "integration_status": "in_progress",
        "sprint_contract": {
            "scope": "x",
            "done_criteria": ["d1"],
            "test_plan": ["t1"],
            "accepted_by": "user",
            "accepted_at": "2026-04-08T00:00:00Z",
        },
        "quality_gates": {
            "evaluator": {"status": "pending", "score": None, "defects": [], "last_run_at": None},
            "reviews": {"required": ["eng"], "passed": [], "pending": ["eng"]},
            "ship_check": {"status": "pending", "failures": [], "last_run_at": None},
        },
        "change_spec": {"categories": ["backend"]},
    }
    feat.update(overrides)
    return feat


def test_missing_sprint_contract_returns_request_sprint_contract():
    feat = _base_feature()
    feat["sprint_contract"] = {"scope": "", "done_criteria": [], "test_plan": []}
    action = compute_next_action(feat)
    assert action.kind == "request_sprint_contract"
    assert action.feature_id == 1


def test_implementing_with_pending_evaluator_returns_dispatch_evaluator():
    feat = _base_feature()
    action = compute_next_action(feat)
    assert action.kind == "dispatch_evaluator"
    assert action.subagent_type in ("code-reviewer", "security-auditor")


def test_evaluator_pass_with_pending_review_lane_returns_dispatch_review_lane():
    feat = _base_feature()
    feat["quality_gates"]["evaluator"]["status"] = "pass"
    feat["quality_gates"]["evaluator"]["score"] = 92
    action = compute_next_action(feat)
    assert action.kind == "dispatch_review_lane"
    assert action.lane == "eng"
    assert action.subagent_type == "code-reviewer"


def test_all_reviews_passed_returns_run_ship_check():
    feat = _base_feature()
    feat["quality_gates"]["evaluator"]["status"] = "pass"
    feat["quality_gates"]["reviews"] = {"required": ["eng"], "passed": ["eng"], "pending": []}
    action = compute_next_action(feat)
    assert action.kind == "run_ship_check"


def test_ship_check_pass_returns_complete_done():
    feat = _base_feature()
    feat["quality_gates"]["evaluator"]["status"] = "pass"
    feat["quality_gates"]["reviews"] = {"required": ["eng"], "passed": ["eng"], "pending": []}
    feat["quality_gates"]["ship_check"]["status"] = "pass"
    action = compute_next_action(feat)
    assert action.kind == "complete_done"


def test_finish_pending_returns_await_user_with_resolver_hint():
    feat = _base_feature()
    feat["lifecycle_state"] = "verified"
    feat["integration_status"] = "finish_pending"
    feat["finish_pending_reason"] = "manual"
    action = compute_next_action(feat)
    assert action.kind == "await_user"
    assert "set-finish-state" in action.blocked_reason


def test_evaluator_retry_returns_dispatch_evaluator_with_retry_flag():
    feat = _base_feature()
    feat["quality_gates"]["evaluator"]["status"] = "retry"
    action = compute_next_action(feat)
    assert action.kind == "dispatch_evaluator"
    assert "retry" in (action.prompt or "").lower()


def test_archived_feature_returns_noop():
    feat = _base_feature()
    feat["lifecycle_state"] = "archived"
    action = compute_next_action(feat)
    assert action.kind == "noop"


def test_action_serializes_to_hook_additional_context_payload():
    feat = _base_feature()
    action = compute_next_action(feat)
    payload = action.to_additional_context()
    assert "<wf-auto-instruction>" in payload
    assert "</wf-auto-instruction>" in payload
    assert "dispatch_evaluator" in payload or action.kind in payload
```

- [ ] **Step 7.1.2: 红测**

```bash
pytest -q plugins/progress-tracker/tests/test_wf_state_machine.py
```

预期：`ImportError: wf_state_machine`。

### Task 7.2: 实现 wf_state_machine.py

- [ ] **Step 7.2.1: Create `hooks/scripts/wf_state_machine.py`**

```python
#!/usr/bin/env python3
"""WF state machine kernel (PR-7).

Pure function: input feature dict, output next Action.
Zero side effects, zero IO. All side effects live in wf_auto_driver.py.

This is the GSD V1→V2 equivalent: program-driven workflow scheduling
instead of LLM-driven free orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


_LANE_TO_SUBAGENT = {
    "eng":    "code-reviewer",
    "qa":     "test-automator",
    "docs":   "docs-architect",
    "design": "design-review",
    "devex":  "python-pro",
}


@dataclass
class Action:
    kind: str
    feature_id: int = 0
    subagent_type: Optional[str] = None
    lane: Optional[str] = None
    prompt: Optional[str] = None
    blocked_reason: Optional[str] = None

    def to_additional_context(self) -> str:
        """Serialize to a hook additionalContext payload that the LLM
        will see in its next turn. The wf-auto-instruction tag is the
        protocol contract enforced by feature-implement / feature-complete
        SKILL.md."""
        body_lines = [f"action: {self.kind}", f"feature_id: {self.feature_id}"]
        if self.subagent_type:
            body_lines.append(f"subagent_type: {self.subagent_type}")
        if self.lane:
            body_lines.append(f"review_lane: {self.lane}")
        if self.prompt:
            body_lines.append(f"prompt: {self.prompt}")
        if self.blocked_reason:
            body_lines.append(f"blocked_reason: {self.blocked_reason}")
        body = "\n".join(body_lines)
        return f"<wf-auto-instruction>\n{body}\n</wf-auto-instruction>"


def _sprint_contract_complete(feature: Dict[str, Any]) -> bool:
    sc = feature.get("sprint_contract") or {}
    return bool(sc.get("scope")) and bool(sc.get("done_criteria")) and bool(sc.get("test_plan"))


def _is_security_feature(feature: Dict[str, Any]) -> bool:
    cats = feature.get("change_spec", {}).get("categories") or []
    return "security" in cats


def compute_next_action(feature: Dict[str, Any]) -> Action:
    """Pure function: decide what should happen next for this feature."""
    fid = feature.get("id", 0)

    # Terminal state
    if feature.get("lifecycle_state") == "archived":
        return Action(kind="noop", feature_id=fid)

    # Hard block: finish_pending requires explicit user resolver
    if feature.get("integration_status") == "finish_pending":
        return Action(
            kind="await_user",
            feature_id=fid,
            blocked_reason=(
                f"feature {fid} is in finish_pending. "
                f"Run `prog set-finish-state --feature-id {fid} --status <merged_and_cleaned|pr_open|kept_with_reason>` to unblock."
            ),
        )

    # Sprint contract gate (PR-6)
    if not _sprint_contract_complete(feature):
        return Action(
            kind="request_sprint_contract",
            feature_id=fid,
            prompt=(
                "Sprint contract incomplete. Use brainstorming + writing-plans "
                "skills to populate scope / done_criteria / test_plan, then "
                "save_progress_json before proceeding."
            ),
        )

    gates = feature.get("quality_gates") or {}
    evaluator = gates.get("evaluator") or {}
    reviews = gates.get("reviews") or {}
    ship = gates.get("ship_check") or {}

    # Evaluator gate (PR-3)
    if evaluator.get("status") in (None, "pending", "retry"):
        return Action(
            kind="dispatch_evaluator",
            feature_id=fid,
            subagent_type="security-auditor" if _is_security_feature(feature) else "code-reviewer",
            prompt=(
                "Run evaluator_gate.assess against this feature in a fresh subagent context. "
                "Persist via progress_manager._store_evaluator_result. "
                + ("Previous run flagged retry; address defects and re-run." if evaluator.get("status") == "retry" else "")
            ),
        )

    # Review router gate (PR-4)
    if evaluator.get("status") == "required_reviews" or reviews.get("pending"):
        pending = reviews.get("pending") or []
        if not pending:
            # required_reviews escalation but no pending lanes — re-init
            pending = reviews.get("required") or ["eng"]
        next_lane = pending[0]
        return Action(
            kind="dispatch_review_lane",
            feature_id=fid,
            lane=next_lane,
            subagent_type=_LANE_TO_SUBAGENT.get(next_lane, "code-reviewer"),
            prompt=(
                f"Dispatch a fresh subagent for review lane {next_lane!r}. "
                "After it passes, call review_router.mark_review_passed(feature, lane=..., reviewer=...) "
                "and persist via save_progress_json."
            ),
        )

    # Ship check gate (PR-5)
    if ship.get("status") in (None, "pending", "fail"):
        return Action(
            kind="run_ship_check",
            feature_id=fid,
            prompt=f"Run `prog ship-check --feature-id {fid}`. If it fails, fix root cause and re-run.",
        )

    # All gates green → done
    return Action(
        kind="complete_done",
        feature_id=fid,
        prompt=f"All gates green. Run `prog done` to complete feature {fid}.",
    )
```

- [ ] **Step 7.2.2: 绿测**

```bash
pytest -q plugins/progress-tracker/tests/test_wf_state_machine.py
```

预期：9 passed。

### Task 7.3: 写 hook auto_driver 失败测试

- [ ] **Step 7.3.1: Create `tests/test_wf_auto_driver.py`**

```python
#!/usr/bin/env python3
"""wf_auto_driver hook entrypoint contract tests (PR-7)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
DRIVER = PLUGIN_ROOT / "hooks" / "scripts" / "wf_auto_driver.py"


def _run_driver(args, cwd, stdin_payload=None):
    return subprocess.run(
        [sys.executable, str(DRIVER), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        input=stdin_payload or "",
    )


def _bootstrap(tmp_path):
    pm = PLUGIN_ROOT / "hooks" / "scripts" / "progress_manager.py"
    subprocess.run([sys.executable, str(pm), "init", "AutoDriver"], cwd=tmp_path)
    subprocess.run([sys.executable, str(pm), "add-feature", "F1", "--test-steps", "echo"], cwd=tmp_path)
    state = tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"
    data = json.loads(state.read_text())
    feat = data["features"][0]
    feat["sprint_contract"] = {
        "scope": "x", "done_criteria": ["d"], "test_plan": ["t"],
        "accepted_by": "user", "accepted_at": "2026-04-08T00:00:00Z",
    }
    feat["lifecycle_state"] = "implementing"
    feat["change_spec"]["categories"] = ["backend"]
    state.write_text(json.dumps(data, indent=2))
    return state


def test_tick_emits_additional_context_for_pending_evaluator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _bootstrap(tmp_path)
    result = _run_driver(["tick"], cwd=tmp_path, stdin_payload="{}")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "additionalContext" in payload or "hookSpecificOutput" in payload
    raw = json.dumps(payload)
    assert "<wf-auto-instruction>" in raw
    assert "dispatch_evaluator" in raw


def test_gate_blocks_prog_done_when_evaluator_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _bootstrap(tmp_path)
    hook_input = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "prog done"},
    })
    result = _run_driver(["gate"], cwd=tmp_path, stdin_payload=hook_input)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    decision = payload.get("decision") or payload.get("hookSpecificOutput", {}).get("permissionDecision")
    assert decision in ("block", "deny")


def test_gate_allows_prog_done_when_all_gates_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = _bootstrap(tmp_path)
    data = json.loads(state.read_text())
    feat = data["features"][0]
    feat["quality_gates"]["evaluator"] = {"status": "pass", "score": 95, "defects": [], "last_run_at": "2026-04-08T00:00:00Z"}
    feat["quality_gates"]["reviews"] = {"required": ["eng"], "passed": ["eng"], "pending": []}
    feat["quality_gates"]["ship_check"] = {"status": "pass", "failures": [], "last_run_at": "2026-04-08T00:00:00Z"}
    state.write_text(json.dumps(data, indent=2))
    hook_input = json.dumps({"tool_name": "Bash", "tool_input": {"command": "prog done"}})
    result = _run_driver(["gate"], cwd=tmp_path, stdin_payload=hook_input)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    decision = payload.get("decision") or payload.get("hookSpecificOutput", {}).get("permissionDecision")
    assert decision in (None, "allow", "approve")


def test_auto_driver_respects_disable_env_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROG_AUTO_DRIVER", "0")
    _bootstrap(tmp_path)
    result = _run_driver(["tick"], cwd=tmp_path, stdin_payload="{}")
    assert result.returncode == 0
    assert result.stdout.strip() in ("", "{}")


def test_drive_cli_runs_one_tick_and_prints_action(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _bootstrap(tmp_path)
    pm = PLUGIN_ROOT / "hooks" / "scripts" / "progress_manager.py"
    result = subprocess.run(
        [sys.executable, str(pm), "drive", "--once"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "dispatch_evaluator" in result.stdout
```

- [ ] **Step 7.3.2: 红测**

### Task 7.4: 实现 wf_auto_driver.py

- [ ] **Step 7.4.1: Create `hooks/scripts/wf_auto_driver.py`**

```python
#!/usr/bin/env python3
"""WF auto-driver: hook entrypoint thin shell (PR-7).

Reads progress.json, calls wf_state_machine.compute_next_action(),
and emits hook JSON to stdout. Three subcommands:

  tick — Stop / UserPromptSubmit hook: emit additionalContext to nudge LLM
  gate — PreToolUse hook: block `prog done` if FSM says gates aren't ready
  print-action — debug helper: print Action for current feature

Respects PROG_AUTO_DRIVER=0 to disable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Allow running as a script
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import wf_state_machine
import progress_manager


def _disabled() -> bool:
    return os.environ.get("PROG_AUTO_DRIVER", "1") == "0"


def _current_feature() -> Optional[Dict[str, Any]]:
    try:
        data = progress_manager.load_progress_json()
    except Exception:
        return None
    fid = data.get("current_feature_id")
    if fid is None:
        return None
    for f in data.get("features", []):
        if f.get("id") == fid:
            return f
    return None


def _emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def cmd_tick() -> int:
    if _disabled():
        _emit({})
        return 0
    feat = _current_feature()
    if not feat:
        _emit({})
        return 0
    action = wf_state_machine.compute_next_action(feat)
    if action.kind == "noop":
        _emit({})
        return 0
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": action.to_additional_context(),
        }
    }
    _emit(payload)
    return 0


def cmd_gate() -> int:
    if _disabled():
        _emit({})
        return 0
    raw = sys.stdin.read() or "{}"
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        _emit({})
        return 0
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {}) or {}
    if tool_name != "Bash":
        _emit({})
        return 0
    cmd = tool_input.get("command", "") or ""
    if "prog done" not in cmd and "prog ship-check" not in cmd:
        _emit({})
        return 0

    feat = _current_feature()
    if not feat:
        _emit({})
        return 0
    action = wf_state_machine.compute_next_action(feat)

    # Allow only when FSM says complete_done and command is `prog done`,
    # or when FSM says run_ship_check and command is `prog ship-check`.
    if action.kind == "complete_done" and "prog done" in cmd:
        _emit({})  # allow
        return 0
    if action.kind == "run_ship_check" and "prog ship-check" in cmd:
        _emit({})
        return 0

    _emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"WF auto-driver blocked: feature {action.feature_id} requires "
                f"{action.kind} before this command. {action.prompt or action.blocked_reason or ''}"
            ),
        }
    })
    return 0


def cmd_print_action() -> int:
    feat = _current_feature()
    if not feat:
        print("no current feature")
        return 0
    action = wf_state_machine.compute_next_action(feat)
    print(json.dumps({
        "kind": action.kind,
        "feature_id": action.feature_id,
        "subagent_type": action.subagent_type,
        "lane": action.lane,
        "prompt": action.prompt,
        "blocked_reason": action.blocked_reason,
    }, indent=2))
    return 0


def main(argv: list) -> int:
    if not argv:
        print("usage: wf_auto_driver.py {tick|gate|print-action}", file=sys.stderr)
        return 2
    sub = argv[0]
    if sub == "tick":
        return cmd_tick()
    if sub == "gate":
        return cmd_gate()
    if sub == "print-action":
        return cmd_print_action()
    print(f"unknown subcommand: {sub}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 7.4.2: 在 progress_manager.py 加 `prog drive` CLI**

```python
def cmd_drive(once: bool = True) -> int:
    """PR-7: manual one-shot WF tick (调试或 hook 失效场景)."""
    import wf_auto_driver
    return wf_auto_driver.cmd_print_action()


# argparse:
sp_drive = subparsers.add_parser("drive", help="Manually tick the WF state machine")
sp_drive.add_argument("--once", action="store_true", default=True)
```

- [ ] **Step 7.4.3: 绿测**

```bash
pytest -q plugins/progress-tracker/tests/test_wf_auto_driver.py
```

### Task 7.5: 注册 hooks.json + run-hook.sh 路由

- [ ] **Step 7.5.1: 修改 `hooks/hooks.json`**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh check", "timeout": 30000},
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh sync-runtime-context --source session_start --quiet", "timeout": 5000},
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh git-sync-check", "timeout": 10000}
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh auto-checkpoint", "timeout": 5000},
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh wf-tick", "timeout": 5000}
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh wf-tick", "timeout": 5000}
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh wf-gate", "timeout": 5000}
        ]
      }
    ]
  }
}
```

- [ ] **Step 7.5.2: 在 `hooks/run-hook.sh` 加路由**

新增 case：

```bash
wf-tick)
    exec python3 "${SCRIPT_DIR}/scripts/wf_auto_driver.py" tick
    ;;
wf-gate)
    exec python3 "${SCRIPT_DIR}/scripts/wf_auto_driver.py" gate
    ;;
```

- [ ] **Step 7.5.3: 验证 hook JSON 合法性**

```bash
python3 -c "import json; json.load(open('plugins/progress-tracker/hooks/hooks.json'))"
```

### Task 7.6: SKILL.md 加 wf-auto-instruction 协议

- [ ] **Step 7.6.1: 修改 `skills/feature-implement/SKILL.md` + `skills/feature-complete/SKILL.md`**

在两个 SKILL.md 顶部（frontmatter 之后）加：

```markdown
## wf-auto-instruction protocol（PR-7 强制契约）

当上下文出现 `<wf-auto-instruction>...</wf-auto-instruction>` 标签，**必须立即解析并执行其中指令**，不得跳过、不得"等待用户进一步指示"。

支持的 `action`:
- `request_sprint_contract` → 立即调用 `superpowers:brainstorming` + `superpowers:writing-plans` 补 sprint_contract，写入 progress.json
- `dispatch_evaluator` → 立即用 `Agent` 工具 dispatch `subagent_type` 字段指定的 agent，执行 evaluator_gate.assess
- `dispatch_review_lane` → 立即 dispatch `subagent_type` 对应的 review subagent，跑完后调用 `review_router.mark_review_passed`
- `run_ship_check` → 立即跑 `prog ship-check --feature-id N`
- `complete_done` → 立即跑 `prog done`
- `await_user` → 报告 `blocked_reason` 给用户并停止

**理由**：FSM kernel 是程序裁判，wf-auto-instruction 是程序对 LLM 的硬指令。绕过它等于回到"LLM 自由调度"的失控模式（GSD V1 的失败模式）。
```

### Task 7.7: 端到端 smoke（手动验证自动 WF）

- [ ] **Step 7.7.1: smoke 步骤**

```bash
mkdir /tmp/wf-smoke && cd /tmp/wf-smoke
python3 plugins/progress-tracker/hooks/scripts/progress_manager.py init "WF Smoke"
python3 plugins/progress-tracker/hooks/scripts/progress_manager.py add-feature "Feature X" --test-steps "echo done"
python3 plugins/progress-tracker/hooks/scripts/progress_manager.py set-current 1

# 手动填 sprint_contract（端到端时由 LLM 看到 wf-auto-instruction 后自动填）
# ...

# 手动 tick FSM 看下一步
python3 plugins/progress-tracker/hooks/scripts/progress_manager.py drive --once
# 期望输出: {"kind":"dispatch_evaluator", ...}

# 模拟 hook input gate `prog done`
echo '{"tool_name":"Bash","tool_input":{"command":"prog done"}}' | \
  python3 plugins/progress-tracker/hooks/scripts/wf_auto_driver.py gate
# 期望: {"hookSpecificOutput":{"permissionDecision":"deny", ...}}
```

- [ ] **Step 7.7.2: 真实 Claude Code 端到端**

在 CC 内启动一个新 session：
1. `prog-init "WF Smoke"`
2. `prog add-feature "Feature X" --test-steps "echo done"`
3. `prog set-current 1`
4. **不发任何后续指令**，只观察：LLM 应当因 Stop hook 注入的 wf-auto-instruction 自动调用 brainstorming → 填 sprint_contract → dispatch evaluator subagent → dispatch review lanes → 跑 ship-check → 跑 prog done
5. 验证 `audit.log` 每一步都有事件
6. 验证 `feature.lifecycle_state` 最终到 `archived`

- [ ] **Step 7.7.3: Commit**

```bash
git add -A
git commit -m "feat(progress-tracker): add WF auto-driver with FSM kernel and hook-driven self-running workflow (PR-7)"
```

### PR-7 验收

| 检查 | 命令 | 期望 |
|---|---|---|
| FSM 单元 | `pytest -q tests/test_wf_state_machine.py` | 9 passed |
| auto_driver 单元 | `pytest -q tests/test_wf_auto_driver.py` | 5 passed |
| hooks.json 合法 | `python3 -c "import json;json.load(open('hooks/hooks.json'))"` | 无报错 |
| `prog drive --once` | 当前 feature 应输出对应 Action | 手动 |
| 自动 WF 端到端 | 在新 CC session 内启动 feature 后不发指令，feature 自动跑到 archived | 手动 |
| 逃生门 | `PROG_AUTO_DRIVER=0` 时 `prog done` 不被 hook 拦截 | 手动 |
| 回归 | `pytest -q tests/` | 全绿 |

---

## 累积验收（所有 7 个 PR 合并后）

### 全量测试

```bash
pytest -q plugins/progress-tracker/tests/
```

预期：全部 passed，包括：
- 原有测试文件（无回归）
- `test_command_discovery_contract.py`（PR-1，3 tests）
- `test_feature_contract_readiness.py`（PR-1+PR-2，含 finish_pending 阻断）
- `test_set_finish_state_cli.py`（PR-2，4 tests）
- `test_schema_2_1_migration.py`（PR-3 prep，5 tests）
- `test_evaluator_gate.py`（PR-3，6 tests）
- `test_review_router.py`（PR-4，8 tests）
- `test_ship_check.py`（PR-5，6 tests）
- `test_sprint_ledger.py`（PR-6，6 tests）
- `test_wf_state_machine.py`（PR-7，9 tests）
- `test_wf_auto_driver.py`（PR-7，5 tests）

### 端到端 smoke（手动）

```bash
# 在临时目录
cd /tmp/prog-smoke && python -m progress_manager init "Smoke"
python -m progress_manager add-feature "Auth rewrite" --test-steps "pytest tests/auth"
python -m progress_manager set-current 1
# 期望：features[0].quality_gates.reviews.required 已被 review_router 初始化

# 模拟 generator 完成，跑独立 evaluator subagent
python -c "
from evaluator_gate import assess
from progress_manager import _store_evaluator_result
r = assess(feature={'id':1,'name':'Auth rewrite'},
           rubric={'test_coverage_min':0.8,'require_changelog':False},
           signals={'test_coverage':0.95,'defects':[]})
_store_evaluator_result(1, r)
"
# 跑 ship_check
python -m progress_manager ship-check --feature-id 1
# 只有 ship_check pass 才能进 done
python -m progress_manager done
```

### 契约 grep（PR-1 锁定）

```bash
rg -n "/prog-start|prog-start.md" plugins/progress-tracker/docs plugins/progress-tracker/tests docs/progress-tracker/architecture/architecture.md
```

预期残留命中：
- `architecture.md` ADR 段
- `plugins/progress-tracker/docs/progress-tracker/state/*` 历史快照
- `tests/test_command_discovery_contract.py::test_prog_start_command_is_not_reintroduced` 反向断言

### 回归矩阵

| 原有命令 | 预期行为（不应有行为变化） |
|---|---|
| `/prog-init` | 正常初始化，新 progress.json schema_version=2.1 |
| `/prog-next` | 正常选 feature，新字段被 `initialize_reviews` 自动填充 |
| `/prog-done` | 如果 evaluator/reviews/ship_check 都 pass，正常走完完成流程；否则阻断并告知具体门 |
| `/prog-update` | 不受影响 |
| `/prog-sync` | 不受影响 |
| `/prog-ui` | 新字段可被读到，dashboard 可渲染 quality_gates 矩阵（PR-4 借机扩展） |
| `/prog-fix` | 不受影响 |

---

## Delivery Sequence 与 Dependencies

```
PR-1 (cleanup)
   └──> PR-2 (set-finish-state CLI; depends on PR-1 clean slate)
           └──> PR-3 (evaluator_gate + schema 2.1; depends on PR-2 resolver + 稳定 CLI 骨架)
                   ├──> PR-4 (review_router; depends on PR-3 schema 2.1 字段)
                   │       └──> PR-5 (ship_check; depends on PR-4 reviews 数据)
                   └──> PR-6 (sprint_ledger; depends on PR-3 schema 2.1 字段，但与 PR-4/PR-5 平行)
                           └──> PR-7 (auto-driver; depends on PR-3~PR-6 全部数据契约就绪)

推荐顺序：PR-1 → PR-2 → PR-3 → PR-6 → PR-4 → PR-5 → PR-7

理由：
1. PR-6 的 sprint_contract 校验是所有其他 gate 的逻辑前置，先做 PR-6 让 PR-4/PR-5 的 cmd_done 前置门统一设计。
2. PR-7 必须**最后**做：FSM kernel 的 compute_next_action 需要读所有 quality_gates 字段，
   只有 PR-3/4/5/6 全部就绪后 PR-7 才有"东西可推进"。
3. PR-7 是从"半自动"→"全自动"的临门一脚——单独 revert PR-7 即可回退到 PR-6 终态而不损失任何数据契约。
```

---

## Risks & Rollback

### 风险

1. **schema 2.1 升级全局影响**：所有 feature 首次加载会被 backfill。缓解：`PROG_DISABLE_V2=1` 逃生门 + `audit.log` 记录迁移事件 + `test_schema_2_1_migration.py` 覆盖往返一致性。
2. **cmd_done 前置门过多导致卡死**：每次新增 gate 都在 `cmd_done` 加一道 `return N`。缓解：每个 gate 的错误消息必须明确给出 `prog <subcommand>` 恢复动作，且返回码分散（6/7/8/9）便于脚本识别。
3. **subagent generator/evaluator 上下文污染**：PR-3 要求独立 subagent，但 skill 只能“指导”而无法强制。缓解：skill 内在 Step Y 明确写 `Use the Agent tool with subagent_type=code-reviewer (fresh context)`；同时 `evaluator_gate.assess` 自身是纯函数，可在 subagent 外也能跑出同样结果，只是少了独立性保证。PR-7 的 wf-auto-instruction 协议进一步把 dispatch 指令从"建议"变成"硬规则"。
4. **sprint_ledger.jsonl 文件无上限增长**：append-only 长期会变大。缓解：本 PR 不实现 rotation；在文件头注释标注“每 1000 条由未来 PR 实现 rotation”。
5. **gstack 映射偏差**：gstack 真实语义可能与推测有差异。缓解：PR-4/PR-5 的 lane / docs-sync 检查都是 progress-tracker 自身定义，gstack 只是灵感来源，不存在 1:1 绑定。
6. **PR-7 hook 副作用范围过大**：PreToolUse hook 拦截所有 `Bash` 调用、Stop hook 在每次 LLM 结束 turn 时跑——hook 异常会拖慢整个 session。缓解：(a) hook 入口零依赖且 try/except 兜底（异常时返回 `{}` 让流程继续）；(b) `PROG_AUTO_DRIVER=0` 一键关闭；(c) hook 超时 5s；(d) `tests/test_wf_auto_driver.py` 必须覆盖"无 progress.json"和"损坏 progress.json"的兜底路径。
7. **wf-auto-instruction 被 LLM 忽略**：CC 不能强制 LLM 执行 additionalContext 里的指令。缓解：(a) skill 顶部的协议是硬约束；(b) PreToolUse 硬门禁兜底——即使 LLM 忘了 tick，用户尝试 `prog done` 也会被拦下并强推回正确路径；(c) `audit.log` 记录"action 是否被执行"，便于事后审计 LLM 服从度。
8. **FSM 状态空间错估**：feature 可能进入 FSM 没覆盖的组合（如 evaluator=pass + reviews 字段缺失）。缓解：FSM kernel 测试用 `_base_feature` fixture 列举所有合法组合；任何 KeyError 都应被 try/except 兜底为 `Action(kind="noop")` 而不是崩溃。

### Rollback

每个 PR 独立 commit，可以单独 `git revert`。

**PR-7 单独回滚（最常见）**：直接 `git revert <PR-7 commit>` 即可。FSM kernel + auto-driver 是纯增量，不动 `progress.json` 任何数据；hook 注册只动 `hooks.json`，revert 后 hook 自动失效。无需任何数据迁移。

**PR-3~PR-6 数据契约回滚**（schema 2.1 → 2.0）：
1. `git revert` PR-3 schema 升级 commit
2. 手动运行：`python -c "import progress_manager; data=progress_manager.load_progress_json(); data['schema_version']='2.0'; progress_manager.save_progress_json(data)"`
3. `PROG_DISABLE_V2=1` 运行所有后续命令直到确认没有新字段依赖

**逃生门优先于 revert**：先用 `PROG_AUTO_DRIVER=0` 和 `PROG_DISABLE_V2=1` 验证问题是否消失；只有逃生门无法解决才走 revert。

---

## Non-Goals（再次重申，防止 scope creep）

1. **不实现 gstack `/office-hours` 六个 forcing questions**——属于 Phase-2 候选，本次不触碰。
2. **不实现 gstack 的 Conductor 并行 10-15 sprint**——多 session 并行工作流归属另一个架构 RFC。
3. **不实现 gstack `/land-and-deploy`**——部署是业务侧，progress-tracker 只管到 archive-capable。
4. **不替换 superpowers 集成**——`feature-implement` 继续 delegate 到 brainstorming / writing-plans / subagent-driven-development / executing-plans。
5. **不新增独立 `transaction_manager.py` 文件**——`progress_transaction()` 已内联在 `progress_manager.py` 中足够用，强行提取会引入循环引用风险。
6. **不动 `architecture.md`**——所有 `/prog-start` 提及均为有意保留的 ADR。
7. **不动历史 state 快照**——`plugins/progress-tracker/docs/progress-tracker/state/*.json` 是历史 sprint 记录，改写会破坏审计一致性。
8. **不实现 `/prog-ui` dashboard 的 quality_gates 矩阵渲染**——虽然 gstack Readiness Dashboard 是亮点，但作为独立改进放到 PR-4 或 Phase-2。本次只保证数据结构可被渲染。

---

## 附录 A: Key 文件路径速查

| 文件 | 角色 | PR |
|---|---|---|
| `plugins/progress-tracker/hooks/scripts/progress_manager.py` | 状态内核 + CLI dispatch（6274 行） | PR-2~PR-6 修改 |
| `plugins/progress-tracker/hooks/scripts/lifecycle_state_machine.py` | 生命周期状态转换 | 不修改（已存在） |
| `plugins/progress-tracker/hooks/scripts/contract_importer.py` | 自动导入 feature contract | 不修改 |
| `plugins/progress-tracker/hooks/scripts/evaluator_gate.py` | **新**：独立评估 | PR-3 |
| `plugins/progress-tracker/hooks/scripts/review_router.py` | **新**：review lane 路由 | PR-4 |
| `plugins/progress-tracker/hooks/scripts/ship_check.py` | **新**：ship 前统一门禁 | PR-5 |
| `plugins/progress-tracker/hooks/scripts/sprint_ledger.py` | **新**：sprint artifact + handoff | PR-6 |
| `plugins/progress-tracker/skills/feature-complete/SKILL.md` | `/prog-done` workflow | PR-3/4/5/6 修改 |
| `plugins/progress-tracker/skills/feature-implement/SKILL.md` | `/prog-next` workflow | PR-6 修改 |
| `docs/progress-tracker/architecture/architecture.md` | 全局架构权威 | **不修改** |

## 附录 B: gstack 参考清单

| gstack 特性 | 借鉴到 | 本次是否实现 |
|---|---|---|
| `Think → Plan → Build → Review → Test → Ship → Reflect` 宏 workflow | progress-tracker 现有 `/prog-init → /prog-plan → /prog-next → /prog-done` 骨架 | 已有 |
| `/office-hours` think 阶段 | — | **否**（Phase-2） |
| `/plan-ceo-review` / `/plan-eng-review` / `/plan-design-review` / `/plan-devex-review` | `review_router` 的 lane 集合 | **是（PR-4）** |
| `/review` 独立 staff-engineer 审计 | `evaluator_gate` | **是（PR-3）** |
| `/qa` 浏览器测 | 现有 `_run_acceptance_tests` | 已有 |
| `/ship` sync+test+coverage audit+push+PR | `ship_check` | **是（PR-5）** |
| `/document-release` 被 `/ship` 自调 | `ship_check._check_docs_sync` 子检查 | **是（PR-5）** |
| `/land-and-deploy` | — | **否** |
| `/retro` | 现有 `add_retro` | 已有 |
| Skill-to-skill artifact handoff | `sprint_ledger.record` + `feature.handoff` | **是（PR-6）** |
| `.gstack/` 每项目 state | `docs/progress-tracker/state/` | 已有 |
| `$B handoff` / `$B resume` browser 交接 | — | **否** |
| Conductor 并行 10-15 sprint | — | **否**（Phase-2） |
| Review Readiness Dashboard | `/prog-ui` 渲染 `quality_gates` 矩阵 | **数据就绪，UI 延后** |

## 附录 C: Anthropic Harness 映射

| Anthropic 原语 | progress-tracker 对应 | PR |
|---|---|---|
| planner | `architectural-planning` skill + `/prog-plan` | 已有 |
| generator | `feature-implement` skill + `/prog-next` | 已有 |
| evaluator | `evaluator_gate.assess()` + 独立 subagent | **PR-3 新增** |
| sprint contract | `features[].sprint_contract` | **PR-6 新增** |
| handoff artifact | `features[].handoff` + `sprint_ledger.jsonl` | **PR-6 新增** |

---

## 附：关于 GSD V2 状态机能否在 Claude Code 落地（策略性讨论保留）

GSD V2 引入“显式状态机 + 启动新阶段时清空 section 保持上下文干净 + 用 Pydantic SDK 简单原子动作串联 workflow”，本质上是把“LLM 自由调度”改成“程序调度 + LLM 在节点内只做局部判断”。**思路可参考、与本次 Hybrid Phase-1 方向完全一致**。

| GSD V2 机制 | Claude Code 可用能力 | 本计划对应 PR |
|---|---|---|
| 固定 workflow / 状态机 | Slash commands + skills checklist + plan mode | `prog-init → prog-next → prog-done` 已是骨架；PR-3~6 的 `cmd_done` 前置门把骨架变门禁 |
| 启动新阶段时清空 section | Subagent dispatch（每阶段 fresh agent，独立上下文） | PR-3 evaluator_gate 必须在 fresh subagent 跑；PR-6 sprint_ledger 用文件 artifact 而非对话记忆 |
| 节点级原子动作 | Read / Edit / Bash + settings.json tool 限制 | 未在本 PR 实施 tool 限制，归 Phase-2 |
| 程序化状态控制 | Hooks (Session/UserPrompt/PreTool/PostTool/Stop) + progress.json 字段 | PR-5 ship_check 是程序化门；cmd_done 门禁链条是程序化状态机 |
| LLM 只做当前节点核心任务 | Plan mode + TodoWrite + subagent isolation | 本计划本身就是写给 subagent 逐 task 执行的 |

**Claude Code 与 GSD V2 的真实差距**（无法在本 PR 消除）：

1. Claude Code **没有原生 FSM kernel**——最终消息路由仍由 LLM 决定；本计划用 hooks/skills/门禁 “围栏” 它，而不是“强制” 它。
2. **没有 Pydantic SDK 风格的 workflow 串联 DSL**——本计划用 CLI 子命令 + 前置门 `return N` 的方式拼图。
3. **subagent 清空 section 是真清空**——本计划 PR-3/PR-6 把这一点当设计点而非 workaround。

**对本计划的具体借鉴落地：**

- PR-3 evaluator_gate **必须**在独立 subagent 跑——这是 GSD V2 “节点隔离” 与 Anthropic harness 的共同结论。
- PR-6 sprint_contract + handoff 使用**文件路径**作为 artifact 载体——这是 GSD V2 “workflow 之间通过 artifact 传递” 的 Claude Code 对应。
- PR-5 ship_check 统一阻断——`return 8` 是 GSD V2 “程序化门” 的 argparse 等价。
- cmd_done 的多重前置门（finish_pending → evaluator → reviews → ship_check → sprint_contract）构成一个事实上的 “准 FSM”：每道门都是纯检查，LLM 无法绕过（除非跳过 `prog done` 直接改 progress.json，但那会被 transaction_manager 审计记录）。
