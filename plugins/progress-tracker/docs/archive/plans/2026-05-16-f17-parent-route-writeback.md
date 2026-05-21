# F17: Parent-Child Route 同步 — 实现计划

> Feature ID: 17 | Bucket: complex | Model: opus

## 目标

子插件执行 `set_current()` 时，自动在父 progress.json 的 `active_routes` 中 upsert 一条路由记录。子插件执行 `cmd_done()` 时自动移除该记录。父 `root dashboard` 直接展示活跃子路由，无需扫描 routing_queue。

---

## 阶段一：TDD — 写失败测试（RED）

### T1 — 新建 `test_parent_route_writeback_f17.py`（不修改现有 test_parent_writeback.py）

> 说明：`test_parent_writeback.py` 首行注释为"F24"，承载 F24 回写测试；F17 测试独立文件，避免混淆。

#### T1.1 `test_set_current_upserts_parent_active_routes`
验证：子项目 `set_current(14)` 后，父 `active_routes` 出现 `{"project_code": "PT", "feature_ref": "PT-F14"}` 条目。

Setup:
- 父 progress.json: tracker_role=parent, linked_projects=[{code=PT, root=child}], active_routes=[]
- 子 progress.json: tracker_role=child, project_code=PT, parent_project_root=../parent, features=[{id:14,name:...,completed:false}]
- `set_current(14)` on child
- Assert: parent active_routes[0].project_code == "PT", feature_ref contains "PT-F14"

#### T1.2 `test_cmd_done_removes_parent_active_route`
验证：子项目 cmd_done 后，父 `active_routes` 中 PT 条目被移除。

Setup:
- 父 active_routes=[{project_code:"PT", feature_ref:"PT-F14"}]
- 子完成所有 quality gates
- `cmd_done()` on child
- Assert: parent active_routes 中无 PT 条目

#### T1.3 `test_set_current_warns_on_parallel_routes`
验证：父已有另一子项目 active_routes 时，set_current 输出 [WARNING]。

Setup:
- 父 active_routes=[{project_code:"NO", feature_ref:"NO-F1"}]
- 子 PT 调用 set_current(14)
- Assert: stdout 包含 "WARNING" 且操作成功

#### T1.4 `test_set_current_bootstrap_warn_when_active_routes_absent`
验证：子已正确注册到父 linked_projects，但父 active_routes 为空时，set_current 通过（仅 warn），
而非被 enforce_route_preflight 的检查 5（active_routes 缺失）阻断。

> **Bootstrap 例外范围说明**：
> - 检查 1-4（无 project_code / 父未注册子 / 多父冲突 / code 不匹配）→ **保持阻断不变**
> - 检查 5（`child_code not in active_route_codes`）→ 对 `set-current` **放行 + warn**，因为
>   set_current 本身是创建 active_routes 条目的动作（bootstrap 场景）

Setup:
- 父: linked_projects=[{code=PT}], active_routes=[] (子已注册，但无活跃路由)
- 子: project_code=PT, parent_project_root=../parent
- set_current(14) 成功通过，stdout 包含 "warn" / "bootstrap"
- Assert: result is True

### T2 — test_sync_linked_command.py 新增 2 个测试

#### T2.1 `test_sync_linked_repair_routes_rebuilds_from_child_current_feature`
验证：--repair-routes 从子 current_feature_id 重建 active_routes。

Setup:
- 子 current_feature_id=5, feature id=5 completed=False
- 父 active_routes=[] (stale/empty)
- `sync_linked(repair_routes=True)`
- Assert: 父 active_routes 包含 {project_code:"PT", feature_ref:"PT-F5"}

#### T2.2 `test_sync_linked_repair_routes_skips_completed_features`
验证：--repair-routes 跳过 completed/deferred feature，从 active_routes 清除。

Setup:
- 子 current_feature_id=5, feature id=5 completed=True
- 父 active_routes=[{project_code:"PT", feature_ref:"PT-F5"}]
- `sync_linked(repair_routes=True)`
- Assert: 父 active_routes 中无 PT 条目

---

## 阶段二：实现（GREEN）

### I1 — 新增 3 个 route helper 函数（progress_manager.py）

位置：`_notify_parent_sync` 函数前

```python
def _format_route_feature_ref(feature_id: int, project_code: str) -> str:
    """Format feature ref string: PT + 14 → 'PT-F14'."""
    return f"{project_code}-F{feature_id}"

def _upsert_active_route(
    parent_data: Dict[str, Any],
    project_code: str,
    feature_ref: str,
) -> None:
    """Upsert active_routes entry (in-place). Deduplicate by project_code."""
    active_routes: List[Any] = parent_data.get("active_routes") or []
    if not isinstance(active_routes, list):
        active_routes = []
    normalized_code = project_code.strip().upper()
    other = [r for r in active_routes if isinstance(r, dict)
             and r.get("project_code", "").strip().upper() != normalized_code]
    other.append({
        "project_code": normalized_code,
        "feature_ref": feature_ref,
        "assigned_at": _iso_now(),
    })
    parent_data["active_routes"] = other

def _remove_active_route(parent_data: Dict[str, Any], project_code: str) -> None:
    """Remove active_routes entry for project_code (in-place)."""
    active_routes: List[Any] = parent_data.get("active_routes") or []
    if not isinstance(active_routes, list):
        parent_data["active_routes"] = []
        return
    normalized_code = project_code.strip().upper()
    parent_data["active_routes"] = [
        r for r in active_routes
        if not (isinstance(r, dict)
                and r.get("project_code", "").strip().upper() == normalized_code)
    ]
```

### I2 — 扩展 `_notify_parent_sync()` 签名

变更：`def _notify_parent_sync() -> None:` → `def _notify_parent_sync(route_event: str = "refresh") -> None:`

逻辑：
1. 读 child_data, parent_project_root（现有逻辑不变）
2. 刷新 linked_snapshot（现有逻辑不变）
3. 若 route_event == "activate":
   - 读 child current_feature_id
   - 若有 project_code + current_feature_id：调用 `_upsert_active_route(parent_data, project_code, feature_ref)`
   - 检测并行路由，若有其它 active routes 则输出 [WARNING]
4. 若 route_event == "clear":
   - 读 child project_code
   - 调用 `_remove_active_route(parent_data, project_code)`
5. `_save_progress_payload_at_root(parent_root, parent_data)`

向后兼容：原有无参调用（init、add_feature）默认为 "refresh"，行为不变。

### I2.5 — `enforce_route_preflight()` set-current bootstrap 例外（精确范围）

修改 `enforce_route_preflight()` 中的**检查 5**（line ~12199）：

```python
if child_code not in active_route_codes:
    # Bootstrap exception: set-current is the action that creates the route entry.
    # Only allow pass-through for set-current when checks 1-4 passed (child is properly
    # registered in parent linked_projects with matching code, single parent).
    if command == "set-current":
        print(
            f"[WARNING] Route preflight: {child_code} not in parent active_routes. "
            "Allowing set-current to bootstrap route entry."
        )
        return True  # 仅此处例外，检查 1-4 已通过确保父注册正确
    # 所有其他命令保持原有阻断行为不变
    _print_route_preflight_block(...)
    return False
```

**不改动**：检查 1（无 project_code）、检查 2（父未注册子）、检查 3（多父冲突）、检查 4（code 不匹配）。这 4 个检查对 set-current 仍然生效。

### I3 — 在 `set_current()` 末尾调用 parent sync

位置：`save_progress_json(data)` 后，`save_progress_md(md_content)` 前

```python
_notify_parent_sync("activate")
```

### I4 — 更新 `cmd_done()` 中的调用

变更：`_notify_parent_sync()` → `_notify_parent_sync("clear")`（line ~9526）

### I5 — `sync_linked()` 新增 `repair_routes` 参数

```python
def sync_linked(
    output_json: bool = False,
    stale_after_hours: int = DEFAULT_LINKED_STATUS_STALE_HOURS,
    repair_routes: bool = False,
) -> bool:
```

若 `repair_routes=True`：
1. 在现有 linked_snapshot 刷新逻辑之后（不之前），额外执行路由重建
2. 对每个 linked_projects 中的子项目，读取其 progress.json 的 current_feature_id
3. 若 current_feature_id != None 且对应 feature 未 completed/deferred:
   - `_upsert_active_route(data, project_code, feature_ref)`
4. 否则：
   - `_remove_active_route(data, project_code)`
5. 保存 data 到 progress.json

**JSON 输出契约**：保留所有现有字段不变（`project_count/ok_count/missing_count/invalid_count/stale_count/stale_after_hours/snapshot`），仅在 repair_routes=True 时**增量添加** `repair_routes_applied: bool` 和 `repaired_routes: List[{project_code, feature_ref, action}]` 字段。现有消费者不受影响。

CLI 解析：`sync_linked_parser.add_argument("--repair-routes", action="store_true")`

### I6 — Dashboard 3-state handoff 输出

修改 `_display_root_dashboard` 文本输出部分（line ~5592）：

```python
# 3-state handoff block
n_active = len(active_routes_raw)
if n_active == 0:
    print(f"\nActive Route: none  |  Queue: {queue_str}")
elif n_active == 1:
    # Single active → direct resume hint
    route = active_routes_raw[0]
    code = route.get("project_code", "?")
    ref = route.get("feature_ref") or route.get("feature_name") or "?"
    print(f"\nActive Route: {code} -> {ref}  |  Queue: {queue_str}")
    print(f"→ Resume: /prog next  (routes to {code} active feature)")
else:
    # Multiple active → list + RecommendedRoute
    print(f"\nActive Routes ({n_active} parallel):")
    for route in active_routes_raw:
        c = route.get("project_code", "?")
        r = route.get("feature_ref") or "?"
        print(f"  {c} -> {r}")
    first_code = active_routes_raw[0].get("project_code", "?")
    print(f"RecommendedRoute: {first_code}  |  Queue: {queue_str}")
```

### I7 — 更新 progress-status SKILL.md handoff 模板

找到模板中的 handoff block 描述，补充 active_routes 三态说明。

---

## 阶段三：验证（REFACTOR）

```bash
# F17 核心测试
uv run pytest tests/test_parent_route_writeback_f17.py -q
uv run pytest tests/test_parent_writeback.py -q  # F24 回归（不能破坏）

# 路由 preflight 回归（本次改动直击 enforce_route_preflight）
uv run pytest tests/test_scope_fail_closed.py -q

# 相关回归
uv run pytest tests/test_dispatch_child_feature.py tests/test_route_commands.py tests/test_root_dashboard.py tests/test_sync_linked_command.py -q

# 完整回归
uv run pytest tests/ -q
```

---

## 任务清单

- [ ] T1.1 新建 test_parent_route_writeback_f17.py: test_set_current_upserts_parent_active_routes
- [ ] T1.2 追加: test_cmd_done_removes_parent_active_route
- [ ] T1.3 追加: test_set_current_warns_on_parallel_routes
- [ ] T1.4 追加: test_set_current_bootstrap_warn_when_active_routes_absent
- [ ] T2.1 test_sync_linked_command.py 追加: test_sync_linked_repair_routes_rebuilds_from_child_current_feature
- [ ] T2.2 追加: test_sync_linked_repair_routes_skips_completed_features
- [ ] I1  新增 3 个 route helper 函数（_format_route_feature_ref / _upsert_active_route / _remove_active_route）
- [ ] I2  扩展 _notify_parent_sync() 支持 route_event（activate/clear）
- [ ] I2.5 enforce_route_preflight() set-current bootstrap 例外（仅豁免检查5，检查1-4不变）
- [ ] I3  set_current() 末尾调用 _notify_parent_sync("activate")
- [ ] I4  cmd_done() 改为 _notify_parent_sync("clear")
- [ ] I5  sync_linked() 添加 --repair-routes（保留原 JSON 字段，仅增量添加 repair_routes_applied）
- [ ] I6  Dashboard 3-state handoff 输出
- [x] I7  更新 progress-status SKILL.md handoff 模板
- [x] V1  运行 test_scope_fail_closed.py + test_parent_route_writeback_f17.py + 全量测试

## Acceptance Mapping

| Test Step | Verification |
|-----------|-------------|
| 子项目 set-current 14 → parent active_routes 有 PT-F14 | test_set_current_upserts_parent_active_routes ✓ |
| 子项目 /prog done → parent active_routes 移除 PT | test_cmd_done_removes_parent_active_route ✓ |
| root features[] 不复制 child feature | 现有 test_root_dashboard 验证 ✓ |
| set_current() 并行路由 [WARNING] | test_set_current_warns_on_parallel_routes ✓ |
| bootstrap 例外（active_routes 为空） | test_set_current_bootstrap_warn_when_active_routes_absent ✓ |
| sync-linked --repair-routes 重建路由 | test_sync_linked_repair_routes_rebuilds_from_child_current_feature ✓ |
| repair-routes 跳过 completed feature | test_sync_linked_repair_routes_skips_completed_features ✓ |
| 全量测试 1073 passed | uv run pytest tests/ ✓ |

## Risks

- F14/F16 合并后 set_current() 和 cmd_done() 形态变化 → 已验证，实现时确认
- 并行活跃路由造成用户困惑 → dashboard 显式暴露冲突 + [WARNING]
- 父 progress.json 损坏时写入失败为 warn-only → sync-linked --repair-routes 修复

## Tasks

- [x] T1.1 新建 test_parent_route_writeback_f17.py: test_set_current_upserts_parent_active_routes
- [x] T1.2 追加: test_cmd_done_removes_parent_active_route
- [x] T1.3 追加: test_set_current_warns_on_parallel_routes
- [x] T1.4 追加: test_set_current_bootstrap_warn_when_active_routes_absent
- [x] T2.1 test_sync_linked_command.py: test_sync_linked_repair_routes_rebuilds_from_child_current_feature
- [x] T2.2 test_sync_linked_command.py: test_sync_linked_repair_routes_skips_completed_features
- [x] I1  新增 3 个 route helper 函数
- [x] I2  扩展 _notify_parent_sync() 支持 route_event
- [x] I2.5 enforce_route_preflight() set-current bootstrap 例外（仅豁免检查5）
- [x] I3  set_current() 调用 _notify_parent_sync("activate")
- [x] I4  cmd_done() 改为 _notify_parent_sync("clear")
- [x] I5  sync_linked() --repair-routes
- [x] I6  Dashboard 3-state handoff 输出
- [x] I7  更新 progress-status SKILL.md handoff 模板
- [x] V1  1073 passed, 0 failed
