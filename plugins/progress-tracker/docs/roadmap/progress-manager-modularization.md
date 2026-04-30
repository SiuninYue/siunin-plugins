# progress_manager.py 模块化

## 目标

将 `progress_manager.py`（11,388 行）重构为轻量门面（facade），6 个核心模块全部提取为独立协作者。
完成后 ADR-001/003/006 从 PARTIAL 变为 DONE，全部 11 个 ADR 达成。

## 当前问题

| 问题 | 影响 |
|------|------|
| 6 个核心模块仍内联在 11,388 行单文件中 | ADR-001 PARTIAL |
| `transaction_manager.py` 不存在，审计/摘要不在同一事务 | ADR-003 PARTIAL |
| `summary_projector.py` 不存在，`transaction_marker` 未实现 | ADR-006 PARTIAL |
| `save_progress_json()` 43 处调用分散在主文件中 | 写入安全无法保证 |

## 现状

### 已提取（7 个）

- `contract_importer.py`
- `lifecycle_state_machine.py`
- `evaluator_gate.py`
- `review_router.py`
- `sprint_ledger.py`
- `ship_check.py`
- `audit_log.py`

### 待提取（6 个）

| 模块 | 包含函数 | 对应 ADR | 难度 |
|------|---------|----------|------|
| `summary_projector.py` | `_status_summary_source_fingerprint`、`_projection_needs_rebuild`、`_build_status_summary_projection`、`load_status_summary_projection`、`_build_status_summary_core` | ADR-006 | 低 |
| `readiness_validator.py` | `validate_feature_readiness`、`validate_readiness_command`、`validate_planning_command`、`fix_readiness_command` | — | 低 |
| `transaction_manager.py` | `_acquire_progress_lock`、`_release_progress_lock`、`progress_transaction`、`_atomic_write_text`、`save_progress_json` | ADR-003 | 中 |
| `finish_gate.py` | `cmd_set_finish_state`、`_clear_feature_finish_pending`、`_run_post_done_cleanup`、`_is_worktree_dirty`、`_remove_worktree`、`_delete_local_branch`、`_delete_remote_branch`、`_resolve_upstream` | — | 中 |
| `schema_migration.py` | `_apply_schema_defaults`、`_default_sprint_contract`、`_default_quality_gates`、`_default_handoff`、`_normalize_feature_contract`、`_derive_lifecycle_state` | ADR-002（已 DONE） | 低 |
| `state_reconciler.py` | `cmd_reconcile_state`、`analyze_reconcile_state`、`find_backfill_candidates`、`cmd_backfill_event`、`_replay_audit_events` | — | 中 |

## 方案设计

### 提取原则

1. **门面模式** — `progress_manager.py` 保留所有公开函数名，只委托调用
2. **测试不改 import** — 57 个测试文件保持 `from progress_manager import xxx`
3. **函数签名不变** — 对外零影响
4. **每次提取后跑 `pytest`** — 63 个测试文件做回归安全网

### 执行阶段

```
Phase 1 — 低风险热身（ADR-006 → DONE）
  summary_projector.py → readiness_validator.py
  纯衍生/校验逻辑，耦合度最低

Phase 2 — 核心价值（ADR-003 → DONE）
  transaction_manager.py → finish_gate.py
  统一写入路径 + closeout 独立可测

Phase 3 — 收尾（ADR-001 → DONE）
  schema_migration.py → state_reconciler.py
  全部 12 个模块就位
```

### 全局变量处理

`progress_manager.py` 中的模块级共享状态（`_PROJECT_ROOT_OVERRIDE`、`_STORAGE_READY_ROOT`、`_REPO_ROOT`）通过函数参数传入新模块，避免循环导入。

### 门面索引

在 `progress_manager.py` 顶部添加：

```python
# ====== Module Index ======
# schema_migration.py    — _apply_schema_defaults, _derive_lifecycle_state
# transaction_manager.py — _acquire_progress_lock, progress_transaction, _atomic_write_text
# state_reconciler.py    — cmd_reconcile_state, analyze_reconcile_state
# readiness_validator.py — validate_feature_readiness, validate_readiness_command
# finish_gate.py         — cmd_set_finish_state, _run_post_done_cleanup
# summary_projector.py   — load_status_summary_projection, _projection_needs_rebuild
```

## 风险与防御

| 风险 | 概率 | 防御 |
|------|------|------|
| 函数移动遗漏全局变量引用 | 中 | Grep 检查每个被移函数 |
| 循环导入 | 低 | 新模块只被门面导入，不相互导入 |
| 测试因路径变化失败 | 零 | 所有 import 走门面 |
| AI 找不到代码 | 低 | 门面索引 + 函数名不变（Grep 可定位） |

## 影响范围

- `/prog-*` CLI 完全不变
- skill 6 处引用全为 CLI/门面调用，无需修改
- hook 全从 `progress_manager` 导入，无需修改
- 57 个测试文件 import 路径不变

## 成功标准

- [ ] `progress_manager.py` < 3,000 行
- [ ] 全部 12 个协作者模块就位
- [ ] `pytest -q plugins/progress-tracker/tests/` 全部通过
- [ ] ADR-001 → DONE
- [ ] ADR-003 → DONE
- [ ] ADR-006 → DONE
- [ ] 全部 11 个 ADR 状态为 DONE

## 待决策项

- [ ] 是否接受 3 个 Phase 的执行顺序
- [ ] Phase 1 完成后是否暂停评估风险再继续
- [ ] `progress_manager.py` 最终保留行数目标（建议 < 3,000）
