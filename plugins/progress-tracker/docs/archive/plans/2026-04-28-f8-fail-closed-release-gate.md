# F8: Fail-Closed Release Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ship_check.py` a runnable CLI that executes real checks (pytest + docs drift + plugin.json schema / codex-plugin-sync), updates `progress.json`, and exits non-zero on failure — becoming a true fail-closed release gate.

**Architecture:** `ship_check.py` uses `Path.cwd()` as default project root (consistent with `cmd_ship_check` in progress_manager.py), accepts `--project-root` for explicit override. It runs pytest as subprocess to collect real signals (plugin-scoped tests only), validates sync compatibility via `codex-plugin-sync --dry-run` when available, falling back to plugin.json schema validation when not. Calls the existing `run_ship_check()` pipeline. Writes gate result back to `progress.json` best-effort. `progress.md` is a derived artifact — any subsequent `prog` command regenerates it automatically; ship_check.py is not responsible for md sync. Existing library API and 7 passing tests are untouched.

**Tech Stack:** Python 3.9+, `subprocess`, `re`, `argparse`, `pathlib`, `json` (stdlib only)

**Exit code convention (matches `cmd_ship_check` in progress_manager.py):**

| Code | Meaning |
|------|---------|
| 0 | pass |
| 8 | fail (one or more checks failed) |

Note: The standalone CLI returns only 0 or 8. Missing progress.json is not an error — the gate result is reported regardless of whether write-back succeeds. (Code 1 and 9 are used by `cmd_ship_check` in progress_manager.py but not by the standalone CLI.)

---

## File Map

| File | Change |
|------|--------|
| `hooks/scripts/ship_check.py` | Add imports; add `_check_sync_compatibility()`; wire it into `run_ship_check()`; add `_collect_real_signals()`, `_update_progress_json()`, `main()`; add `__main__` block |
| `tests/test_ship_check.py` | Add 7 tests: sync check valid/missing-keys (+2), real signals with/without tests/ + e2e contract (+3), CLI exit-0/exit-8 (+2) |

---

## Task 1: Add `_check_sync_compatibility()` — RED → GREEN → COMMIT

**Design decision (Q2-C):** Primary strategy is `codex-plugin-sync --dry-run`; fallback to plugin.json schema validation when tool is absent. No plugin.json → skip gracefully.

**Files:**
- Modify: `tests/test_ship_check.py` (append 2 tests)
- Modify: `hooks/scripts/ship_check.py` (add imports + function)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ship_check.py`:

```python
# ── Task 1: sync compatibility ────────────────────────────────────────────────

def test_check_sync_compat_passes_with_valid_plugin_json(tmp_path):
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"name":"x","version":"1.0","description":"d","author":{"name":"a"},'
        '"license":"MIT","repository":"https://g","homepage":"https://g"}'
    )
    from ship_check import _check_sync_compatibility
    assert _check_sync_compatibility(tmp_path) == []


def test_check_sync_compat_fails_with_missing_keys(tmp_path):
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text('{"name":"x"}')
    from ship_check import _check_sync_compatibility
    failures = _check_sync_compatibility(tmp_path)
    assert len(failures) == 1
    assert failures[0].check_id == "sync_compat"
    assert "missing" in failures[0].detail
```

- [ ] **Step 2: Run tests — expect FAIL (ImportError / AttributeError)**

```bash
cd <worktree>/plugins/progress-tracker
pytest tests/test_ship_check.py::test_check_sync_compat_passes_with_valid_plugin_json \
       tests/test_ship_check.py::test_check_sync_compat_fails_with_missing_keys -v
```

Expected: `FAILED` with `ImportError: cannot import name '_check_sync_compatibility'`

- [ ] **Step 3: Add imports + `_check_sync_compatibility` to `ship_check.py`**

At the top of `ship_check.py`, replace the existing imports block with:

```python
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
```

After the existing `_check_docs_sync()` function and before `run_ship_check()`, insert:

```python
_PLUGIN_JSON_REQUIRED_KEYS = {
    "name", "version", "description", "author",
    "license", "repository", "homepage",
}


def _check_sync_compatibility(project_root: Path) -> List[ShipFailure]:
    """Sync compatibility gate (Q2-C strategy):

    Primary: run codex-plugin-sync --dry-run when available (richer evidence).
    Fallback: validate .claude-plugin/plugin.json schema (required keys) when tool absent.
    No plugin.json present → skip gracefully (non-plugin project).
    """
    plugin_json_path = project_root / ".claude-plugin" / "plugin.json"
    if not plugin_json_path.exists():
        return []  # Non-plugin project — skip check gracefully

    # Primary: try codex-plugin-sync --dry-run first
    if shutil.which("codex-plugin-sync"):
        try:
            r = subprocess.run(
                ["codex-plugin-sync", "--dry-run"],
                capture_output=True, text=True,
                cwd=str(project_root), timeout=30,
            )
            if r.returncode != 0:
                return [ShipFailure(
                    check_id="sync_compat",
                    detail=f"codex-plugin-sync --dry-run failed: {r.stderr.strip()[:200]}",
                )]
            return []  # Tool ran and passed
        except Exception:
            pass  # Tool present but failed to exec — fall through to schema check

    # Fallback: static schema validation when codex-plugin-sync is absent
    try:
        data = json.loads(plugin_json_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return [ShipFailure(check_id="sync_compat", detail=f"plugin.json parse error: {exc}")]

    missing = _PLUGIN_JSON_REQUIRED_KEYS - set(data.keys())
    if missing:
        return [ShipFailure(
            check_id="sync_compat",
            detail=f"plugin.json missing required keys: {', '.join(sorted(missing))}",
        )]

    return []
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_ship_check.py::test_check_sync_compat_passes_with_valid_plugin_json \
       tests/test_ship_check.py::test_check_sync_compat_fails_with_missing_keys -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add hooks/scripts/ship_check.py tests/test_ship_check.py
git commit -m "feat(f8): add _check_sync_compatibility with Q2-C fallback strategy"
```

---

## Task 2: Wire sync check into `run_ship_check()` pipeline — GREEN stays GREEN

**Files:**
- Modify: `hooks/scripts/ship_check.py` (1-line addition to `run_ship_check()`)

- [ ] **Step 1: Add sync check to `run_ship_check()` pipeline**

In `run_ship_check()`, change the body to:

```python
def run_ship_check(
    *,
    feature_id: int,
    project_root: Path,
    inputs: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> ShipCheckResult:
    failures: List[ShipFailure] = []
    failures += _check_tests(inputs)
    failures += _check_coverage(inputs, thresholds)
    failures += _check_regression(inputs)
    failures += _check_docs_sync(inputs)
    failures += _check_sync_compatibility(project_root)

    return ShipCheckResult(
        status="fail" if failures else "pass",
        failures=failures,
        last_run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
```

- [ ] **Step 2: Run ALL existing + new tests — expect 9 passed**

```bash
pytest tests/test_ship_check.py -v
```

Expected: `9 passed` (7 existing + 2 from Task 1)

Backward-compat note: existing tests pass `tmp_path` as `project_root`. `tmp_path` has no `.claude-plugin/plugin.json` → `_check_sync_compatibility` returns `[]` → no regressions.

- [ ] **Step 3: Commit**

```bash
git add hooks/scripts/ship_check.py
git commit -m "feat(f8): wire sync_compat check into run_ship_check pipeline"
```

---

## Task 3: Add `_collect_real_signals()` and `_update_progress_json()` — TDD

**Design decisions:**
- pytest scope: `<project_root>/tests/` by default (plugin-scoped, not full monorepo). Caller may override via `test_path` argument.
- Missing tests/ is a gate failure: `_collect_real_signals()` sets `tests_dir_exists=False`; new `_check_test_scope()` turns this into a `ShipFailure`. Existing tests don't pass `tests_dir_exists`, so `inputs.get("tests_dir_exists", True)` defaults to True — no regressions.
- pytest returncode is authoritative: if returncode ≠ 0 and no "N failed" line was parsed (collection errors, import errors, interrupts), set `failed=1` to preserve fail-closed semantics.
- progress.md: `ship_check.py` only writes `progress.json`. `progress.md` is a derived artifact regenerated by any subsequent `prog` command — no action needed here. (`reconcile-state` does audit-log drift correction, not md generation; importing from `progress_manager.py` is a circular import.)

**Files:**
- Modify: `tests/test_ship_check.py` (append 2 tests)
- Modify: `hooks/scripts/ship_check.py` (add 2 helper functions)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ship_check.py`:

```python
# ── Task 3: real signal collection ───────────────────────────────────────────

def test_collect_real_signals_runs_pytest_and_returns_counts(tmp_path):
    """_collect_real_signals runs pytest in tests/ and parses pass/fail counts."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_trivial.py").write_text("def test_ok(): assert 1 + 1 == 2\n")

    from ship_check import _collect_real_signals
    signals = _collect_real_signals(tmp_path)

    assert signals["tests_dir_exists"] is True
    assert signals["test_results"]["passed"] >= 1
    assert signals["test_results"]["failed"] == 0


def test_collect_real_signals_no_tests_dir_signals_missing_scope(tmp_path):
    """_collect_real_signals sets tests_dir_exists=False when tests/ is absent (fail-closed)."""
    from ship_check import _collect_real_signals
    signals = _collect_real_signals(tmp_path)
    assert signals["tests_dir_exists"] is False


def test_run_ship_check_fails_with_no_test_scope_when_tests_dir_missing(tmp_path):
    """End-to-end: run_ship_check returns fail with check_id='no_test_scope' when tests/ absent."""
    from ship_check import run_ship_check
    result = run_ship_check(
        feature_id=1,
        project_root=tmp_path,
        inputs={
            "test_coverage": 1.0,
            "tests_dir_exists": False,
            "test_results": {"passed": 0, "failed": 0, "skipped": 0},
            "docs_sync": {"progress_md_matches_json": True, "architecture_refs_valid": True},
            "regression_results": {"passed": 0, "failed": 0},
        },
        thresholds={"coverage_min": 0.8},
    )
    assert result.status == "fail"
    assert any(f.check_id == "no_test_scope" for f in result.failures)
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_ship_check.py::test_collect_real_signals_runs_pytest_and_returns_counts \
       tests/test_ship_check.py::test_collect_real_signals_no_tests_dir_signals_missing_scope -v
```

Expected: `FAILED` with `ImportError: cannot import name '_collect_real_signals'`

- [ ] **Step 3: Implement `_collect_real_signals()`, `_check_test_scope()`, and `_update_progress_json()` in `ship_check.py`**

After `_check_sync_compatibility()` and before `run_ship_check()`, insert:

```python
def _collect_real_signals(
    project_root: Path,
    test_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run real checks and collect signals for run_ship_check.

    pytest scope: project_root/tests/ by default (plugin-scoped, not full monorepo).
    Pass test_path to override scope.

    Fail-closed rules:
    - Missing tests/ dir → tests_dir_exists=False (triggers _check_test_scope failure).
    - pytest returncode != 0 with no parsed failures → set failed=1 (collection errors,
      import errors, or interrupts are treated as implicit test failures).

    Docs drift: compares progress.md mtime vs progress.json mtime (60s tolerance).
    """
    passed, failed = 0, 0
    tests_dir = test_path or (project_root / "tests")
    tests_dir_exists = tests_dir.is_dir()

    if tests_dir_exists:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests_dir), "-q", "--tb=no"],
            capture_output=True, text=True, timeout=300,
            cwd=str(project_root),
        )
        for line in (result.stdout + result.stderr).splitlines():
            m_pass = re.search(r"(\d+) passed", line)
            m_fail = re.search(r"(\d+) failed", line)
            if m_pass:
                passed = int(m_pass.group(1))
            if m_fail:
                failed = int(m_fail.group(1))
        # Fail-closed: non-zero returncode with no parsed failures = collection/interrupt error
        if result.returncode != 0 and failed == 0:
            failed = 1

    # Docs drift: progress.md should be at least as recent as progress.json
    progress_json_path = project_root / "docs" / "progress-tracker" / "state" / "progress.json"
    progress_md_path = project_root / "docs" / "progress-tracker" / "state" / "progress.md"
    md_in_sync = True
    if progress_json_path.exists() and progress_md_path.exists():
        tolerance = 60  # seconds
        md_in_sync = (
            progress_md_path.stat().st_mtime >= progress_json_path.stat().st_mtime - tolerance
        )

    return {
        "test_coverage": 1.0,  # Coverage not collected in CLI mode
        "tests_dir_exists": tests_dir_exists,
        "test_results": {"passed": passed, "failed": failed, "skipped": 0},
        "docs_sync": {"progress_md_matches_json": md_in_sync, "architecture_refs_valid": True},
        "regression_results": {"passed": passed, "failed": 0},
    }


def _check_test_scope(inputs: Dict[str, Any]) -> List[ShipFailure]:
    """Fail-closed: missing tests/ directory is a gate failure.

    Existing callers that don't pass tests_dir_exists default to True (no regression).
    """
    if not inputs.get("tests_dir_exists", True):
        return [ShipFailure(
            check_id="no_test_scope",
            detail="tests/ directory not found — gate cannot verify test coverage",
        )]
    return []


def _update_progress_json(
    project_root: Path,
    feature_id: int,
    result: "ShipCheckResult",
) -> None:
    """Best-effort: write ship_check result back to quality_gates in progress.json.

    progress.md is intentionally NOT updated here — it is a derived artifact
    regenerated automatically by any subsequent prog command.
    Never blocks the gate on persistence failure.
    """
    progress_json_path = project_root / "docs" / "progress-tracker" / "state" / "progress.json"
    if not progress_json_path.exists():
        return
    try:
        data = json.loads(progress_json_path.read_text())
        for feat in data.get("features", []):
            if feat.get("id") == feature_id:
                feat.setdefault("quality_gates", {})["ship_check"] = result.to_quality_gate_payload()
                break
        progress_json_path.write_text(json.dumps(data, indent=2))
    except Exception:
        pass  # Never block the gate on persistence failure
```

- [ ] **Step 4: Run new tests — expect PASS**

```bash
pytest tests/test_ship_check.py::test_collect_real_signals_runs_pytest_and_returns_counts \
       tests/test_ship_check.py::test_collect_real_signals_no_tests_dir_signals_missing_scope -v
```

Expected: `2 passed`

- [ ] **Step 4b: Wire `_check_test_scope` into `run_ship_check()`**

Update `run_ship_check()` to add the scope check:

```python
def run_ship_check(
    *,
    feature_id: int,
    project_root: Path,
    inputs: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> ShipCheckResult:
    failures: List[ShipFailure] = []
    failures += _check_tests(inputs)
    failures += _check_coverage(inputs, thresholds)
    failures += _check_regression(inputs)
    failures += _check_docs_sync(inputs)
    failures += _check_sync_compatibility(project_root)
    failures += _check_test_scope(inputs)  # fail-closed: missing tests/ → fail

    return ShipCheckResult(
        status="fail" if failures else "pass",
        failures=failures,
        last_run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
```

- [ ] **Step 4c: Run ALL tests — expect 12 passed**

```bash
pytest tests/test_ship_check.py -v
```

Expected: `12 passed` (7 original + 2 sync from Task 1 + 3 signals/contract from Task 3)

Backward-compat note: existing tests don't pass `tests_dir_exists` in `inputs`, so `_check_test_scope` defaults to `True` → no regressions.

- [ ] **Step 5: Commit**

```bash
git add hooks/scripts/ship_check.py tests/test_ship_check.py
git commit -m "feat(f8): add _collect_real_signals, _check_test_scope, _update_progress_json"
```

---

## Task 4: Add `__main__` CLI entry point — TDD

**Exit code convention:** 0=pass, 8=fail (matches `cmd_ship_check` in progress_manager.py).

**Files:**
- Modify: `tests/test_ship_check.py` (append 2 CLI tests)
- Modify: `hooks/scripts/ship_check.py` (add `main()` + `__main__` block)

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_ship_check.py`:

```python
# ── Task 4: CLI entry point ───────────────────────────────────────────────────

def test_ship_check_cli_exits_0_on_clean_project(tmp_path):
    """python3 ship_check.py exits 0 when all checks pass."""
    import subprocess, sys
    from pathlib import Path

    # Minimal project: plugin.json + trivial test
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"name":"x","version":"1.0","description":"d","author":{"name":"a"},'
        '"license":"MIT","repository":"https://g","homepage":"https://g"}'
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_trivial.py").write_text("def test_ok(): assert True\n")

    ship_check_script = Path(__file__).parent.parent / "hooks" / "scripts" / "ship_check.py"
    result = subprocess.run(
        [sys.executable, str(ship_check_script), "--project-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pass" in result.stdout.lower()


def test_ship_check_cli_exits_8_on_missing_plugin_keys(tmp_path):
    """python3 ship_check.py exits 8 when plugin.json is missing required keys."""
    import subprocess, sys
    from pathlib import Path

    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text('{"name":"broken"}')

    ship_check_script = Path(__file__).parent.parent / "hooks" / "scripts" / "ship_check.py"
    result = subprocess.run(
        [sys.executable, str(ship_check_script), "--project-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 8, f"Expected 8, got {result.returncode}"
    assert "FAIL" in result.stdout or "FAIL" in result.stderr
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_ship_check.py::test_ship_check_cli_exits_0_on_clean_project \
       tests/test_ship_check.py::test_ship_check_cli_exits_8_on_missing_plugin_keys -v
```

Expected: `FAILED` — script exits 0 with no output (no `__main__` block yet)

- [ ] **Step 3: Add `main()` and `__main__` block to `ship_check.py`**

Append at the **end** of `ship_check.py`, after `run_ship_check()`:

```python
def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point: run the ship gate against the current project.

    Exit codes:
        0 = pass
        8 = fail (matches cmd_ship_check convention in progress_manager.py)

    Default project root: Path.cwd() — consistent with cmd_ship_check.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="ship_check: unified pre-archive release gate"
    )
    parser.add_argument(
        "--feature-id", type=int, default=None,
        help="Feature ID to update in progress.json (default: auto-discover from current_feature_id)",
    )
    parser.add_argument(
        "--project-root", type=Path, default=None,
        help="Project root directory (default: cwd, consistent with prog ship-check)",
    )
    parser.add_argument(
        "--test-path", type=Path, default=None,
        help="Override pytest target path (default: <project-root>/tests/)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output result as JSON",
    )
    args = parser.parse_args(argv)

    # Default project root: cwd (matches cmd_ship_check in progress_manager.py)
    project_root: Path = args.project_root or Path.cwd()

    # Auto-discover feature_id before run_ship_check so all calls use the same value
    feature_id = args.feature_id
    if feature_id is None:
        progress_json_path = (
            project_root / "docs" / "progress-tracker" / "state" / "progress.json"
        )
        if progress_json_path.exists():
            try:
                data = json.loads(progress_json_path.read_text())
                fid = data.get("current_feature_id")
                if fid is not None:
                    feature_id = int(fid)
            except Exception:
                pass

    inputs = _collect_real_signals(project_root, test_path=args.test_path)
    result = run_ship_check(
        feature_id=feature_id or 0,
        project_root=project_root,
        inputs=inputs,
        thresholds={"coverage_min": 0.8},
    )

    if feature_id is not None:
        _update_progress_json(project_root, feature_id, result)

    if args.json_output:
        print(json.dumps(result.to_quality_gate_payload(), indent=2))
    else:
        if result.status == "pass":
            print("[SHIP-CHECK] pass")
        else:
            for f in result.failures:
                print(f"  FAIL [{f.check_id}] {f.detail}")
            print(f"[SHIP-CHECK] FAIL ({len(result.failures)} issue(s))")

    # Exit code: 0=pass, 8=fail (matches cmd_ship_check convention)
    return 0 if result.status == "pass" else 8


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run CLI tests — expect PASS**

```bash
pytest tests/test_ship_check.py::test_ship_check_cli_exits_0_on_clean_project \
       tests/test_ship_check.py::test_ship_check_cli_exits_8_on_missing_plugin_keys -v
```

Expected: `2 passed`

- [ ] **Step 5: Run ALL ship_check tests — expect 14 passed**

```bash
pytest tests/test_ship_check.py -v
```

Expected: `14 passed` (7 original + 2 sync + 3 signal/contract + 2 CLI)

- [ ] **Step 6: Commit**

```bash
git add hooks/scripts/ship_check.py tests/test_ship_check.py
git commit -m "feat(f8): add __main__ CLI with fail-closed exit codes (0=pass, 8=fail)"
```

---

## Task 5: Acceptance Verification

- [ ] **Step 1: Run unified gate as standalone CLI**

```bash
python3 hooks/scripts/ship_check.py
```

Expected output:
```
[SHIP-CHECK] pass
```
Exit code: 0

- [ ] **Step 2: Run gate tests**

```bash
pytest tests/test_ship_check.py -q
```

Expected: `14 passed`

- [ ] **Step 3: Verify sync compatibility covers plugin.json schema**

```bash
python3 hooks/scripts/ship_check.py --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])"
```

Expected: `pass`

- [ ] **Step 4: Run full regression suite**

```bash
pytest tests/ -q --tb=short
```

Expected: all passing (no regressions)

- [ ] **Step 5: Final commit**

```bash
git add hooks/scripts/ship_check.py tests/test_ship_check.py
git commit -m "feat(f8): implement fail-closed release gate with sync compatibility evidence"
```
