# Progress Tracker Hybrid Phase-1 Executable Revision Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以可执行、可回滚、可验证的方式完成 Hybrid Phase-1 更新，修复原计划中的命令不兼容、路径不可执行、门禁语义冲突与一致性风险。

**Architecture:** 保持 `progress_manager.py` 为状态内核与事务入口；增量引入 `evaluator_gate/review_router/ship_check/sprint_ledger/wf_state_machine/wf_auto_driver`。所有状态变更经 `progress_transaction()` 串行化，跨文件写入（如 `sprint_ledger.jsonl`）明确为“串行一致性”而非“跨文件原子事务”。

**Tech Stack:** Python 3 标准库、pytest、argparse、现有 hooks 机制。

---

## 0. 执行前硬约束（替换原稿中的歧义）

- 所有命令默认在仓库根目录执行：`/Users/siunin/Projects/Claude-Plugins`。
- 统一用 `plugins/progress-tracker/prog ...` 调用 CLI（避免 `python -m progress_manager` 不可用问题）。
- `add-feature` 使用**位置参数**，不是 `--test-steps`：
  - 正确：`plugins/progress-tracker/prog add-feature "Feature X" "echo done"`
- “兼容性声明”修正：
  - `/prog-next` 和 `/prog-done` 将新增阻断逻辑，属于**受控行为变化**，不再宣称“零行为变化”。
- 子代理调度不绑定不存在的固定角色名（如 `code-reviewer`）。统一写为：
  - “dispatch fresh review subagent with lane-specific prompt”。

---

## 1. 基线校验（必须先跑）

**Task 1: 验证当前基线与已知失败点**

**Files:**
- Read-only

- [ ] **Step 1.1: 跑当前已知红测**

```bash
pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py
```

预期：`test_core_progress_commands_remain_discoverable` 因 `prog-start.md` 断言失败。

- [ ] **Step 1.2: 校验 CLI 语法现实**

```bash
plugins/progress-tracker/prog add-feature --help
```

预期：仅 `name test_steps...` 位置参数，无 `--test-steps`。

- [ ] **Step 1.3: 记录基线**

把以上结果写入 PR-1 描述，作为回归对照。

---

## 2. PR-1 清理 `/prog-start` 契约残留

**Goal:** 解锁当前红测，明确 `/prog-next` 是唯一起点。

**Files:**
- Modify: `plugins/progress-tracker/tests/test_command_discovery_contract.py`
- Modify: `plugins/progress-tracker/tests/test_feature_contract_readiness.py`

- [ ] **Step 2.1: 删除 discoverable 期望里的 `prog-start.md` 并新增反向守卫测试**

新增：

```python
def test_prog_start_command_is_not_reintroduced():
    assert not (COMMANDS_DIR / "prog-start.md").exists()
```

- [ ] **Step 2.2: 修正文案（`/prog-start` -> `/prog-next`）**

`test_feature_contract_readiness.py` 第 103 行 docstring 改为 `/prog-next`。

- [ ] **Step 2.3: 验证**

```bash
pytest -q \
  plugins/progress-tracker/tests/test_command_discovery_contract.py \
  plugins/progress-tracker/tests/test_feature_contract_readiness.py
```

- [ ] **Step 2.4: Commit**

```bash
git add \
  plugins/progress-tracker/tests/test_command_discovery_contract.py \
  plugins/progress-tracker/tests/test_feature_contract_readiness.py
git commit -m "test(progress-tracker): remove prog-start contract and lock /prog-next as sole start path"
```

---

## 3. PR-2 `set-finish-state` + `/prog-next` 阻断

**Goal:** 给 `finish_pending` 提供显式解锁命令，并防止带债推进下一 feature。

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Create: `plugins/progress-tracker/tests/test_set_finish_state_cli.py`
- Modify: `plugins/progress-tracker/tests/test_feature_contract_readiness.py`

- [ ] **Step 3.1: 先写测试（修正命令语法）**

测试中创建 feature 使用：

```python
_run(["add-feature", "Feature A", "step 1"], cwd=tmp_path)
```

不要用 `--test-steps`。

- [ ] **Step 3.2: 实现 `set-finish-state` 子命令**

新增：
- 常量 `VALID_FINISH_STATES = ("merged_and_cleaned", "pr_open", "kept_with_reason")`
- `cmd_set_finish_state(feature_id, status, reason=None) -> int`
- argparse 子命令 `set-finish-state`
- `_dispatch_command` 分支

- [ ] **Step 3.3: 扩展 `next_feature` 签名（向后兼容）**

改为：

```python
def next_feature(output_json: bool = False, return_result: bool = False):
```

行为：
- 若任一 feature `integration_status == finish_pending`：
  - `return_result=True` 返回 `{"blocked": True, ...}`
  - 否则打印阻断原因并返回 `False`

- [ ] **Step 3.4: 验证**

```bash
pytest -q \
  plugins/progress-tracker/tests/test_set_finish_state_cli.py \
  plugins/progress-tracker/tests/test_feature_contract_readiness.py -k "finish_pending or development_stage"
```

- [ ] **Step 3.5: Commit**

```bash
git add -A
git commit -m "feat(progress-tracker): add set-finish-state resolver and block next-feature on finish_pending"
```

---

## 4. PR-3 Schema 2.1 + evaluator gate

**Goal:** 升级 schema 并落地独立 evaluator 质量门。

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Create: `plugins/progress-tracker/hooks/scripts/evaluator_gate.py`
- Create: `plugins/progress-tracker/tests/test_schema_2_1_migration.py`
- Create: `plugins/progress-tracker/tests/test_evaluator_gate.py`
- Modify: `plugins/progress-tracker/skills/feature-complete/SKILL.md`

- [ ] **Step 4.1: Schema 2.1 测试先行**

覆盖：
- `CURRENT_SCHEMA_VERSION == "2.1"`
- 2.0 -> 2.1 新字段回填
- `PROG_DISABLE_V2=1` 不覆盖已存在新字段
- unknown fields round-trip
- migration event 记录

- [ ] **Step 4.2: 实现 schema 升级**

关键点：
- `CURRENT_SCHEMA_VERSION = "2.1"`
- `_apply_schema_defaults()` 内补齐：`sprint_contract` / `quality_gates` / `handoff`
- `load_progress_json()` 检测到从 `2.0` 迁移时，写回一次并追加 `audit.log` migration 事件
- migration 仅记录一次（按文件当前版本判断）

- [ ] **Step 4.3: 实现 `evaluator_gate.py`**

提供：
- `EvaluatorDefect`
- `EvaluatorResult`
- `assess(feature, rubric, signals)`
- `to_quality_gate_payload()`

- [ ] **Step 4.4: 写入集成点**

在 `progress_manager.py` 新增：
- `_store_evaluator_result(feature_id, result)`

在 `_validate_done_preconditions` 增加 evaluator gate：
- `quality_gates.evaluator.status != pass` 时阻断并给出恢复动作。

- [ ] **Step 4.5: 更新 skill 文档（避免过时角色名）**

`feature-complete/SKILL.md` 新增步骤：
- “在 fresh subagent 运行 evaluator，写回 `_store_evaluator_result`，不通过则禁止 done”。
- 不使用 `superpowers:code-reviewer` 文案。

- [ ] **Step 4.6: 验证 + Commit**

```bash
pytest -q \
  plugins/progress-tracker/tests/test_schema_2_1_migration.py \
  plugins/progress-tracker/tests/test_evaluator_gate.py

git add -A
git commit -m "feat(progress-tracker): schema 2.1 migration and evaluator quality gate"
```

---

## 5. PR-4 review_router 多 lane 路由

**Goal:** 按变更类型动态决定必需 review lanes。

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/review_router.py`
- Create: `plugins/progress-tracker/tests/test_review_router.py`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Modify: `plugins/progress-tracker/skills/feature-complete/SKILL.md`

- [ ] **Step 5.1: 统一 lane 策略（修复原稿冲突）**

规则：
- `docs-only`（仅 docs 类别）=> `required=["docs"]`
- 其他默认强制 `eng+qa+docs`
- `frontend/ui` 额外加 `design`
- `sdk/api` 额外加 `devex`

- [ ] **Step 5.2: 防止恢复时重置评审进度**

`set_current()` 中调用 `initialize_reviews(feature)` 的条件改为：
- 仅当 `quality_gates.reviews.required` 为空时初始化。
- 已存在 `passed/pending` 时不重置。

- [ ] **Step 5.3: done 前置门**

在 `_validate_done_preconditions` 加：
- `reviews.pending` 非空阻断并输出 pending lanes。

- [ ] **Step 5.4: 验证 + Commit**

```bash
pytest -q plugins/progress-tracker/tests/test_review_router.py

git add -A
git commit -m "feat(progress-tracker): add review_router with deterministic lane policy"
```

---

## 6. PR-5 ship_check + docs-sync

**Goal:** 在归档前统一执行 ship 门禁。

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/ship_check.py`
- Create: `plugins/progress-tracker/tests/test_ship_check.py`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Modify: `plugins/progress-tracker/skills/feature-complete/SKILL.md`

- [ ] **Step 6.1: 定义并实现 `_collect_ship_signals`（补齐原稿空洞）**

信号来源：
- 最近一次 `docs/progress-tracker/state/test_reports/feature-<id>-done-attempt-*.json`
- docs-sync：调用 `generate_prog_docs.py --check`
- coverage：优先 `--coverage` CLI 显式输入；否则从约定输入读取，缺失则给出明确 failure。

- [ ] **Step 6.2: 增加 `ship-check` CLI**

参数：
- `--feature-id` 必填
- `--coverage-min` 默认 `0.8`
- `--coverage` 可选（便于手动与 CI 注入）

- [ ] **Step 6.3: done 前置门**

在 `_validate_done_preconditions` 中增加：
- `quality_gates.ship_check.status != pass` 阻断并给出 `prog ship-check` 恢复动作。

- [ ] **Step 6.4: 验证 + Commit**

```bash
pytest -q plugins/progress-tracker/tests/test_ship_check.py

git add -A
git commit -m "feat(progress-tracker): add ship-check gate with docs-sync and explicit signal collection"
```

---

## 7. PR-6 sprint_contract + sprint_ledger + handoff

**Goal:** 提供可恢复的 sprint 合约与 artifact 交接。

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/sprint_ledger.py`
- Create: `plugins/progress-tracker/tests/test_sprint_ledger.py`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Modify: `plugins/progress-tracker/skills/feature-implement/SKILL.md`
- Modify: `plugins/progress-tracker/skills/feature-complete/SKILL.md`

- [ ] **Step 7.1: 实现 ledger 与 contract 校验**

包含：
- `record/list_sprint_records/read_latest`
- `require_sprint_contract`
- `mark_handoff`

- [ ] **Step 7.2: 修正文案与实现语义**

把“跨文件原子事务”改为“单锁串行一致性”：
- 持有 `progress_transaction()` 锁期间更新 `progress.json`
- 同锁内 append ledger（使用 `_atomic_write_text` 的 read-modify-write 方式，避免裸 append）
- 明确异常时的补偿策略：写失败则整体抛错并拒绝阶段推进

- [ ] **Step 7.3: done 前置门增加 sprint_contract 检查**

不完整时阻断并提示缺失字段。

- [ ] **Step 7.4: skill 串联**

`feature-implement/SKILL.md`：
- set-current 后强制检查 `sprint_contract`
- 缺失则先补 contract，再记 `sprint_ledger`

- [ ] **Step 7.5: 验证 + Commit**

```bash
pytest -q plugins/progress-tracker/tests/test_sprint_ledger.py

git add -A
git commit -m "feat(progress-tracker): add sprint contract + sprint ledger with serialized consistency"
```

---

## 8. PR-7 FSM kernel + auto-driver hooks

**Goal:** 把推进逻辑收束为程序判定，hook 负责注入下一步动作与硬门禁。

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/wf_state_machine.py`
- Create: `plugins/progress-tracker/hooks/scripts/wf_auto_driver.py`
- Create: `plugins/progress-tracker/tests/test_wf_state_machine.py`
- Create: `plugins/progress-tracker/tests/test_wf_auto_driver.py`
- Modify: `plugins/progress-tracker/hooks/hooks.json`
- Modify: `plugins/progress-tracker/hooks/run-hook.sh`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Modify: `plugins/progress-tracker/skills/feature-implement/SKILL.md`
- Modify: `plugins/progress-tracker/skills/feature-complete/SKILL.md`

- [ ] **Step 8.1: 实现纯函数 FSM**

`compute_next_action(feature) -> Action`，覆盖：
- `request_sprint_contract`
- `dispatch_evaluator`
- `dispatch_review_lane`
- `run_ship_check`
- `complete_done`
- `await_user`
- `noop`

- [ ] **Step 8.2: 实现 hook shell**

`wf_auto_driver.py` 子命令：
- `tick`（Stop/UserPromptSubmit）
- `gate`（PreToolUse）
- `print-action`（debug）

`PROG_AUTO_DRIVER=0` 时返回空对象并放行。

`gate` 的命令识别必须同时覆盖：
- `prog done` / `prog ship-check`
- `plugins/progress-tracker/prog done` / `plugins/progress-tracker/prog ship-check`

- [ ] **Step 8.3: `run-hook.sh` 路由改造（保留兼容）**

新增 case：
- `wf-tick` -> `wf_auto_driver.py tick`
- `wf-gate` -> `wf_auto_driver.py gate`
- 其他命令继续走 `progress_manager.py "$@"`（兼容原行为）

- [ ] **Step 8.4: `hooks.json` 注册新 hook**

新增：
- `UserPromptSubmit` 加 `wf-tick`
- `Stop` 加 `wf-tick`
- `PreToolUse/Bash` 加 `wf-gate`

- [ ] **Step 8.5: `prog drive --once` 调试入口**

在 `progress_manager.py` 增加 `drive` 子命令调用 `wf_auto_driver.print-action`。

- [ ] **Step 8.6: skill 协议**

在两个 SKILL.md 增加 `wf-auto-instruction` 协议段：
- 解析标签并执行 action
- `await_user` 直接向用户报告阻断原因

- [ ] **Step 8.7: 验证 + Commit**

```bash
pytest -q \
  plugins/progress-tracker/tests/test_wf_state_machine.py \
  plugins/progress-tracker/tests/test_wf_auto_driver.py

python3 -c "import json; json.load(open('plugins/progress-tracker/hooks/hooks.json'))"

git add -A
git commit -m "feat(progress-tracker): add FSM auto-driver and hook-based workflow ticking"
```

---

## 9. 全量回归与 E2E smoke（修正后的可执行命令）

- [ ] **Step 9.1: 全量测试**

```bash
pytest -q plugins/progress-tracker/tests/
```

- [ ] **Step 9.2: CLI smoke（仓库根执行）**

```bash
plugins/progress-tracker/prog init "WF Smoke" --force
plugins/progress-tracker/prog add-feature "Feature X" "echo done"
plugins/progress-tracker/prog set-current 1
plugins/progress-tracker/prog drive --once
```

预期：输出 action（初始通常为 `request_sprint_contract` 或 `dispatch_evaluator`，取决于当前字段状态）。

- [ ] **Step 9.3: hook gate smoke**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"prog done"}}' \
  | python3 plugins/progress-tracker/hooks/scripts/wf_auto_driver.py gate
```

预期：未满足门禁时返回 deny/block payload。

---

## 10. 交付顺序（执行版）

推荐顺序：
1. PR-1
2. PR-2
3. PR-3
4. PR-4
5. PR-5
6. PR-6
7. PR-7

理由：
- PR-3 给出 schema 与 evaluator 基础。
- PR-4/PR-5 依赖 quality_gates。
- PR-6 虽可并行，但为降低冲突并便于审查，顺序执行更稳。
- PR-7 最后，方便单独回滚。

---

## 11. 回滚与逃生门

- 自动推进异常：先 `PROG_AUTO_DRIVER=0`。
- schema 行为异常：先 `PROG_DISABLE_V2=1`。
- PR-7 可单独 `git revert <sha>`。
- 涉及 schema 的回退必须先备份 `progress.json` 与 `audit.log`。

---

## 12. 自检清单（计划作者自审，执行前必须打勾）

- [ ] 本文所有 `add-feature` 命令均为位置参数，无 `--test-steps`
- [ ] 所有 smoke 命令都可在仓库根直接执行
- [ ] 不再声明“零行为变化”
- [ ] `mark_handoff` 不再宣称跨文件原子事务
- [ ] `set_current` 初始化 reviews 具备幂等保护，不覆盖已通过 lanes
- [ ] `_collect_ship_signals` 有明确定义与输入来源
- [ ] 未使用已废弃 `superpowers:code-reviewer` 文案
