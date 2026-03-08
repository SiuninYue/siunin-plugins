# SPM x PROG Beta Integration Guide

## 目标

在 Beta 阶段打通 `super-product-manager` 与 `progress-tracker`，形成“会议决策 -> 执行跟踪”的可验证闭环。

## 组件

1. SPM 命令层（`/meeting` `/roundtable` `/assign` `/followup`）
2. SPM 工作流脚本（`plugins/super-product-manager/scripts/meeting_workflow.py`）
3. SPM 桥接层（`plugins/super-product-manager/scripts/prog_bridge.py`）
4. PROG 状态层（`plugins/progress-tracker/hooks/scripts/progress_manager.py`）

## 数据契约

### PROG `progress.json`

- 新增顶层 `updates[]`
- `features[].owners` 固定角色：
  - `architecture`
  - `coding`
  - `testing`

### `updates[]` 字段

- `id` (`UPD-XXX`)
- `created_at`
- `category` (`status|decision|risk|handoff|assignment|meeting`)
- `summary`
- `details`
- `feature_id`
- `bug_id`
- `role`
- `owner`
- `source` (`prog_update|spm_meeting|spm_assign|manual`)
- `next_action`
- `refs`

## 命令映射

### 会议同步

`/meeting` 与 `/roundtable`：

1. 写 `docs/meetings/YYYY-MM-DD-<topic>.md`
2. 更新 `docs/meetings/action-items.json`
3. 通过桥接调用：

```bash
plugins/progress-tracker/prog add-update --category meeting --summary "..."
```

### 负责人分配

`/assign`：

```bash
plugins/progress-tracker/prog set-feature-owner <feature_id> <role> <owner>
plugins/progress-tracker/prog add-update --category assignment --summary "..."
```

### 跟进行动项

`/followup`：

1. 更新 `action-items.json`
2. 同步 `status|handoff` 更新到 PROG

## 降级策略

当 PROG 不可用或命令失败时：

1. 会议/行动项文件照常落盘。
2. 返回 `sync_errors`，包含失败命令与 stderr 摘要。
3. 不阻断 SPM 主流程。

## 验证命令

```bash
pytest -q plugins/progress-tracker/tests
pytest -q plugins/super-product-manager/tests
pytest -q tests/test_spm_prog_beta_integration.py
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
python3 plugins/progress-tracker/hooks/scripts/quick_validate.py
```
