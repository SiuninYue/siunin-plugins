# Round 3: Extract Feature Activation and Stage Commands to feature_commands.py

**change_id:** 20260604-feature-activation-f22a  
**date:** 2026-06-04  
**component:** hooks/scripts/progress_manager.py  
**feature:** F22

## 问题现象

`progress_manager.py` 仍保留 feature 激活与开发阶段变更等写入行为逻辑（set_current_command、set_development_stage_command、_set_current、_set_development_stage），不符合 facade 清理的要求。

## 根因

作为 F22 progress-tracker 演进的一部分，需持续将业务逻辑向独立子模块迁移，从而减小 progress_manager  facade 的体积和职责。

## 修复点

- 新建 `hooks/scripts/feature_commands.py`：
  - `FeatureCommandsServices` dataclass 用于注入回调
  - 核心逻辑：`_set_current`、`_set_development_stage`
  - 命令实现：`set_current_command`、`set_development_stage_command`
- `progress_manager.py` 替换为 thin facade wrappers（`is_wrapper = True`）
- 更新 `progress-manager-module-map.md` 的模块所有权映射。

## 影响面

- `prog set-current` 和 `prog set-development-stage` 命令行为保持完全兼容
- 原 facade 接口继续通过兼容 wrapper 导出

## 验证命令

```bash
scripts/check_pm_boundary.sh
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
uv run pytest plugins/progress-tracker/tests/test_feature_commands.py -q
uv run pytest plugins/progress-tracker/tests -q
```

## 验证结果

- 所有检查与测试均已通过，详情参见 F22 done 关闭证据。

## 回退步骤

```bash
git revert 436039c8835bc976334c3541e3c9aa3053064e9c
```

## 残余风险

- 若 `FeatureCommandsServices` 中的回调接口发生变更，需对应修改 facade 中的 services 初始化工厂方法。
