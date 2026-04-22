# F13 Plan Optimization: sprint_ledger + schema 2.1 persistence hardening

**Goal:** 在已完成的 F13 基础上补齐一致性与可恢复性缺口，确保 sprint artifact 持久化在长跑 session 中断后可稳定恢复。
**Architecture:** 保持 `progress_manager.py` 作为状态入口；`sprint_ledger.py` 负责 append-only artifact 记录与 contract 校验。跨文件写入采用“同锁串行一致性”策略：持有 `progress_transaction()` 锁执行 `progress.json` 更新与 ledger 追记，失败即阻断阶段推进。

## Scope

1. 强化 `sprint_ledger.record` 的写入一致性语义（避免裸 append）。
2. 在 `/prog done` 路径记录 `evaluation` artifact（done attempt report）。
3. 将 ledger 写失败视为阻断（fail-closed），避免“状态前进但无可恢复证据”。
4. 补充契约测试与集成测试，覆盖上述行为。

## Gaps Found In Current Implementation

1. `record()` 当前为直接 append，未绑定进度锁语义。
2. `cmd_done` 已校验 `require_sprint_contract`，但未统一写入 evaluation artifact。
3. `mark_handoff` 测试只验证 `progress.json` handoff 字段，未验证 ledger side effects。

## Tasks

## Task 1: ledger serialized consistency

- 修改 `hooks/scripts/sprint_ledger.py`：
  - 增加锁内追记 helper（RMW + atomic replace）。
  - `record()` 默认走串行一致性写入；无法安全写入时抛 `SprintLedgerError`。

## Task 2: `/prog done` artifact persistence

- 修改 `hooks/scripts/progress_manager.py`：
  - done attempt 生成 report 后，调用 `sprint_ledger.record(... phase="evaluation" ...)`。
  - record 失败返回阻断码（沿用 F13 语义：`9`）。

## Task 3: contract tests hardening

- 修改 `tests/test_sprint_ledger.py`：
  - `mark_handoff` 除更新 handoff 字段外，断言 ledger 追加了 handoff record。
- 修改 `tests/test_progress_manager.py`：
  - 新增 done 成功后写入 evaluation ledger record 的用例。

## Task 4: Validation

- `pytest -q tests/test_sprint_ledger.py`
- `pytest -q tests/test_schema_2_1_migration.py`
- `pytest -q tests/test_progress_manager.py -k "done_command"`
- `pytest -q tests/test_review_router.py -k "cmd_done or load_progress_json_recomputes_reviews_pending_cache"`
- `pytest -q tests/test_integration.py -k "prog_done_completes_current_feature"`
- `pytest -q tests`

## Exit Criteria

1. 所有新增/受影响测试通过，无回归。
2. `cmd_done` 在生成报告后可稳定写入 `sprint_ledger.jsonl` 的 `evaluation` 记录。
3. `mark_handoff` 对 `progress.json` 与 ledger 的 side effects 同时可验证。
