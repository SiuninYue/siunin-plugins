# Feature 10 Plan: Summary Projection and Status Display

**Feature ID:** 10
**Name:** summary 投影与状态展示
**Complexity:** 21 (Standard)
**Workflow:** plan_execute
**Goal:** 让 `/prog` CLI 与 UI 状态栏基于同一份可重建的 summary 投影，避免展示口径漂移。
**Architecture:** 在 `hooks/scripts/` 内提供唯一入口（同一个读取/重建函数）负责 summary projection；`progress_manager.py` 与 `progress_ui_server.py` 仅通过该入口取数，禁止并行实现第二套汇总逻辑。

## Scope

- In scope:
  - 统一 summary 计算口径（`progress` / `next_action` / `plan_health` / `risk_blocker` / `recent_snapshot`）。
  - 引入可持久化的 summary 投影及漂移检测与自动重建。
  - 让 `/prog` 与 UI API 共用该投影数据路径。
- Out of scope:
  - 无关命令重构。
  - 非 Feature 10 验收路径上的 UI 风格改动。

## Tasks

1. 定义 summary 投影契约与存储策略  
   - 明确投影文件路径为 `docs/progress-tracker/state/status_summary.v1.json`。  
   - 设计投影结构（字段、版本、来源、时间戳），并固定 schema 命名。  
   - 明确最小一致性字段：`progress`、`next_action`、`plan_health`、`risk_blocker`、`recent_snapshot`。  
   - 约束与 `progress.json` / `checkpoints.json` 的关联关系与容错规则。
   - 明确迁移策略：若检测到旧命名投影文件，首次读取时迁移到 `status_summary.v1.json`，并将来源版本写入 `migration.from_schema_version`。

2. 实现投影构建与漂移检测/重建  
   - 提供统一构建与读取函数（建议独立模块，供 CLI/UI 复用）。  
   - 实现漂移判定（例如输入文件更新、缺失、字段不一致、版本不匹配）。  
   - 在读取路径中自动触发重建，并保持幂等与原子写入（temp file + fsync + rename）。

3. 接入 CLI 与 UI 状态展示  
   - `/prog` 状态输出改为读取同一 summary 投影入口（不允许“CLI 一套 / UI 一套”）。  
   - `GET /api/status-summary` 与相关详情面板复用相同来源，减少重复逻辑。  
   - 保留降级路径：投影不可用时可回退并自修复，不阻塞基础状态展示。
   - 增加一致性校验钩子：同一输入快照下，CLI 与 API 的 summary 核心字段必须同值。

4. 补齐测试与回归验证  
   - 覆盖正常路径：投影生成、读取、字段一致性。  
   - 覆盖异常路径：投影缺失/损坏、输入文件漂移、自动重建。  
   - 覆盖跨通道一致性：CLI 与 UI/API 对同一状态源返回同源同值的 summary 核心字段。  
   - 覆盖迁移路径：旧命名投影文件可自动迁移到 `status_summary.v1.json`，并保留可追踪版本信息。  
   - 确认现有 UI 状态 API 与展示逻辑测试全部通过。

5. 文档与运行说明  
   - 更新注释/文档说明 summary 投影来源、重建触发条件、排障方式。  
   - 给出最小诊断命令（如何确认投影是否漂移与是否重建成功）。

## Acceptance Mapping

- `cd plugins/progress-tracker && pytest tests/test_progress_ui_status.py -q`  
  验证状态摘要 API、计划合规面板、上下文展示与空态降级行为。
- `cd plugins/progress-tracker && pytest tests/test_progress_ui.py -q`  
  验证 UI 服务端接口与前端状态栏/抽屉契约不回退。
- `cd plugins/progress-tracker && pytest tests/test_ui_display_logic.py -q`  
  验证 development_stage 到 UI 标题/动作映射保持一致。
- `cd plugins/progress-tracker && pytest -q tests/test_progress_ui_status.py::test_status_summary_api_normal tests/test_progress_ui_status.py::test_status_summary_without_progress_json tests/test_progress_ui_status.py::test_status_summary_with_current_feature`  
  验证 summary 核心字段结构、空态降级与 active feature 语义。
- 一致性 smoke（CLI vs API vs projection，同一输入快照）:
```bash
cd plugins/progress-tracker && python3 - <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,'hooks/scripts')
import progress_manager, progress_ui_server
progress_manager.configure_project_scope('.')
cli_loader=getattr(progress_manager,'load_status_summary_projection',None)
assert callable(cli_loader), 'progress_manager.load_status_summary_projection missing'
cli_summary=cli_loader()
h=progress_ui_server.ProgressUIHandler.__new__(progress_ui_server.ProgressUIHandler)
h.working_dir=Path('.')
api_summary=h.handle_get_status_summary()
projection_path=Path('docs/progress-tracker/state/status_summary.v1.json')
assert projection_path.exists(), 'status_summary.v1.json missing'
projection=json.loads(projection_path.read_text(encoding='utf-8'))
core=('progress','next_action','plan_health','risk_blocker','recent_snapshot')
for key in core:
    assert cli_summary[key]==api_summary[key]==projection[key], f'core field mismatch: {key}'
print('ok')
PY
```
- 旧命名迁移 smoke（Feature 10 完成后应转为自动化测试文件）:
```bash
cd plugins/progress-tracker && python3 - <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,'hooks/scripts')
import progress_ui_server
state=Path('docs/progress-tracker/state')
state.mkdir(parents=True,exist_ok=True)
legacy=state/'status_summary.json'
legacy.write_text(json.dumps({'schema_version':'legacy','progress':{},'next_action':{},'plan_health':{},'risk_blocker':{},'recent_snapshot':{}},ensure_ascii=False),encoding='utf-8')
h=progress_ui_server.ProgressUIHandler.__new__(progress_ui_server.ProgressUIHandler)
h.working_dir=Path('.')
_ = h.handle_get_status_summary()
new_path=state/'status_summary.v1.json'
assert new_path.exists(), 'status_summary.v1.json not created from legacy projection'
migrated=json.loads(new_path.read_text(encoding='utf-8'))
assert migrated.get('schema_version')=='status_summary.v1', migrated
trace=migrated.get('migration', {})
assert trace.get('from_schema_version')=='legacy', trace
print('ok')
PY
```
- `cd plugins/progress-tracker && python3 hooks/scripts/progress_manager.py --project-root . status`  
  触发 CLI 路径读取/重建投影。
- `cd plugins/progress-tracker && test -f docs/progress-tracker/state/status_summary.v1.json`  
  验证投影文件已落盘。
- `cd plugins/progress-tracker && jq -e '.schema_version == \"status_summary.v1\" and has(\"recent_snapshot\")' docs/progress-tracker/state/status_summary.v1.json >/dev/null`  
  验证投影 schema_version 与字段命名契约（`recent_snapshot`）。
- Hard DoD（阻断式）:
  - summary 投影文件固定为 `docs/progress-tracker/state/status_summary.v1.json`，字段名固定使用 `recent_snapshot`。
  - 删除或破坏投影后，下一次 `/prog` 或 `/api/status-summary` 访问会自动重建并恢复可用状态。
  - 旧命名迁移后保留 `migration.from_schema_version`，可追踪来源版本。
  - 在同一输入快照下，CLI 与 UI/API 的 summary 核心字段（`progress`/`next_action`/`plan_health`/`risk_blocker`/`recent_snapshot`）同源且同值。

## Risks

- 投影与源数据存在双写或时序差异，可能导致短时不一致。  
  - Mitigation: 单一构建入口 + 原子写入 + 读取时自愈重建。
- CLI/UI 在不同路径仍保留旧逻辑，可能造成口径再次分叉。  
  - Mitigation: 明确“统一入口”并在测试中做跨通道一致性断言。
- 重建触发过于频繁可能影响响应性能。  
  - Mitigation: 基于输入变更判定重建，并复用已有缓存策略。
