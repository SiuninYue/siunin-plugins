# SPM x PROG Beta Integration Design

**Date:** 2026-03-09  
**Status:** Approved (initial)  
**Owner:** `codex/prog-beta-setup`

## 1. Goal

在 Beta 阶段打通 `super-product-manager`（SPM）与 `progress-tracker`（PROG），形成可验证闭环：

1. SPM 产生会议决策与任务分配。
2. 通过桥接同步到 PROG 的结构化更新与角色归属。
3. PROG 继续负责 feature 生命周期、测试驱动完成、bug 与恢复流程。

## 2. Scope

### In Scope

1. PROG 新增 `/prog-update` 命令能力（命令 + skill + CLI 支撑）。
2. `progress.json` 扩展：
   - 顶层 `updates[]`
   - `features[].owners`（三角色：`architecture|coding|testing`）
3. SPM 新增会议命令组：
   - `/meeting`
   - `/roundtable`
   - `/assign`
   - `/followup`
4. 新增 SPM -> PROG 桥接脚本，通过 `prog` CLI 同步，不直接写 PROG state 文件。
5. 文档、测试、发布说明更新，形成 Beta 验收基线。

### Out of Scope (Beta 不做)

1. PROG 内自动多 agent 执行编排器。
2. 复杂动态插件路由（P2 全自动方案）。
3. Web UI 会议排程与跨机器同步队列。

## 3. Architecture

### 3.1 Logical Components

1. SPM Command Layer  
负责会议输入结构化、产物落盘、触发桥接同步。

2. SPM Bridge Layer (`prog_bridge.py`)  
负责把会议事件转换为 `prog` CLI 参数，执行同步与降级处理。

3. PROG CLI Layer (`progress_manager.py` + `prog` wrapper)  
负责 `add-update`、`list-updates`、`set-feature-owner` 等可测试的状态写入。

4. PROG Display Layer  
负责在 `/prog` 与 `progress.md` 展示最近更新与角色分配。

### 3.2 Data Model

`progress.json` schema 从 `2.0` 向后兼容扩展到 `2.1`（建议）：

1. `updates` 顶层数组（默认空）。
2. `features[].owners` 默认对象：
   - `architecture: null`
   - `coding: null`
   - `testing: null`

`updates[]` 对象字段：

1. `id` (UPD-xxx)
2. `created_at`
3. `category` (`status|decision|risk|handoff|assignment|meeting`)
4. `summary`
5. `details`
6. `feature_id` (nullable)
7. `bug_id` (nullable)
8. `role` (`architecture|coding|testing`, nullable)
9. `owner` (nullable)
10. `source` (`prog_update|spm_meeting|spm_assign|manual`)
11. `next_action` (nullable)
12. `refs` (list, nullable)

## 4. Workflow & Data Flow

### 4.1 `/meeting` and `/roundtable`

1. 生成会议纪要到 `docs/meetings/YYYY-MM-DD-<topic>.md`。
2. 更新 `docs/meetings/action-items.json`。
3. 通过 bridge 调用 `prog add-update --category meeting|decision ...`。
4. 若同步失败：不阻断主流程，记录 `sync_errors` 并输出修复建议。

### 4.2 `/assign`

1. 解析 `feature_id + role + owner`。
2. 调用 `prog set-feature-owner` 写入角色归属。
3. 同时写一条 `assignment` 更新（可追溯）。

### 4.3 `/followup`

1. 更新 action item 状态。
2. 同步 `status|handoff` 更新到 PROG。
3. `/prog` 状态页可看到最近同步记录。

## 5. Error Handling & Compatibility

1. PROG 未初始化：
   - SPM 命令继续工作，仅输出“待同步”提示。
   - 会议产物仍正常落盘。
2. CLI 执行失败：
   - 记录 `sync_errors`，附可复现命令与 stderr 摘要。
3. 旧 `progress.json`：
   - 读取时自动补齐 `updates` 与 `owners` 默认字段。
4. 输入校验：
   - `category`、`role` 枚举严格校验。
   - 不存在 feature_id 时返回明确错误码与文案。

## 6. Testing Strategy

1. PROG 单测：
   - 新 CLI 子命令行为与错误路径。
   - schema 迁移兼容。
2. SPM 单测：
   - 命令契约 frontmatter。
   - `prog_bridge.py` 成功/失败/降级路径。
3. 集成测试：
   - `meeting -> update`
   - `assign -> owners + update`
   - `followup -> status/handoff update`
4. 回归门禁：
   - `pytest -q plugins/progress-tracker/tests`
   - `pytest -q plugins/super-product-manager/tests`
   - 命令帮助/文档生成检查。

## 7. Beta Definition of Done

满足以下全部条件即 Beta 完成：

1. 新命令可发现、可执行、契约测试通过。
2. 会议命令可生成文件并把更新同步到 PROG（含失败降级）。
3. `/prog` 与 `progress.md` 可见最近更新与角色归属。
4. 核心测试全绿，文档和 changelog 更新完成。
5. marketplace 版本与各插件 manifest 对齐，消除版本漂移。

## 8. Decisions Frozen for Beta

1. 角色固定三类：`architecture|coding|testing`。
2. owner 先用自由文本，不引入复杂身份系统。
3. 同步只通过 `prog` CLI，不跨层直接写 PROG 状态文件。
4. 命令命名标准以连字符形式为主（如 `/prog-update`）。

## 9. Risks

1. 命令文档与实际行为漂移。
2. schema 迁移破坏历史项目。
3. bridge 调用环境差异导致同步不稳定。

缓解策略：

1. 增加契约测试 + 生成文档检查。
2. 在单测中覆盖旧 schema 自动补齐。
3. bridge 统一封装调用与错误文本，保留降级路径。
