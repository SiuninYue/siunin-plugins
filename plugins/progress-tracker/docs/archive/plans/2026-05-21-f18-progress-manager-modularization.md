# F18: progress_manager.py 深度模块化拆分（Phase 2 技术债偿还）

**Date**: 2026-05-21  
**Complexity**: 61 / standard  
**Branch**: main (in_place)  
**Worktree**: /Users/siunin/Projects/Claude-Plugins
**Rev**: v6（阻断修复计划版）

---

## 目标

将 `hooks/scripts/progress_manager.py`（当前 13,587 行）拆分为职责单一的多模块架构：

- 主入口 `progress_manager.py` 行数大幅降低（见"行数目标说明"）
- 各新增子模块 ≤ 1000 行
- **零行为变更，全套 1073 测试 pass，零测试文件改动**
- 无循环依赖，各子模块可独立 import

---

## P0 硬规则：mock 兼容迁移决策树（最终版）

### 背景

实际运行后，16 个函数同时出现在"被 patch 的符号列表"和"迁移计划清单"中：

```
交集（16 个）：progress_transaction, _run_git, _detect_default_branch,
collect_git_context, _resolve_upstream, _remove_worktree, _delete_local_branch,
_delete_remote_branch, _is_worktree_dirty, analyze_git_auto_preflight,
_resolve_linked_project_root, _get_main_repo_root, _resolve_main_repo_path,
_load_progress_payload_at_root, _save_progress_payload_at_root, _notify_parent_sync
```

### 核心机制

`from submodule import X` 在 pm.py 中创建独立的名字绑定 `pm.X`。
pm.py 中的函数调用 `X()` 使用 pm 命名空间 → `patch("pm.X")` 替换该绑定 → 模拟生效。  
**这意味着：只要被 patch 的函数的调用者（被测试的外层函数）留在 pm.py，
提取 + re-import 就足够，无需改任何测试。**

### 决策树（对 16 个交集符号逐一应用）

```
对于每个被 patch 的符号 X：

测试调用路径：patch("pm.X") → 调用 pm.Y() → Y 内部调用 X

Case A（Y 留在 pm.py，X 可提取）：
  pm.Y() 调用 X()，使用 pm 命名空间中的 X 绑定
  patch("pm.X") 替换 pm.X 绑定 → Y 调用 mock ✓
  → X 可以提取到子模块 + re-import 到 pm.py

Case B（Y 也被提取到子模块）：
  子模块 Y 调用 submodule.X（子模块命名空间）
  patch("pm.X") 不影响子模块命名空间 → Y 不调用 mock ✗
  → X 不可提取，必须留在 pm.py 中保留定义

Case C（X 被直接测试，且 X 调用另一个被 patch 的 dep）：
  test 调用 pm.X()，X 内部调用 dep。若 X 在子模块中，
  X 通过子模块命名空间调用 dep（不是 pm 命名空间）
  patch("pm.dep") 不生效 ✗
  → X 不可提取，必须在 pm.py 中保留定义
```

### 应用结果：16 个符号的最终归属

#### 不可提取（定义必须在 pm.py）：3 个

| 符号 | Case | 原因 |
|------|------|------|
| `analyze_git_auto_preflight` | C | 直接被 test_progress_manager.py:1501 调用，内部调用 mocked `collect_git_context`/`_detect_default_branch`/`analyze_git_sync_risks` |
| `_resolve_main_repo_path` | C | 直接被 test_git_worktree_support.py:38/56 调用，内部调用 mocked `_get_main_repo_root` |
| `_save_progress_payload_at_root` | C | 直接被 test_git_worktree_support.py:233/296 调用，内部调用 mocked `progress_transaction` |

这 3 个函数的实现代码保留在 pm.py（不是子模块的 wrapper），外层调用者（`link_project`、`git_auto_preflight`、`_run_post_done_cleanup`）也留在 pm.py。

#### 可提取 + re-import（pm.py 补 import 绑定，无需改测试）：13 个

| 符号 | 目标子模块 | 调用者（留在 pm.py） | patch 仍通过 pm |
|------|-----------|-------------------|----------------|
| `progress_transaction` | `lock_manager` | `_save_progress_payload_at_root` | `pm.progress_transaction` ✓ |
| `_run_git` | `git_utils` | `_check_other_worktrees_for_incomplete_work`（pm.py） | `pm._run_git` ✓ |
| `_detect_default_branch` | `git_utils` | `analyze_git_auto_preflight`（pm.py） | `pm._detect_default_branch` ✓ |
| `collect_git_context` | `git_utils` | `analyze_git_auto_preflight`（pm.py） | `pm.collect_git_context` ✓ |
| `_resolve_upstream` | `git_utils` | `_run_post_done_cleanup`（pm.py） | `pm._resolve_upstream` ✓ |
| `_remove_worktree` | `git_utils` | `_run_post_done_cleanup`（pm.py） | `pm._remove_worktree` ✓ |
| `_delete_local_branch` | `git_utils` | `_run_post_done_cleanup`（pm.py） | `pm._delete_local_branch` ✓ |
| `_delete_remote_branch` | `git_utils` | `_run_post_done_cleanup`（pm.py） | `pm._delete_remote_branch` ✓ |
| `_is_worktree_dirty` | `worktree_handler` | `_run_post_done_cleanup`（pm.py） | `pm._is_worktree_dirty` ✓ |
| `_notify_parent_sync` | `route_sync` | `set_current`/`cmd_done`（pm.py） | `pm._notify_parent_sync` ✓ |
| `_resolve_linked_project_root` | `route_sync` | `link_project`（pm.py） | `pm._resolve_linked_project_root` ✓ |
| `_get_main_repo_root` | `route_sync` | `_resolve_main_repo_path`（pm.py） | `pm._get_main_repo_root` ✓ |
| `_load_progress_payload_at_root` | `route_sync` | `sync_linked`（pm.py） | `pm._load_progress_payload_at_root` ✓ |

---

## F18 阻断修复计划 (v6 审查修复版)

针对 2026-05-24 二次审查确认的阻断项（`_PROJECT_ROOT_OVERRIDE/get_progress_dir`、`_PROGRESS_LOCK_DEPTHS`、`save_progress_json` 签名、`load/save_progress_md` wrapper 冲突、`schema_migration` 审计语义），制定以下修复设计：

1. **保留 Mock 兼容（问题 1、2、4）— 薄 wrapper + 参数注入模式**：
   - 全局变量 `_PROJECT_ROOT_OVERRIDE`、`_ensure_storage_ready()`、`find_project_root()` 与 `get_progress_dir()` **保留在 `progress_manager.py` 中**。
   - 这确保了测试代码对 `progress_manager._PROJECT_ROOT_OVERRIDE` 和 `progress_manager.get_progress_dir` 的 patch/赋值操作依然能在 `progress_manager` 命名空间正常生效，**完全杜绝 Case C 类型的 Mock 穿透问题**。
   - 拆分出来的底层子模块（如 `lock_manager.py` 和 `state_io.py`）采用 **参数注入设计**：模块内部的底层逻辑不直接调用 `find_project_root()` 或 `get_progress_dir()`，而是将其定义为显式参数（如 `project_root: Path`、`progress_dir: Path`）接收。
   - 在 `pm.py` 中保留薄的 API wrapper（如 `progress_transaction` 和 `load_progress_json`），在调用底层时自动解析并注入 `project_root = project_root or find_project_root()` / `progress_dir = progress_dir or get_progress_dir()`，维持向后兼容性。

2. **解决循环依赖 (问题 A) 与 lock 深度兼容 (新增阻断项)**：
   - 底层 `lock_manager.py` 和 `state_io.py` 等不再导入 `progress_manager.py`，依赖方向干净单向流。
   - `_PROGRESS_LOCK_HANDLES` 和 `_PROGRESS_LOCK_DEPTHS` 的“真实定义”仅保留在 `lock_manager.py`。
   - `pm.py` 保留**兼容别名导出**（`pm._PROGRESS_LOCK_DEPTHS` / `pm._PROGRESS_LOCK_HANDLES`）用于既有测试读取，业务代码禁止直接读写；等 F18-Phase2 再统一替换测试后移除。

3. **解决 state_io 提取不完整 + 签名回归风险（新增阻断项）**：
   - 将 `load_progress_json`、`save_progress_json`、`load_progress_md`、`save_progress_md` 从 `progress_manager.py` 移入 `state_io.py`（改写为接收 `progress_dir: Path` 显式参数）。
   - `save_progress_json` 在 `state_io.py` 中保留参数 `touch_updated_at: bool = True`，`pm.py` wrapper 也保留同名参数，保证与现有调用/测试兼容。
   - `_apply_schema_defaults` 采用“核心逻辑下沉 + pm wrapper 保留”策略：`state_io.py` 提供 `_apply_schema_defaults_core(...)`；`pm.py` 继续提供 `_apply_schema_defaults(...)` 入口以维持导入路径兼容。
   - `state_io.py` 的行数将补齐至原计划约定的 `~800` 行，使 `pm.py` 的物理缩减达到预期。

4. **解决 `schema_migration` 审计语义保真（新增重要缺口）**：
   - `state_io._apply_schema_defaults_core(...)` 返回迁移元信息（如 `("2.0","2.1")`）。
   - `pm._apply_schema_defaults(...)` 在收到迁移元信息时，通过 `pm._append_audit_event(...)` 写入 `schema_migration`，保持现有 `project_root` 路由语义与测试行为不变。

5. **解决 workflow_state 任务追踪失效 (问题 E)**：
   - 在状态机流转和 `/prog done` 相关的归档/清理逻辑中，在 `workflow_state` 下正确记录已完成的任务 `completed_tasks` 列表与总任务数 `total_tasks`，使进度百分比自动呈现。

---

## 行数目标说明（诚实估算）

当前 13,587 行的组成：
- 可安全提取的代码（state_io/lock/git_utils/worktree/route_sync）：约 3,500 行
- 必须留在 pm.py 的代码（cmd_*, status, next_feature, reconcile, main() 等）：约 10,000 行

**Method A（零测试改动）可实现的目标：pm.py ≤ ~10,000 行**（相比原始 13,587 行减少约 27%）

**要达到 ≤ 1500 行**，需要将 cmd_* 和 main() 也迁移到 `cmd_handlers/` 子目录。
这会要求把 ~65 个测试 patch 路径从 `"progress_manager.X"` 改为 `"cmd_handlers.X"` 或
`"cmd_handlers.done.X"` 等（Method B）。

**F18 本次执行的目标**：
- 实施 Method A，提取 7 个子模块
- pm.py 减少至约 **≤ 10,000 行**（从 13,587 下降 ~27%）
- 这已消除最紧急的 AI 读取障碍（state_io/git/route 可独立阅读）
- 行数目标 "≤ 1500" 留给 F18-Phase2（允许 Method B 测试更新），作为 F19 前的可选 follow-up

---

## 目标模块结构

| 文件 | 职责 | 预计行数 | 主要内容 |
|------|------|---------|---------|
| `lock_manager.py` | 文件锁与事务 | ~120 | `_progress_lock_path`, `_acquire_progress_lock`, `_release_progress_lock`, `progress_transaction`, `PROGRESS_LOCK_TIMEOUT_SECONDS`（锁深度字典真实定义在本模块） |
| `state_io.py` | progress.json 读写 + schema 规范化 | ~800 | `load_progress_json`, `save_progress_json(touch_updated_at=...)`, `load_progress_md`, `save_progress_md`, `_atomic_write_text`, `_apply_schema_defaults_core` 及所有 schema helpers（含 `_normalize_linked_schema`, `_normalize_route_schema`, `_default_linked_snapshot`） |
| `git_utils.py` | Git 基础操作 | ~900 | `_run_git`, `_get_dirty_state_files`, `_git_commit_state`, `_auto_state_commit`, `_git_squash_close_task`, `_detect_default_branch`, `collect_git_context`, `analyze_git_sync_risks`, `git_sync_check`, `build_runtime_context`（及变体）, `_resolve_upstream`, `_remove_worktree`, `_delete_local_branch`, `_delete_remote_branch`, `_get_head_commit` |
| `worktree_handler.py` | Worktree 路径解析 | ~400 | `_parse_worktree_list_output`, `_extract_branch_name_from_worktree_ref`, `_count_branch_commits_behind`, `_find_existing_worktree_candidates_for_feature`, `_local_and_origin_ref_candidates`, `_is_branch_merged_into`, `_is_worktree_dirty` |
| `route_sync.py` | Active routes 状态管理 + linked snapshot | ~700 | `_upsert_active_route`, `_remove_active_route`, `_format_route_feature_ref`, `_detect_parallel_active_routes`, `_notify_parent_sync`, `_get_main_repo_root`, `_resolve_linked_project_root`, `_load_progress_payload_at_root`, `_count_feature_completion`, `_is_linked_snapshot_stale`, `_iter_linked_project_specs`, `_normalize_project_code`, `_serialize_project_root_for_config` |
| `route_commands.py` | 路由 CLI 命令 + preflight 守卫 | ~700 | `route_status`, `prioritize_route`, `set_routing_queue`, `_resolve_repo_root`, `route_select`, `discover_children`, `_auto_discover_child_plugins`, `_discover_plugin_catalog`, `_derive_plugin_code`, `_generate_project_code`, `_discover_parent_route_bindings_for_child`, `_print_route_preflight_block`, `enforce_route_preflight` |
| `evaluator_gateway.py` | Evaluator 调用 | ~200 | `_emit`, `reconcile_evaluator`, `_collect_ship_signals`（**注意：`cmd_ship_check` 不在此，留在 pm.py**） |

**pm.py 新增的 re-import 与薄 wrapper 块**：

```python
# lock_manager wrappers & re-exports
import lock_manager
from lock_manager import PROGRESS_LOCK_TIMEOUT_SECONDS

# compatibility aliases (existing tests read pm._PROGRESS_LOCK_DEPTHS)
_PROGRESS_LOCK_HANDLES = lock_manager._PROGRESS_LOCK_HANDLES
_PROGRESS_LOCK_DEPTHS = lock_manager._PROGRESS_LOCK_DEPTHS

def _progress_lock_path(project_root: Optional[Path] = None) -> Path:
    root = project_root if project_root is not None else find_project_root()
    return lock_manager._progress_lock_path(project_root=root)

def _acquire_progress_lock(timeout_seconds: float = PROGRESS_LOCK_TIMEOUT_SECONDS, project_root: Optional[Path] = None):
    root = project_root if project_root is not None else find_project_root()
    return lock_manager._acquire_progress_lock(timeout_seconds=timeout_seconds, project_root=root)

def _release_progress_lock(project_root: Optional[Path] = None):
    root = project_root if project_root is not None else find_project_root()
    return lock_manager._release_progress_lock(project_root=root)

@contextmanager
def progress_transaction(timeout_seconds: float = PROGRESS_LOCK_TIMEOUT_SECONDS, project_root: Optional[Path] = None):
    root = project_root if project_root is not None else find_project_root()
    with lock_manager.progress_transaction(timeout_seconds=timeout_seconds, project_root=root):
        yield

# state_io wrappers & re-exports
import state_io
from state_io import (
    _atomic_write_text, _default_linked_snapshot, _normalize_linked_schema,
    _normalize_route_schema, _default_sprint_contract, _default_quality_gates,
    _sync_reviews_pending_cache, _default_handoff, _apply_schema_defaults_core
)

def _apply_schema_defaults(data: Dict[str, Any]) -> None:
    migrated = state_io._apply_schema_defaults_core(data)
    if migrated is not None:
        old_version, new_version = migrated
        _append_audit_event(
            event_type="schema_migration",
            details={"from": old_version, "to": new_version},
        )

def load_progress_json(progress_dir: Optional[Path] = None) -> Dict[str, Any]:
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.load_progress_json(
        progress_dir=dir_path,
        apply_schema_defaults=_apply_schema_defaults,
    )

def save_progress_json(
    data: Dict[str, Any],
    touch_updated_at: bool = True,
    progress_dir: Optional[Path] = None,
) -> None:
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.save_progress_json(
        progress_dir=dir_path,
        data=data,
        touch_updated_at=touch_updated_at,
        apply_schema_defaults=_apply_schema_defaults,
        now_fn=_iso_now,
    )

def load_progress_md(progress_dir: Optional[Path] = None) -> str:
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.load_progress_md(progress_dir=dir_path)

def save_progress_md(content: str, progress_dir: Optional[Path] = None) -> None:
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.save_progress_md(progress_dir=dir_path, content=content)
```

# git_utils re-exports（保持 pm.X 名字绑定，现有测试 patch("pm.X") 继续有效）
from git_utils import (
    _run_git, _detect_default_branch, collect_git_context, analyze_git_sync_risks,
    _resolve_upstream, _remove_worktree, _delete_local_branch, _delete_remote_branch,
    _get_head_commit, _git_squash_close_task, # ...etc
)

# worktree_handler re-exports
from worktree_handler import _is_worktree_dirty, # ...

# route_sync re-exports
from route_sync import (
    _notify_parent_sync, _resolve_linked_project_root,
    _load_progress_payload_at_root, _get_main_repo_root,
    # ...
)
```
---

## 依赖方向（禁止反向）

```
prog_paths.py（已存在）
      ↓
lock_manager.py
      ↓
state_io.py
      ↓
git_utils.py        worktree_handler.py
      ↓                     ↓
      └────── route_sync.py ┘
                    ↓
          route_commands.py    evaluator_gateway.py
                    ↓                  ↓
         progress_manager.py（thin dispatcher，re-imports all above）
```

---

## 执行任务列表

### Pre-Task 0: Mock 列表确认

```bash
cd /Users/siunin/Projects/Claude-Plugins
python3 -c "
import re, pathlib
tests = pathlib.Path('plugins/progress-tracker/tests')
syms = set()
for f in tests.glob('*.py'):
    for m in re.finditer(r'patch\([\"\'']progress_manager\.([^\"\'()]+)', f.read_text()):
        syms.add(m.group(1))
print('\n'.join(sorted(syms)))
"
```

预期输出包含 16 个交集符号。任何不在上表中的符号出现时，立即暂停执行并分析其 Case（A/B/C）。

---

### Task 0: 引入路径解析的显式参数化支持

**prog_paths.py 变更**（修改路径助手以接受显式 override 参数）：
- 重构 `find_project_root(override: Optional[str] = None) -> Path`：若传入 `override` 则优先返回，否则按原逻辑自动解析。

**pm.py 变更**：
- 保留 `_PROJECT_ROOT_OVERRIDE` 变量、`find_project_root()` 与 `get_progress_dir()`，其内部作为薄 wrapper 转发给 `prog_paths`（传入本地的 `_PROJECT_ROOT_OVERRIDE`）。
- **这确保了测试中对 `pm._PROJECT_ROOT_OVERRIDE` 及 `pm.get_progress_dir` 的 Mock 依然 100% 有效。**

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 1: 提取 lock_manager.py 并引入参数注入与状态封锁

**移动函数**（搬移至 `lock_manager.py`，但改写签名以支持注入）：
- `PROGRESS_LOCK_TIMEOUT_SECONDS`
- `_progress_lock_path(project_root: Path)`（将可选改为必填 Path）
- `_acquire_progress_lock(timeout_seconds: float, project_root: Path)`
- `_release_progress_lock(project_root: Path)`
- `progress_transaction(timeout_seconds: float, project_root: Path)`

**lock_manager.py 变更**：
- 内部私有字典 `_PROGRESS_LOCK_HANDLES` 和 `_PROGRESS_LOCK_DEPTHS` 仅在 `lock_manager.py` 内定义，完全私有化。
- **严禁从 `progress_manager` 导入 `find_project_root()`**；`lock_manager.py` 仅接收显式注入的 `project_root`。

**pm.py 变更**：
- 保留 `_PROGRESS_LOCK_HANDLES` 和 `_PROGRESS_LOCK_DEPTHS` 的**兼容别名导出**（指向 `lock_manager` 中的真实字典），仅用于既有测试读取。
- 实现薄 wrapper 负责注入 `project_root`，供业务逻辑和测试直接调用：
```python
def progress_transaction(
    timeout_seconds: float = lock_manager.PROGRESS_LOCK_TIMEOUT_SECONDS,
    project_root: Optional[Path] = None,
):
    root = project_root if project_root is not None else find_project_root()
    return lock_manager.progress_transaction(timeout_seconds=timeout_seconds, project_root=root)
```

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
python -c "import lock_manager; print('lock_manager ok')"
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 2: 提取 state_io.py 并引入参数注入与完整读写迁移

**移动函数**（搬移至 `state_io.py`，并对读写签名改写为显式接收 `progress_dir: Path`）：
- `_atomic_write_text`
- `_default_sprint_contract`
- `_default_quality_gates`
- `_sync_reviews_pending_cache`
- `_default_handoff`
- `_default_linked_snapshot`
- `_normalize_linked_schema`
- `_normalize_route_schema`
- `_apply_schema_defaults_core`（纯逻辑，不直接写 audit）
- `load_progress_json(progress_dir: Path, apply_schema_defaults: Callable[[Dict[str, Any]], None])`
- `save_progress_json(progress_dir: Path, data: Dict[str, Any], touch_updated_at: bool = True, apply_schema_defaults: Callable[[Dict[str, Any]], None], now_fn: Callable[[], str])`
- `load_progress_md(progress_dir: Path)`
- `save_progress_md(progress_dir: Path, content: str)`

**state_io.py 依赖**：`lock_manager.progress_transaction`，`json`，`pathlib`，`datetime`，**不依赖 `get_progress_dir` 或 `progress_manager` 的任何状态**（一律由调用方注入）。

**pm.py 变更**：
- 保留薄 wrapper 自动解析并注入 `progress_dir`，确保对测试 patch 透明：
```python
def load_progress_json(progress_dir: Optional[Path] = None) -> Dict[str, Any]:
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.load_progress_json(progress_dir=dir_path, apply_schema_defaults=_apply_schema_defaults)

def save_progress_json(data: Dict[str, Any], touch_updated_at: bool = True, progress_dir: Optional[Path] = None) -> None:
    dir_path = progress_dir if progress_dir is not None else get_progress_dir()
    return state_io.save_progress_json(
        progress_dir=dir_path,
        data=data,
        touch_updated_at=touch_updated_at,
        apply_schema_defaults=_apply_schema_defaults,
        now_fn=_iso_now,
    )
```
- `pm.py` 保留 `_apply_schema_defaults(data)` 公共入口（内部转发 `state_io._apply_schema_defaults_core` 并在版本升级时写入 `schema_migration` 审计事件）。
- 从 `state_io` 导入其它 schema helpers（**不直接导入 `load_progress_md/save_progress_md`，避免覆盖 wrapper 签名**）：
```python
from state_io import (
    _atomic_write_text, _default_linked_snapshot, _normalize_linked_schema,
    _normalize_route_schema, _default_sprint_contract, _default_quality_gates,
    _sync_reviews_pending_cache, _default_handoff, _apply_schema_defaults_core,
)
```

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
python -c "import state_io; print('state_io ok')"
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 3: 提取 git_utils.py（中等风险）

**移动函数**（新建 hooks/scripts/git_utils.py）：
- `_run_git` (~6078)
- `_get_dirty_state_files` (~6109)
- `_git_commit_state` (~6167)
- `_auto_state_commit` (~6233)
- `_detect_default_branch` (~6441)
- `_git_squash_close_task` (~6470)
- `collect_git_context` (~4447)
- `build_runtime_context` (~4520)
- `build_execution_context` (~4542)
- `_runtime_context_fingerprint` (~4559)
- `_update_runtime_context` (~4573)
- `_update_execution_context` (~4588)
- `compare_contexts` (~4595)
- `_format_context_summary` (~4719)
- `analyze_git_sync_risks` (~6586)
- `git_sync_check` (~6805)
- `_resolve_upstream` (~8998)
- `_remove_worktree` (~9026)
- `_delete_local_branch` (~9046)
- `_delete_remote_branch` (~9072)
- `_get_head_commit` (~9140)

**git_utils.py 依赖**：`state_io.load_progress_json`, `prog_paths`, `subprocess`, `re`, `pathlib`

**pm.py 变更**：  
以下符号 re-import 后测试 patch 继续有效（pm 命名空间保持）：
```python
from git_utils import (
    _run_git, _detect_default_branch, collect_git_context, analyze_git_sync_risks,
    git_sync_check, _resolve_upstream, _remove_worktree, _delete_local_branch,
    _delete_remote_branch, _get_head_commit, _git_squash_close_task,
    build_runtime_context, collect_git_context,
    # ... others
)
```

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
python -c "import git_utils; print('git_utils ok')"
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 4: 提取 worktree_handler.py（中等风险）

**移动函数**（新建 hooks/scripts/worktree_handler.py）：
- `_parse_worktree_list_output` (~6278)
- `_extract_branch_name_from_worktree_ref` (~6304)
- `_count_branch_commits_behind` (~6317)
- `_find_existing_worktree_candidates_for_feature` (~6348)
- `_local_and_origin_ref_candidates` (~6555)
- `_is_branch_merged_into` (~6566)
- `_is_worktree_dirty` (~8979)

**注意**：`analyze_git_auto_preflight`、`git_auto_preflight`、`_check_other_worktrees_for_incomplete_work`、`check_worktree_branch_consistency` 不在此处，它们留在 pm.py（P0 不可提取组）。

**worktree_handler.py 依赖**：`git_utils._run_git`, `state_io.load_progress_json`, `prog_paths`

**pm.py 变更**：
```python
from worktree_handler import (
    _is_worktree_dirty, _parse_worktree_list_output,
    # ...
)
```

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
python -c "import worktree_handler; print('worktree_handler ok')"
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 5: 提取 route_sync.py（中等高风险）

**移动函数**（新建 hooks/scripts/route_sync.py）：
- `_count_feature_completion` (~1071)
- `_is_linked_snapshot_stale` (~1087)
- `_iter_linked_project_specs` (~965)
- `_resolve_linked_project_root` (~1002)
- `_get_main_repo_root` (~1024)
- `_resolve_main_repo_path` 的辅助函数（不包含 `_resolve_main_repo_path` 本身，见 P0 不可提取组）
- `_load_progress_payload_at_root` (~1418)
- `_normalize_project_code` (~1393)
- `_serialize_project_root_for_config` (~1403)
- `_format_route_feature_ref` (~1452)
- `_upsert_active_route` (~1457)
- `_remove_active_route` (~1480)
- `_detect_parallel_active_routes` (~1370)
- `_notify_parent_sync` (~1496)

**_save_progress_payload_at_root 保持在 pm.py**（不迁移，P0 不可提取组）。

**route_sync.py 依赖**：`state_io.load_progress_json`, `prog_paths`, `json`, `pathlib`  

**pm.py 变更**：
```python
from route_sync import (
    _notify_parent_sync, _resolve_linked_project_root, _load_progress_payload_at_root,
    _get_main_repo_root, _upsert_active_route, _remove_active_route,
    _format_route_feature_ref, _count_feature_completion, _is_linked_snapshot_stale,
    # ...
)
```

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
python -c "import route_sync; print('route_sync ok')"
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/test_parent_route_writeback_f17.py \
  plugins/progress-tracker/tests/test_sync_linked_command.py \
  plugins/progress-tracker/tests/test_route_commands.py -q --tb=short
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 6: 提取 route_commands.py（中等高风险）

**移动函数**（新建 hooks/scripts/route_commands.py）：
- `_link_child_to_parent` (~1925)
- `_discover_plugin_catalog` (~1875)
- `_derive_plugin_code` (~1824)
- `_generate_project_code` (~1840)
- `_auto_discover_child_plugins` (~2037)
- `discover_children` (~2159)
- `route_status` (~2209)
- `prioritize_route` (~2312)
- `set_routing_queue` (~2386)
- `_resolve_repo_root` (~2477)
- `route_select` (~2483)
- `_discover_parent_route_bindings_for_child` (~12144)
- `_print_route_preflight_block` (~12203)
- `enforce_route_preflight` (~12253)

**注意**：`link_project` 不在此处，留在 pm.py（P0 不可提取组，调用多个 mocked 函数）。

**route_commands.py 依赖**：`route_sync`, `state_io`, `git_utils._run_git`, `prog_paths`

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
python -c "import route_commands; print('route_commands ok')"
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/test_scope_fail_closed.py \
  plugins/progress-tracker/tests/test_root_dashboard.py -q --tb=short
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 7: 提取 evaluator_gateway.py（中等风险）

**移动函数**（新建 hooks/scripts/evaluator_gateway.py）：
- `_emit` (~3874)
- `reconcile_evaluator` (~3889)
- `_collect_ship_signals` (~9688)

**cmd_ship_check 不迁移**，留在 pm.py（cmd_* 规则：以 `cmd_` 开头的函数不迁移）。  
`_store_evaluator_result` 也不迁移（调用 `_resolve_main_repo_path`，后者在 pm.py 中）。

**evaluator_gateway.py 依赖**：`state_io`, `evaluator_gate`（已存在）

**验证**：
```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
python -c "import evaluator_gateway; print('evaluator_gateway ok')"
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/ -q --tb=no
```

---

### Task 8: F19 Dogfooding — 写入 docs/changes/

创建目录和文件（相对于 progress-tracker 目录）：
```
docs/changes/index.jsonl
docs/changes/20260521-pm-modularize-<4hex>.md
```

生成 4hex：`python -c "import random; print('%04x'%random.randint(0,65535))"`

`index.jsonl` 首条记录（一行 JSON，不得折行）：
```json
{"change_id": "20260521-pm-modularize-XXXX", "date": "2026-05-21", "component": "progress_manager", "summary": "拆分 progress_manager.py 为 7 个子模块（Method A，零测试改动）", "root_cause": "13,587 行单文件导致 AI session 无法全量读取，影响高风险修复定位", "fixes": ["F18"], "touched_files": ["hooks/scripts/progress_manager.py", "hooks/scripts/lock_manager.py", "hooks/scripts/state_io.py", "hooks/scripts/git_utils.py", "hooks/scripts/worktree_handler.py", "hooks/scripts/route_sync.py", "hooks/scripts/route_commands.py", "hooks/scripts/evaluator_gateway.py"], "test_command": "uv run pytest plugins/progress-tracker/tests/ -q", "test_result": "1073 passed", "rollback_strategy": "git revert <squash_commit_sha>", "record_path": "docs/changes/20260521-pm-modularize-XXXX.md"}
```

---

### Task 9: 全套验收验证

```bash
# 1. 独立 import 检查
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
for mod in lock_manager state_io git_utils worktree_handler route_sync route_commands evaluator_gateway; do
  python -c "import $mod; print('$mod ok')" || echo "FAIL: $mod"
done

# 2. 行数检查
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts
wc -l progress_manager.py lock_manager.py state_io.py git_utils.py worktree_handler.py route_sync.py route_commands.py evaluator_gateway.py

# 3. 全套测试（零回归）
cd /Users/siunin/Projects/Claude-Plugins
uv run pytest plugins/progress-tracker/tests/ -q

# 4. 核心命令 smoke test
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker
./prog status
./prog next-feature --json
./prog git-sync-check
```

---

## Acceptance Mapping (验收标准 v6 阻断修复版)

- [ ] 7 个新增子模块以及解耦后的 `prog_paths` 均可独立 import 通过。
- [ ] 各子模块（包括 `state_io.py`）`wc -l` 均 ≤ 1000 行。
- [ ] `state_io.py` 完整迁入了包括 `load_progress_json` / `save_progress_json` 等在内的状态读写函数，行数在 `~800` 行左右。
- [ ] 各新增模块（特别是 `lock_manager.py` 和 `state_io.py`）无任何向 `progress_manager.py` 的反向或循环导入。
- [ ] `_PROGRESS_LOCK_HANDLES` / `_PROGRESS_LOCK_DEPTHS` 的真实定义仅存在于 `lock_manager.py`；`pm.py` 仅保留兼容别名（用于既有测试读取）。
- [ ] `save_progress_json` 对外签名保持兼容：`save_progress_json(data, touch_updated_at: bool = True)`，原测试调用零改动通过。
- [ ] `load_progress_md()` / `save_progress_md(content)` 在 `pm.py` 仍保持 wrapper 入口，不被 `from state_io import ...` 覆盖。
- [ ] `_apply_schema_defaults` 的对外导入路径仍为 `progress_manager._apply_schema_defaults`，且 `schema_version 2.0 -> 2.1` 时仍写入 `schema_migration` 审计事件。
- [ ] `workflow_state` 的 `completed_tasks` 与 `total_tasks` 会在流程扭转时被正确回填，任务进度可被正常追踪。
- [ ] `uv run pytest plugins/progress-tracker/tests/ -q` → 全部 pass，**零回归，零测试文件改动**。
- [ ] `pm.py` 行数减少（从 13,587 降至约 ≤ 10,000，当前已合并的减幅由于 `state_io` 完整迁移而显著拉大）。
- [ ] `docs/changes/index.jsonl` 存在，首条 F18 dogfooding 记录合规 JSONL。
- [ ] `_save_progress_payload_at_root` 保留 `progress_transaction` + `_atomic_write_text` 完整语义。

---

## Risks (风险矩阵 v6 修复版)

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| mock patch 失效 | ✅ 已解决 | Case A/B/C 决策树；3 个不可提取函数留 pm.py；13 个 re-import 保持 pm 命名空间绑定 |
| `_PROJECT_ROOT_OVERRIDE` / `get_progress_dir` mock 穿透 | ✅ 已解决 | 两者保留在 pm.py；子模块仅接受参数注入，不直接依赖 pm 全局状态 |
| `_PROGRESS_LOCK_DEPTHS` 兼容性回归 | ✅ 已解决 | 真实状态留 lock_manager；pm 暴露兼容别名供旧测试读取 |
| `save_progress_json` 签名回归（`touch_updated_at` 丢失） | ✅ 已解决 | state_io 与 pm wrapper 同步保留 `touch_updated_at: bool = True` |
| `load/save_progress_md` wrapper 被导入覆盖 | ✅ 已解决 | 禁止直接从 state_io 导入 `load_progress_md/save_progress_md`，pm 固定 wrapper 入口 |
| `schema_migration` 审计语义漂移 | ✅ 已解决 | `_apply_schema_defaults_core` 返回迁移信息；pm wrapper 统一写审计事件 |
| state_io↔route 循环 | ✅ 已解决 | _normalize_linked/route_schema + _default_linked_snapshot 归入 state_io |
| route 模块超 1000 行 | ✅ 已解决 | 拆分为 route_sync + route_commands |
| 遗漏 preflight 依赖函数 | ✅ 已解决 | Task 6 包含 _discover_parent_route_bindings_for_child, _print_route_preflight_block |
| 验证路径错误 | ✅ 已解决 | 统一用全路径；import 检查从 hooks/scripts 执行 |
| _save_progress_payload_at_root 锁语义丢失 | ✅ 已解决 | 函数留在 pm.py，调用 pm.progress_transaction + pm._atomic_write_text；不改变实现 |
| cmd_ship_check 误迁移 | ✅ 已解决 | cmd_* 硬规则：不迁移；evaluator_gateway 只含 _emit, reconcile_evaluator, _collect_ship_signals |
| ≤1500 行目标未达成 | ⚠️ 已知 | 明确为 Phase 2 任务；本次目标 ≤ 10,000 行，7 个子模块可独立阅读，已解决核心痛点 |
