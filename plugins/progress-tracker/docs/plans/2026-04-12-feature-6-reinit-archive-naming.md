# Feature 6 Plan: `prog init --force` 归档与旧状态重命名策略标准化

**Feature ID:** 6  
**Name:** prog init --force 归档与旧状态重命名策略标准化  
**Complexity:** 21 (Standard)  
**Workflow:** plan_execute

## Goal

在 `init --force` 的重初始化场景中，统一归档旧状态文件命名、补齐可追溯元信息，并保证重复 re-init 不会覆盖历史归档。

## Tasks

1. 扩展 `archive_current_progress()`，为归档 entry 补充标准化 artifact 元信息（来源文件、归档路径、类型）。
2. 将旧状态投影文件纳入归档并采用统一命名：
   - `status_summary.v1.json` -> `<archive_id>.status-summary.v1.json`
   - `status_summary.json` -> `<archive_id>.status-summary.legacy.json`
3. 增加 archive-id 冲突消解策略，确保重复 re-init（即使基础 ID 相同）也会生成新归档 ID，避免覆盖历史文件。
4. 新增 `tests/test_reinit_archive_naming.py`，覆盖：
   - re-init 归档元信息与命名规范；
   - 重复 re-init 不覆盖历史归档（冲突 ID 场景）。
5. 运行目标验收测试并确认通过。

## Acceptance Mapping

- "在 re-init 时统一归档旧 progress 文件并保留可追溯元信息"  
  -> `test_reinit_archives_progress_and_status_files_with_traceable_metadata`
- "运行: pytest -q plugins/progress-tracker/tests/test_reinit_archive_naming.py"  
  -> 执行该命令并通过
- "校验重复 re-init 不会覆盖历史归档"  
  -> `test_reinit_archive_ids_are_collision_safe_and_history_is_not_overwritten`

## Risks

- 新增归档字段必须保持向后兼容，不能破坏既有 `progress_history` 消费方。
- 冲突消解策略需稳定且可读，避免生成不可预测路径影响排障。
