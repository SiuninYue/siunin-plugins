# [RouteV1] route-status / route-select 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `progress_manager.py` 中新增两个 CLI 命令：`route-status`（只读，输出路由状态与冲突摘要）和 `route-select`（写操作，按 `project_code` 唯一键 upsert active_routes）。

**Architecture:** 两个命令均遵循现有 `link-project` 模式 — 独立函数 + argparse subparser + `_dispatch_command()` 分发。`route-select` 加入 `MUTATING_COMMANDS` 并受 `progress_transaction()` 保护；`route-status` 为只读，不加入 MUTATING_COMMANDS。`route-select` 写回时同步调用 `_update_runtime_context` 和 `save_progress_md`（与 `link_project` 一致）。

**Tech Stack:** Python 3, argparse, 现有 `load_progress_json()` / `save_progress_json()` / `_update_runtime_context()` / `save_progress_md()` 基础设施。

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `tests/test_route_commands.py` | route-status + route-select 函数级与 CLI 级测试 |
| 修改 | `hooks/scripts/progress_manager.py` | 函数实现 + MUTATING_COMMANDS + argparse + dispatch |

---

## Task 1: 为 `route-status` 写失败测试

**Files:**
- Create: `tests/test_route_commands.py`

- [ ] **Step 1: 写失败测试**

```python
"""Tests for route-status and route-select commands."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import progress_manager


def _write_progress(root: Path, payload: dict) -> None:
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _base_progress() -> dict:
    return {
        "project_name": "Test Project",
        "schema_version": "2.0",
        "features": [],
        "current_feature_id": None,
        "updates": [],
        "retrospectives": [],
        "tracker_role": "parent",
        "project_code": "PT",
        "linked_projects": [
            {"project_root": "plugins/note-organizer", "project_code": "NO", "label": "Note Organizer"},
        ],
        "routing_queue": ["NO"],
        "active_routes": [],
        "linked_snapshot": {"schema_version": "1.0", "updated_at": None, "projects": []},
    }


# --- route-status tests ---

def test_route_status_shows_routing_queue(temp_dir, capsys):
    """route_status() prints routing_queue codes."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "NO" in output


def test_route_status_shows_active_routes(temp_dir, capsys):
    """route_status() prints active_routes entries."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F3"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "NO-F3" in output


def test_route_status_detects_conflict_type_a(temp_dir, capsys):
    """route_status() detects Type A: duplicate project_code in active_routes."""
    data = _base_progress()
    data["active_routes"] = [
        {"project_code": "NO", "feature_ref": "NO-F1"},
        {"project_code": "NO", "feature_ref": "NO-F2"},
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "conflict" in output.lower() or "duplicate" in output.lower()


def test_route_status_detects_conflict_type_b(temp_dir, capsys):
    """route_status() detects Type B: code in routing_queue not in linked_projects."""
    data = _base_progress()
    data["routing_queue"] = ["NO", "GHOST"]  # GHOST not in linked_projects
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "GHOST" in output
    assert "conflict" in output.lower() or "not linked" in output.lower() or "unlinked" in output.lower()


def test_route_status_no_conflicts(temp_dir, capsys):
    """route_status() shows no conflict section when clean."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status()

    assert result is True
    output = capsys.readouterr().out
    assert "conflict" not in output.lower()


def test_route_status_json_output(temp_dir, capsys):
    """route_status(output_json=True) emits valid JSON with routing_queue, active_routes, conflicts."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F1"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_status(output_json=True)

    assert result is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["routing_queue"] == ["NO"]
    assert payload["active_routes"] == [{"project_code": "NO", "feature_ref": "NO-F1"}]
    assert "conflicts" in payload
    assert isinstance(payload["conflicts"], list)
```

- [ ] **Step 2: 运行测试，确认全部失败**

```bash
cd /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker
python -m pytest tests/test_route_commands.py -v 2>&1 | head -30
```

预期：`AttributeError: module 'progress_manager' has no attribute 'route_status'`

---

## Task 2: 实现 `route_status()` 函数

**Files:**
- Modify: `hooks/scripts/progress_manager.py`（在 `link_project` 函数之后，约第 1358 行附近添加）

- [ ] **Step 3: 实现函数**

在 `progress_manager.py` 中 `link_project` 函数结尾（约第 1357 行）之后插入：

```python
def route_status(*, output_json: bool = False) -> bool:
    """Display routing_queue, active_routes, and conflict summary."""
    data = load_progress_json()
    if not data:
        message = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    routing_queue: List[str] = data.get("routing_queue") or []
    if not isinstance(routing_queue, list):
        routing_queue = []

    active_routes: List[Any] = data.get("active_routes") or []
    if not isinstance(active_routes, list):
        active_routes = []

    linked_projects: List[Any] = data.get("linked_projects") or []
    if not isinstance(linked_projects, list):
        linked_projects = []

    # Collect linked project codes for conflict Type B check
    linked_codes: set = set()
    for entry in linked_projects:
        if isinstance(entry, dict):
            code_raw = entry.get("project_code")
            if isinstance(code_raw, str) and code_raw.strip():
                linked_codes.add(code_raw.strip().upper())

    # Detect conflicts
    conflicts: List[Dict[str, Any]] = []

    # Type A: duplicate project_code in active_routes
    seen_codes: Dict[str, int] = {}
    for route in active_routes:
        if not isinstance(route, dict):
            continue
        code_raw = route.get("project_code")
        if not isinstance(code_raw, str):
            continue
        code = code_raw.strip().upper()
        seen_codes[code] = seen_codes.get(code, 0) + 1
    for code, count in seen_codes.items():
        if count > 1:
            conflicts.append(
                {"type": "A", "code": code, "message": f"duplicate in active_routes ({count} entries)"}
            )

    # Type B: routing_queue code not in linked_projects
    for item in routing_queue:
        if not isinstance(item, str):
            continue
        code = item.strip().upper()
        if code and code not in linked_codes:
            conflicts.append(
                {"type": "B", "code": code, "message": f"{code} in routing_queue but not in linked_projects"}
            )

    if output_json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "routing_queue": routing_queue,
                    "active_routes": active_routes,
                    "conflicts": conflicts,
                },
                ensure_ascii=False,
            )
        )
        return True

    print("Route Status")
    print("============")
    print(f"routing_queue: {routing_queue or '(empty)'}")
    print()
    if active_routes:
        print("active_routes:")
        for route in active_routes:
            if isinstance(route, dict):
                code = route.get("project_code", "?")
                ref = route.get("feature_ref") or "(no feature_ref)"
                print(f"  {code} -> {ref}")
    else:
        print("active_routes: (empty)")
    if conflicts:
        print()
        print("Conflicts:")
        for c in conflicts:
            print(f"  [{c['type']}] {c['message']}")
    return True
```

- [ ] **Step 4: 运行 route-status 测试，确认通过**

```bash
python -m pytest tests/test_route_commands.py -k "route_status" -v
```

预期：所有 `route_status` 相关测试 PASS。

---

## Task 3: 为 `route-select` 写失败测试（含去重与 CLI 级测试）

**Files:**
- Modify: `tests/test_route_commands.py`（追加到文件末尾）

- [ ] **Step 5: 追加 route-select 函数级测试**

```python
# --- route-select tests ---

def test_route_select_inserts_new_entry(temp_dir, capsys):
    """route_select() inserts new active_routes entry when code not present."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F3")

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = saved["active_routes"]
    assert len(routes) == 1
    assert routes[0]["project_code"] == "NO"
    assert routes[0]["feature_ref"] == "NO-F3"


def test_route_select_updates_existing_entry(temp_dir):
    """route_select() updates feature_ref for existing project_code entry."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F1"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F5")

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = saved["active_routes"]
    assert len(routes) == 1
    assert routes[0]["feature_ref"] == "NO-F5"


def test_route_select_deduplicates_existing_duplicates(temp_dir):
    """route_select() merges duplicate project_code entries into a single record (fixes Type A conflict)."""
    data = _base_progress()
    data["active_routes"] = [
        {"project_code": "NO", "feature_ref": "NO-F1"},
        {"project_code": "NO", "feature_ref": "NO-F2"},
    ]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F3")

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = saved["active_routes"]
    # Must be collapsed to a single entry
    no_routes = [r for r in routes if r.get("project_code") == "NO"]
    assert len(no_routes) == 1
    assert no_routes[0]["feature_ref"] == "NO-F3"


def test_route_select_preserves_feature_ref_when_not_provided(temp_dir):
    """route_select() preserves existing feature_ref when --feature-ref not given."""
    data = _base_progress()
    data["active_routes"] = [{"project_code": "NO", "feature_ref": "NO-F2"}]
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref=None)

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    assert saved["active_routes"][0]["feature_ref"] == "NO-F2"


def test_route_select_empty_feature_ref_when_new_and_not_provided(temp_dir):
    """route_select() uses empty string when new entry and no --feature-ref given."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref=None)

    assert result is True
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    assert saved["active_routes"][0]["feature_ref"] == ""


def test_route_select_json_output(temp_dir, capsys):
    """route_select(output_json=True) emits valid JSON with updated active_routes."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        result = progress_manager.route_select("NO", feature_ref="NO-F1", output_json=True)

    assert result is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert any(r["project_code"] == "NO" for r in payload["active_routes"])


# --- CLI-level (main()) tests ---

def test_cli_route_status_json(temp_dir, capsys):
    """CLI: `prog route-status --json` parses correctly and returns exit 0."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    argv = ["progress_manager.py", "--project-root", str(temp_dir), "route-status", "--json"]
    with patch("sys.argv", argv):
        result = progress_manager.main()

    assert result is True or result == 0
    payload = json.loads(capsys.readouterr().out)
    assert "routing_queue" in payload
    assert "conflicts" in payload


def test_cli_route_select_project(temp_dir, capsys):
    """CLI: `prog route-select --project NO --feature-ref NO-F1` parses and writes correctly."""
    data = _base_progress()
    _write_progress(temp_dir, data)

    argv = [
        "progress_manager.py",
        "--project-root", str(temp_dir),
        "route-select",
        "--project", "NO",
        "--feature-ref", "NO-F1",
    ]
    with patch("sys.argv", argv):
        result = progress_manager.main()

    assert result is True or result == 0
    with patch("progress_manager._PROJECT_ROOT_OVERRIDE", temp_dir):
        saved = progress_manager.load_progress_json()
    routes = [r for r in saved["active_routes"] if r.get("project_code") == "NO"]
    assert len(routes) == 1
    assert routes[0]["feature_ref"] == "NO-F1"
```

- [ ] **Step 6: 运行 route-select 测试，确认全部失败**

```bash
python -m pytest tests/test_route_commands.py -k "route_select or cli_route" -v 2>&1 | head -20
```

预期：`AttributeError: module 'progress_manager' has no attribute 'route_select'`

---

## Task 4: 实现 `route_select()` 函数（含去重 + 运行时同步）

**Files:**
- Modify: `hooks/scripts/progress_manager.py`（在 `route_status` 函数之后插入）

- [ ] **Step 7: 实现函数**

在 `route_status` 函数结尾之后插入：

```python
def route_select(
    project_code: str,
    *,
    feature_ref: Optional[str] = None,
    output_json: bool = False,
) -> bool:
    """Upsert active_routes entry for project_code (unique key), merging duplicates."""
    data = load_progress_json()
    if not data:
        message = "No progress tracking found. Use init first."
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    normalized_code = _normalize_project_code(project_code)
    if normalized_code is None:
        message = (
            "Error: Invalid --project value. Use 1-32 chars matching "
            "[A-Z][A-Z0-9_]* (example: NO, APP2, CORE_API)."
        )
        if output_json:
            print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        else:
            print(message)
        return False

    active_routes: List[Any] = data.get("active_routes") or []
    if not isinstance(active_routes, list):
        active_routes = []

    # Collect existing entry for the target code (take first match for feature_ref preservation)
    existing_entry: Optional[Dict[str, Any]] = None
    other_routes: List[Any] = []
    for route in active_routes:
        if not isinstance(route, dict):
            other_routes.append(route)
            continue
        route_code_raw = route.get("project_code")
        route_code = (
            str(route_code_raw).strip().upper()
            if isinstance(route_code_raw, str) and route_code_raw.strip()
            else None
        )
        if route_code == normalized_code:
            if existing_entry is None:
                existing_entry = dict(route)
            # Skip duplicates — deduplication happens by writing only one entry below
        else:
            other_routes.append(route)

    # Determine final feature_ref
    if feature_ref is not None:
        final_ref = feature_ref
    elif existing_entry is not None:
        final_ref = existing_entry.get("feature_ref", "")
        if not isinstance(final_ref, str):
            final_ref = ""
    else:
        final_ref = ""

    upserted_entry: Dict[str, Any] = {"project_code": normalized_code, "feature_ref": final_ref}
    if existing_entry is not None:
        # Preserve extra fields (e.g. worktree_path, custom flags) from first match
        merged = dict(existing_entry)
        merged["project_code"] = normalized_code
        merged["feature_ref"] = final_ref
        upserted_entry = merged

    new_routes = other_routes + [upserted_entry]
    data["active_routes"] = new_routes

    _update_runtime_context(data, source="route_select")
    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

    action = "updated" if existing_entry is not None else "inserted"
    if output_json:
        print(
            json.dumps(
                {"status": "ok", "project_code": normalized_code, "active_routes": new_routes},
                ensure_ascii=False,
            )
        )
    else:
        ref_display = final_ref or "(empty)"
        print(f"route-select: {action} {normalized_code} -> {ref_display}")
    return True
```

- [ ] **Step 8: 运行全部 route 测试，确认通过**

```bash
python -m pytest tests/test_route_commands.py -v
```

预期：所有测试 PASS。

---

## Task 5: 接入 CLI（argparse + MUTATING_COMMANDS + dispatch）

**Files:**
- Modify: `hooks/scripts/progress_manager.py`（三处修改：MUTATING_COMMANDS、argparse、dispatch）

- [ ] **Step 9: 将 `route-select` 加入 MUTATING_COMMANDS**

找到第 157-185 行的 `MUTATING_COMMANDS` 集合，在 `"link-project",` 之后插入：

```python
    "route-select",
```

- [ ] **Step 10: 添加 argparse subparsers**

在 `link_project_parser` 定义块（约第 7195-7200 行 `--json` 参数）之后、`runtime_sync_parser` 之前插入：

```python
    route_status_parser = subparsers.add_parser(
        "route-status",
        help="Display routing_queue, active_routes, and conflict summary.",
    )
    route_status_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
    route_select_parser = subparsers.add_parser(
        "route-select",
        help="Upsert active_routes entry for a project code (unique key).",
    )
    route_select_parser.add_argument(
        "--project",
        required=True,
        help="Project code token to select (e.g. NO, APP2)",
    )
    route_select_parser.add_argument(
        "--feature-ref",
        dest="feature_ref",
        help="Feature reference within the project (e.g. NO-F3). Omit to preserve existing.",
    )
    route_select_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON output",
    )
```

- [ ] **Step 11: 在 `_dispatch_command()` 中添加分发**

在 `if args.command == "link-project":` 分支之后插入：

```python
        if args.command == "route-status":
            return route_status(output_json=args.output_json)
        if args.command == "route-select":
            return route_select(
                args.project,
                feature_ref=args.feature_ref,
                output_json=args.output_json,
            )
```

- [ ] **Step 12: 手工冒烟验证 CLI**

```bash
./prog route-status
./prog route-status --json
./prog route-select --project NO --feature-ref NO-F1
./prog route-select --project NO --json
```

预期：无报错，输出格式符合预期。

---

## Task 6: 回归验证

- [ ] **Step 13: 运行完整测试套件**

```bash
python -m pytest tests/test_route_commands.py tests/test_status_linked_summary.py tests/test_linked_projects_schema.py tests/test_sync_linked_command.py -v
```

预期：全部 PASS。

- [ ] **Step 14: 验证 docs 检查通过**

```bash
python3 hooks/scripts/generate_prog_docs.py --check
```

预期：`Generated docs are up to date.`

- [ ] **Step 15: 提交**

```bash
git add tests/test_route_commands.py hooks/scripts/progress_manager.py
git commit -m "feat(route): add route-status and route-select commands

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
