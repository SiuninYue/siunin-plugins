# Round 2: Extract Readiness Validation to readiness_validator.py

**change_id:** 20260604-readiness-validator-r2  
**date:** 2026-06-04  
**component:** hooks/scripts/progress_manager.py  
**feature:** F21

## 问题现象

`progress_manager.py` 仍保留 readiness validation 逻辑（validate_feature_readiness、validate_planning_command、fix_readiness_command 等），与 facade 收口目标不符。Round 1 完成 status/summary 只读链路外移后，readiness validation 成为下一个优先提取的责任集群。

## 根因

progress_manager.py 混合了 CLI 入口层与业务逻辑，readiness validation 是一个独立责任集群，可以安全提取到专注的子模块。

## 修复点

- 新建 `hooks/scripts/readiness_validator.py`：
  - `ReadinessValidatorServices` dataclass（注入 5 个回调）
  - 5 个自包含函数：`_has_non_empty_list_items`、`validate_feature_readiness`、`print_readiness_warnings`、`_build_readiness_fix_commands`、`print_readiness_error`
  - 3 个命令函数：`validate_readiness_command`、`validate_planning_command`、`fix_readiness_command`
- `progress_manager.py` 替换为 thin facade wrappers（`is_wrapper = True`），净减约 234 行（8997/10000）
- `_normalize_feature_contract` 直接从 `state_io` 导入（无反向依赖）
- `_evaluate_planning_readiness` 保留在 facade，通过 `evaluate_planning_readiness_fn` 回调注入
- 更新 `progress-manager-module-map.md`：添加 Round 2 行，移除 Round 2 待办行

## 影响面

- `validate-readiness` / `validate-planning` / `fix-readiness` CLI 行为保持完全兼容
- 所有公共函数名在 `progress_manager.py` 中保留为兼容 facade wrapper
- 现有测试无需修改（函数通过 facade 层透明访问）

## 验证命令

```bash
scripts/check_pm_boundary.sh
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
uv run pytest plugins/progress-tracker/tests/test_prog_readiness.py plugins/progress-tracker/tests/test_validate_planning_json_contract.py plugins/progress-tracker/tests/test_feature_contract_readiness.py -q
uv run pytest plugins/progress-tracker/tests -q
```

## 验证结果

- boundary check: pass（8997/10000 行，无反向导入）
- docs parity: pass
- 目标测试: 38 passed
- 完整回归: 1077 passed, 1 warning

## 回退步骤

```bash
git revert <commit_sha>
# 或还原 readiness_validator.py 的创建和 progress_manager.py 的修改
```

## 残余风险

- `_evaluate_planning_readiness` 及其依赖（`_normalize_ref_tokens`、`_collect_update_refs`、`_planning_gate_enabled`、PLANNING_* 常量）仍在 facade 中，待 Round 7（workflow_commands）阶段评估是否提取
- `fix_readiness_command` 通过回调写入 progress.json，若回调签名变更需同步更新 services factory
