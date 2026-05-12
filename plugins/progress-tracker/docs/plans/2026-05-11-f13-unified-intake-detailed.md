# F13 详细实施计划 v3：统一工作项 intake 与优先级路由

**Feature**: PT-F13 — Unified work-item intake and profile routing (task/feature/bug) via /prog next  
**Bucket**: standard | **Model**: sonnet | **Workflow**: plan_execute  
**Created**: 2026-05-11 | **Revised**: 2026-05-12 v3  
**Goal:** Introduce prog smart CLI as deterministic executor with work-item taxonomy, workflow_profile, and unified routing via prog next.  
**Architecture:** Skill layer handles classification; CLI layer is deterministic executor; smart --commit wraps writes in progress_transaction().

---

## 目标

1. 引入 `prog smart` CLI 命令：**确定性 executor**，接收 AI/skill 层传来的分类结果后做 preview 或 commit
2. 定义 work-item taxonomy（epic|feature|task|bug|spike|risk|decision|update）和 `workflow_profile` 字段
3. bug intake 写入后同步推 bug-id 进 routing_queue（P0/P1/P2 权重排序）
4. `prog next` / `prog next-feature` 扩展为统一工作项视图：P0>P1>task>feature_task>P2
5. 扩展 `wf_state_machine.py` 覆盖 task 生命周期状态

---

## 设计原则（来自冻结约束）

- `progress_manager.py` = 确定性 executor：接收明确 type/profile/candidate 参数，不做 keyword 推断
- 分类逻辑 100% 归 skill/AI 层（`skills/prog-smart/`）；CLI 只执行已分类的结果
- `smart --commit` 是 mutating path → 必须走 `progress_transaction()`
- `smart`（无 `--commit`）= preview only，zero mutation

---

## Feature Contract 要求（来自 progress.json 行 1499–1561）

```
line 1499: Define work-item taxonomy: epic|feature|task|bug|spike|risk|decision|update
line 1504: Add workflow_profile field to tasks + features; values: quick_task|standard_task|feature_delivery|hotfix; default: standard_task
line 1505: Bug intake → push bug-id into routing_queue with priority weight (P0=critical, P1=high, P2=normal)
line 1556: F13 contract doc defines candidate→confirm→commit flow with fail-closed ambiguity handling
line 1560: workflow_profile field exists on work-item records with documented values + default=standard_task
line 1561: Bug intake writes to routing_queue; prog next surfaces P0 bugs above standalone tasks
line 1623: workflow_profile taxonomy, schema extension, and intake contract must be merged before F14
```

---

## 验收测试步骤（来自 progress.json test_steps）

1. `prog smart --candidate-json '<json>'` → 展示候选（type/confidence/profile 字段从 JSON 读取）；**不写 JSON**
2. `prog smart --candidate-json '<ambiguous-json>'`（confidence < 0.6 且无 `--commit`）→ 打印恰好一个澄清提示；无写入
3. `prog smart --candidate-json '<bug-json>' --commit` → bug 写入 bugs[]，routing_queue 包含新 BUG-id，优先级权重正确
4. `prog next` → P0 bug 在 standalone task 之上；顺序符合 P0>P1>task>feature_task>P2
5. `prog add-feature / add-bug / add-update` → 无回归；/prog-fix 契约不变

**命令名说明**：验收步骤写 `prog next`；CLI 实现需同时支持 `next-feature`（现有）和 `next`（新别名）。

---

## 数据模型变更

### A. work-item taxonomy 常量（新增）
```python
WORK_ITEM_TAXONOMY = frozenset([
    "epic", "feature", "task", "bug", "spike", "risk", "decision", "update"
])

WORKFLOW_PROFILE_VALUES = frozenset([
    "quick_task", "standard_task", "feature_delivery", "hotfix"
])
WORKFLOW_PROFILE_DEFAULT = "standard_task"
```

### B. workflow_profile 字段注入
- `tasks[]` 新条目：默认 `workflow_profile = "standard_task"`
- `features[]` 现有条目：backfill 迁移时不自动注入（avoid breaking existing tests）；新 feature 创建时 `add_feature()` 可接受 `workflow_profile` 可选参数（默认 `"feature_delivery"`）

### C. tasks[] schema（新增字段）
```json
"tasks": [
  {
    "id": "TASK-001",
    "type": "task",
    "description": "...",
    "workflow_profile": "standard_task",
    "status": "pending",
    "priority": "P1",
    "details": "",
    "refs": [],
    "next_action": "",
    "created_at": "2026-05-11T..."
  }
]
```

### D. routing_queue BUG-* 扩展
- 格式保持字符串：`["PT", "ROOT", "BUG-001"]`（BUG-* 前缀识别）
- `BUG-*` 条目按 priority 权重插入：P0 插在第一个非 P0 条目前，P1/P2 类推
- `_get_dispatched_child_feature()` 不改动（不感知 BUG-*）
- 新增 `_select_next_work_item()` 统一选择器（见下）

---

## 统一选择器：_select_next_work_item()

替代 `next_feature()` 中 parent dispatch + 直接 feature 返回的逻辑：

```python
def _select_next_work_item(data, project_root, repo_root):
    """
    优先级顺序选择下一个工作项：
      P0 bug > P1 bug > standalone task > feature_task > P2 bug

    routing_queue 扫描顺序：
      - BUG-<N>  → 在 bugs[] 中查找；跳过 fixed/false_positive/已在 active_route
      - ROOT     → root-level 未完成 feature（已有逻辑）
      - <code>   → child project dispatch（已有逻辑）

    tasks[] 扫描：routing_queue 中未出现的 pending task，
    优先级低于所有 bug，高于 feature_task。
    """
```

测试覆盖：
- BUG-* 在队列中 → 正确返回 bug workitem
- ROOT + BUG-* 混排 → P0 bug 排在 ROOT feature 之前
- active_route conflict → BUG-* 被 active bug 冲突时跳过（仅当 route status 非 done/cancelled）
- fixed/false_positive bug → 跳过，不阻塞队列
- queue 全空 → fallback 到 tasks[]
- tasks[] 全空 → fallback 到 get_next_feature()

---

## wf_state_machine.py 扩展

新增 task 生命周期状态映射（工作流层面，不是 bug 状态）：

```python
# 新增 work-item intake flow 状态
"intake:pending"    → "classify_with_ai"
"intake:classified" → "confirm_or_clarify"
"intake:confirmed"  → "commit_work_item"
"intake:committed"  → "route_to_queue"

# 新增 task lifecycle 状态（供 F14 使用，F13 定义常量）
"task:pending"      → "start_task"
"task:active"       → "complete_task"
"task:done"         → None
```

**范围说明**：F13 在 `wf_state_machine.py` 中定义常量和状态图；F14 接入执行语义。

---

## Tasks

### T1: 写测试 RED — test_smart_intake.py
文件：`plugins/progress-tracker/tests/test_smart_intake.py`

测试场景：
- `test_smart_preview_no_mutation` — `prog smart --candidate-json ...` 无 `--commit`，type 从 JSON 读取 → JSON 不变
- `test_smart_ambiguous_no_mutation` — `confidence < 0.6` 无 `--commit` → 输出澄清提示，JSON 不变
- `test_smart_commit_bug_writes_bugs` — `--commit` → bugs[] 增一条
- `test_smart_commit_bug_routing_queue` — `--commit bug` → routing_queue 含 "BUG-NNN"，priority 权重正确
- `test_smart_commit_task_writes_tasks` — `--commit task` → tasks[] 增一条，含 workflow_profile
- `test_smart_commit_feature_writes_features` — `--commit feature` → features[] 增一条
- `test_smart_commit_update_calls_add_update` — `--commit update` → updates[] 增一条（需传 category + summary）
- `test_workflow_profile_default` — 新建 task 默认 workflow_profile=standard_task

### T2: 写测试 RED — test_unified_selection.py
文件：`plugins/progress-tracker/tests/test_unified_selection.py`

测试场景：
- `test_p0_bug_above_feature_in_queue`
- `test_p1_bug_above_standalone_task`
- `test_standalone_task_above_feature_task`
- `test_fixed_bug_skipped`
- `test_active_route_conflict_skipped`
- `test_routing_queue_mixed_codes_and_bugs`
- `test_fallback_to_tasks_when_queue_empty`
- `test_fallback_to_feature_when_tasks_empty`

### T3: 数据模型 GREEN
文件：`plugins/progress-tracker/hooks/scripts/progress_manager.py`

- 添加 `WORK_ITEM_TAXONOMY`、`WORKFLOW_PROFILE_VALUES`、`WORKFLOW_PROFILE_DEFAULT` 常量
- `load_progress_json()` 下游确保 `data.setdefault("tasks", [])`
- 修改 `add_bug()` 返回值：保持 `bool` 外部签名；内部重构为 `_add_bug_internal()` 返回 `(bool, Optional[str])` 即 (success, bug_id)；`add_bug()` 调用 `_add_bug_internal()` 包装，确保向后兼容
- 新增 `add_task_item(description, details="", refs=None, next_action="", priority="P1", workflow_profile=WORKFLOW_PROFILE_DEFAULT)` → 写入 tasks[]，返回 task_id

### T4: routing_queue BUG-* 注入 GREEN
文件：`plugins/progress-tracker/hooks/scripts/progress_manager.py`

新增 `_push_bug_to_routing_queue(data, bug_id, priority_tier)`：
- 按 P0>P1>P2 权重，将 bug_id 插入 routing_queue 正确位置
- 跳过已存在的相同 bug_id（幂等）
- priority_tier 映射：`{"high": "P0", "medium": "P1", "low": "P2"}`

在 `smart --commit bug` 路径中：
1. 调用 `_add_bug_internal()` 得到 bug_id
2. 调用 `_push_bug_to_routing_queue(data, bug_id, priority)`
3. 整体包在 `with progress_transaction():` 内

### T5: 统一选择器 GREEN
文件：`plugins/progress-tracker/hooks/scripts/progress_manager.py`

新增 `_select_next_work_item(data, project_root, repo_root)` 函数：
- 扫描 routing_queue（BUG-* → bugs[]；ROOT → root features；code → child dispatch）
- fallback：tasks[] → get_next_feature()
- 返回统一结构：`{"item_type": "bug|task|feature|child", "id", "name", "priority_tier", "action"}`

修改 `next_feature()` parent dispatch 分支：改用 `_select_next_work_item()` 替代当前 `_get_dispatched_child_feature()` 直接调用；保留所有现有输出字段（不破坏 JSON 输出格式）。

新增 `next` 命令别名：
```python
subparsers.add_parser("next", help="Alias for next-feature")
```
在 main dispatch 中：`if args.command in ("next", "next-feature"):`

### T6: prog smart 命令 GREEN
文件：`plugins/progress-tracker/hooks/scripts/progress_manager.py`

新增 `smart_intake(candidate_json, commit, workflow_profile)` 函数（无 `item_type` 参数，type 从 JSON 读取）：
```
1. 解析 candidate_json（validate: type ∈ WORK_ITEM_TAXONOMY, confidence ≥ 0, profile.description 非空）
2. 无 --commit（preview 模式）：
   - 打印候选展示（type / confidence / profile 字段）
   - 若 confidence < 0.6：打印恰好一条澄清问题，不写 JSON
   - 直接返回，零副作用（不走 preflight，不加锁）
3. 带 --commit <type>（commit 模式，在 main dispatch 中按 args.commit 分支执行）：
   - 先执行 route preflight 检查（与其他 mutating 命令一致）
   - 再用 with progress_transaction(): 包裹写入：
     - bug → _add_bug_internal() + _push_bug_to_routing_queue()
     - task → add_task_item()
     - feature → add_feature()（传 workflow_profile）
     - update → add_update(category=..., summary=profile["description"], ...)
```

**事务边界规则（main dispatch）：**
```python
if args.command == "smart":
    if args.commit:
        # 只有 commit 分支走 mutating 路径
        _run_preflight_if_needed()          # 与其他 mutating 命令一致
        return smart_intake(..., commit=args.commit, ...)
    else:
        # preview 分支：不走 MUTATING_COMMANDS preflight，不加锁
        return smart_intake(..., commit=None, ...)
```

**`smart` 不加入 `MUTATING_COMMANDS` 常量集合**，避免 preview 误触 preflight 以及 `progress_transaction()` 嵌套锁风险（smart_intake 内部已按 commit 分支选择性加锁）。

`add_update()` 调用需传 `category` 和 `summary`（从 profile 中提取）：
- `category` 默认 `"status"`（UPDATE_CATEGORIES = status|decision|risk|handoff|assignment|meeting，`"progress"` 不合法）
- skill 层可在 candidate JSON 的 `profile.category` 字段传入合法值；CLI 校验，非法时 fallback 到 `"status"`
- `summary` 来自 `profile["description"]`
- **回归测试**：T1 补充 `test_smart_commit_update_valid_category`，验证非法 category 自动 fallback 到 `"status"` 并写入成功

命令注册：
```python
smart_parser = subparsers.add_parser("smart", help="Deterministic work-item intake executor")
smart_parser.add_argument("--candidate-json", required=True)
smart_parser.add_argument("--commit", choices=["bug", "feature", "task", "update"])
smart_parser.add_argument("--priority", choices=["P0", "P1", "P2"], default="P1")
smart_parser.add_argument("--workflow-profile", choices=list(WORKFLOW_PROFILE_VALUES),
                          default=WORKFLOW_PROFILE_DEFAULT)
```

### T7: wf_state_machine.py 扩展 GREEN
文件：`plugins/progress-tracker/hooks/scripts/wf_state_machine.py`

新增 intake flow 和 task lifecycle 状态映射：
```python
"intake:pending"    → "classify_with_ai"
"intake:classified" → "confirm_or_clarify"
"intake:confirmed"  → "commit_work_item"
"intake:committed"  → "route_to_queue"
"task:pending"      → "start_task"
"task:active"       → "complete_task"
"task:done"         → None
```

### T8: 命令文档 + skill 文件 GREEN

文件 1：`plugins/progress-tracker/commands/prog-smart.md`
```markdown
---
name: prog-smart
description: AI-first work-item intake routing. Classify intent with AI, then commit via prog smart --commit.
---

/progress-tracker:prog-smart
```

文件 2：`plugins/progress-tracker/skills/prog-smart/SKILL.md`
```
---
name: prog-smart
description: Route work-item intake: use haiku to classify text, then call prog smart --commit
---

# prog-smart intake flow
1. Call haiku to classify user's text → get {type, confidence, profile}
2. If confidence ≥ 0.6: call prog smart --candidate-json ... --commit <type>
3. If confidence < 0.6: ask ONE clarification question, then re-classify
4. Never write JSON without explicit --commit
```

文件 3：更新 `docs/PROG_COMMANDS.md` 添加 `prog smart` 条目

### T9: 全测试 GREEN
```bash
pytest plugins/progress-tracker/tests/test_smart_intake.py -v
pytest plugins/progress-tracker/tests/test_unified_selection.py -v
pytest plugins/progress-tracker/tests/ -q --tb=short
```
目标：926 + 新增测试全部通过。

---

## 调用契约修正（解决反馈问题）

| 问题 | 修正方案 |
|------|---------|
| `add_bug()` 返回 bool，不返回 bug_id | 重构为 `_add_bug_internal()` 返回 `(bool, bug_id)`；`add_bug()` 保持 bool 向后兼容 |
| `add_update()` 需要 category + summary | `smart --commit update` 从 profile 提取 `category`（默认 "status"）和 `summary`（来自 description） |
| `add_feature()` profile/test_steps 默认 | `smart --commit feature` 传 `workflow_profile` 参数；test_steps 默认 `[]`（空列表） |
| `smart --commit` 事务边界 | `smart` **不加入** `MUTATING_COMMANDS`；main dispatch 按 `args.commit` 分支：commit 分支走 preflight + `progress_transaction()`；preview 分支零副作用直接返回，避免嵌套锁 |
| 命令名 `prog next` vs `next-feature` | 新增 `next` 别名；`next_feature()` dispatch 改为 `if args.command in ("next", "next-feature"):` |

---

## 文件影响清单

| 文件 | 变更类型 |
|------|---------|
| `hooks/scripts/progress_manager.py` | 新增：constants, smart 命令, add_task_item, _add_bug_internal, _push_bug_to_routing_queue, _select_next_work_item, `next` 别名；修改：next_feature dispatch |
| `hooks/scripts/wf_state_machine.py` | 新增：intake flow + task lifecycle 状态映射 |
| `tests/test_smart_intake.py` | 新建（TDD） |
| `tests/test_unified_selection.py` | 新建（TDD） |
| `commands/prog-smart.md` | 新建 |
| `skills/prog-smart/SKILL.md` | 新建 |
| `docs/PROG_COMMANDS.md` | 更新 |

共 7 个文件（2 新测试、1 新 skill、1 新命令、2 现有修改、1 现有更新）。

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| routing_queue BUG-* 破坏 child dispatch | `_select_next_work_item()` 隔离 BUG-* 处理；`_get_dispatched_child_feature()` 不改动 |
| `next_feature()` 输出格式变更 | 保持所有现有 JSON 字段；新增 `item_type` / `priority_tier` 字段（追加，不替换） |
| `add_bug()` 返回值重构 | 双层函数（internal + public wrapper）；现有测试验证 bool 返回不变 |
| `add_update()` category 默认值 | 使用 `"status"` 作为默认 category（已在 UPDATE_CATEGORIES 中） |
| wf_state_machine.py 扩展副作用 | 新状态不覆盖现有状态；`compute_next_action()` 对未知 phase 返回 None（已有行为） |

---

## 非目标（本功能不包含）

- CLI 层关键词推断/heuristic 分类（归 skill 层）
- F14 task 执行语义（lifecycle 执行 + worktree）
- backfill 存量 features 的 workflow_profile 字段
- 修改 `_get_dispatched_child_feature()` 内部逻辑
