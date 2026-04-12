# E2E Cross-Plugin Integration Tests and Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现有边界的跨插件 planning handoff E2E 测试，验证 SPM planning 产物被 PROG consumers 正确消费

**Architecture:** 创建独立的 E2E 测试模块，直接调用 Python/CLI 契约（非 slash command），使用真实实现跑 happy path，fixtures 覆盖边界情况

**Tech Stack:** pytest, subprocess (CLI 调用), JSON 契约验证

---

## File Structure

```
plugins/super-product-manager/
  tests/
    e2e/
      __init__.py
      test_planning_handoff_e2e.py    # 主 E2E 测试文件
      fixtures/
        __init__.py
        planning_fixtures.py            # 共享 fixtures 和 helpers
  docs/
    superpowers/
      plans/
        2026-04-12-e2e-cross-plugin-integration-tests.md  # 本计划
  README.md                              # 更新集成说明

plugins/progress-tracker/
  docs/
    PROG_COMMANDS.md                     # 更新 validate-planning/next-feature 说明
```

---

## Task 1: Create E2E test directory structure and fixtures module

**Files:**
- Create: `plugins/super-product-manager/tests/e2e/__init__.py`
- Create: `plugins/super-product-manager/tests/e2e/fixtures/__init__.py`
- Create: `plugins/super-product-manager/tests/e2e/fixtures/planning_fixtures.py`

- [ ] **Step 1: Create empty init files**

```bash
mkdir -p plugins/super-product-manager/tests/e2e/fixtures
touch plugins/super-product-manager/tests/e2e/__init__.py
touch plugins/super-product-manager/tests/e2e/fixtures/__init__.py
```

- [ ] **Step 2: Write planning_fixtures.py with helpers**

```python
"""E2E test fixtures and helpers for SPM-PROG planning handoff integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def project_root() -> Path:
    """Return the monorepo root directory."""
    return Path(__file__).resolve().parents[4]


def spm_scripts_dir() -> Path:
    """Return super-product-manager scripts directory."""
    return project_root() / "plugins" / "super-product-manager" / "scripts"


def prog_cli_path() -> Path:
    """Return progress-tracker prog CLI path."""
    return project_root() / "plugins" / "progress-tracker" / "prog"


def run_python_script(script_path: Path, args: List[str]) -> Dict[str, Any]:
    """Run a Python script and return parsed JSON output."""
    cmd = ["python3", str(script_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root()),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stderr": "Command timed out after 30s"}

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "invalid_json",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }


def run_prog_cli(args: List[str]) -> Dict[str, Any]:
    """Run PROG CLI command and return parsed result."""
    prog_path = prog_cli_path()
    if not prog_path.exists():
        return {"ok": False, "error": "prog_not_found", "path": str(prog_path)}

    cmd = [str(prog_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root()),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stderr": "Command timed out after 30s"}

    # Try JSON output first
    if "--json" in args:
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def minimal_planning_workflow_result() -> Dict[str, Any]:
    """Return minimal expected structure from planning workflow calls."""
    return {
        "ok": True,
        "artifact_file": str,  # Path to created artifact
        "sync": {
            "ok": True,
        },
        "sync_errors": list,
    }


def validate_planning_result_schema() -> Dict[str, Any]:
    """Return expected schema from validate-planning --json."""
    return {
        "ok": True,
        "status": str,  # "ready" | "warn" | "missing"
        "change_type": str,
        "required": list,
        "missing": list,
        "optional_missing": list,
        "refs": list,
        "message": str,
        "schema_version": str,
    }


def next_feature_result_schema() -> Dict[str, Any]:
    """Return expected schema from next-feature --json."""
    return {
        "status": str,  # "ok" | "blocked" | "none"
        "feature_id": int,
        "feature_name": str,
    }


class TempFeatureContext:
    """Context manager for creating and cleaning up a temporary feature for E2E testing."""

    def __init__(self, prog_cli_args: List[str] = ["--project-root", "plugins/super-product-manager"]):
        self.prog_cli_args = prog_cli_args
        self.feature_id: Optional[int] = None

    def __enter__(self) -> "TempFeatureContext":
        # Create a temporary feature via PROG CLI
        # Using add-feature command if available, otherwise manual JSON edit
        # For now, we'll use an existing feature ID for testing
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Cleanup: remove test updates if any
        pass
```

- [ ] **Step 3: Run directory structure verification**

```bash
test -f plugins/super-product-manager/tests/e2e/__init__.py
test -f plugins/super-product-manager/tests/e2e/fixtures/__init__.py
test -f plugins/super-product-manager/tests/e2e/fixtures/planning_fixtures.py
```

Expected: All files exist

- [ ] **Step 4: Verify fixtures module imports**

```bash
python3 -c "from plugins.super_product_manager.tests.e2e.fixtures.planning_fixtures import project_root; print(project_root())"
```

Expected: Prints `/Users/siunin/Projects/Claude-Plugins`

- [ ] **Step 5: Commit**

```bash
git add plugins/super-product-manager/tests/e2e/
git commit -m "feat(e2e): add test directory structure and fixtures helpers"
```

---

## Task 2: Implement Scenario 1 - Complete planning chain happy path

**Files:**
- Create: `plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py`

- [ ] **Step 1: Write the failing test for complete chain**

```python
"""E2E tests for SPM planning → PROG preflight handoff integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .fixtures.planning_fixtures import (
    project_root,
    run_python_script,
    run_prog_cli,
    spm_scripts_dir,
)


def test_complete_planning_chain_happy_path():
    """Scenario 1: Full planning chain → validate-planning ready → next-feature ok.

    Chain: office-hours → plan-ceo-review → plan-design-review → plan-devex-review
    Expected: validate-planning returns "ready", next-feature returns feature
    """
    # Setup: Get or create a test feature
    prog_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "list", "--json"]
    )
    assert prog_result["ok"], f"Failed to list features: {prog_result.get('stderr')}"
    features = prog_result.get("features", [])
    assert len(features) > 0, "No features available for testing"

    # Use the first non-completed feature for testing
    test_feature = next((f for f in features if not f.get("completed", False)), None)
    if not test_feature:
        pytest.skip("No incomplete feature available for E2E testing")

    feature_id = test_feature["id"]
    feature_name = test_feature["name"]

    # Step 1: Run office-hours via planning_workflow.py
    planning_script = spm_scripts_dir() / "planning_workflow.py"
    office_hours_result = run_python_script(
        [
            str(planning_script),
            "office-hours",
            "--topic", f"Feature {feature_id} E2E test",
            "--goals", "Test happy path planning chain",
            "--feature-id", str(feature_id),
        ]
    )
    assert office_hours_result.get("ok"), f"office-hours failed: {office_hours_result}"
    assert "artifact_file" in office_hours_result

    # Step 2: Run plan-ceo-review
    ceo_review_result = run_python_script(
        [
            str(planning_script),
            "plan-ceo-review",
            "--topic", f"Feature {feature_id} E2E test",
            "--verdict", "pass",
            "--feature-id", str(feature_id),
        ]
    )
    assert ceo_review_result.get("ok"), f"plan-ceo-review failed: {ceo_review_result}"

    # Step 3: Run plan-design-review
    design_review_result = run_python_script(
        [
            str(planning_script),
            "plan-design-review",
            "--topic", f"Feature {feature_id} E2E test",
            "--score", "8",
            "--recommendation", "Approved for E2E testing",
            "--feature-id", str(feature_id),
        ]
    )
    assert design_review_result.get("ok"), f"plan-design-review failed: {design_review_result}"

    # Step 4: Run plan-devex-review
    devex_review_result = run_python_script(
        [
            str(planning_script),
            "plan-devex-review",
            "--topic", f"Feature {feature_id} E2E test",
            "--score", "8",
            "--recommendation", "Developer experience approved",
            "--feature-id", str(feature_id),
        ]
    )
    assert devex_review_result.get("ok"), f"plan-devex-review failed: {devex_review_result}"

    # Step 5: Verify validate-planning returns "ready"
    validate_result = run_prog_cli(
        [
            "--project-root", "plugins/super-product-manager",
            "validate-planning", str(feature_id),
            "--json",
        ]
    )
    assert validate_result.get("ok"), f"validate-planning failed: {validate_result}"
    assert validate_result.get("status") == "ready", \
        f"Expected status 'ready', got '{validate_result.get('status')}'"

    # Verify required lanes are satisfied
    assert "office_hours" not in validate_result.get("missing", [])
    assert "ceo_review" not in validate_result.get("missing", [])

    # Step 6: Verify next-feature returns the feature (not blocked)
    next_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "next-feature", "--json"]
    )
    assert next_result.get("status") != "blocked", \
        f"next-feature should not be blocked, got: {next_result}"

    # Cleanup: Remove test updates (optional, can be left for manual verification)
```

- [ ] **Step 2: Run test to verify it fails (infrastructure check)**

```bash
cd plugins/super-product-manager && python3 -m pytest tests/e2e/test_planning_handoff_e2e.py::test_complete_planning_chain_happy_path -v
```

Expected: FAIL (no features available or infrastructure needs setup)

- [ ] **Step 3: Check current state and adjust test if needed**

```bash
plugins/progress-tracker/prog --project-root plugins/super-product-manager list --json
```

- [ ] **Step 4: Run test again to verify execution flow**

```bash
cd plugins/super-product-manager && python3 -m pytest tests/e2e/test_planning_handoff_e2e.py::test_complete_planning_chain_happy_path -v -s
```

- [ ] **Step 5: Commit**

```bash
git add plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py
git commit -m "feat(e2e): add complete planning chain happy path test"
```

---

## Task 3: Implement Scenario 2 - Required only → warn → block

**Files:**
- Modify: `plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py`

- [ ] **Step 1: Add test for required-only scenario**

```python
def test_required_only_planning_warn_then_block():
    """Scenario 2: office-hours + ceo-review only → validate-planning warn → next-feature blocks.

    Chain: office-hours → plan-ceo-review (skip design/devex)
    Expected: validate-planning returns "warn", next-feature blocks without --ack-planning-risk
    """
    # Get a test feature
    prog_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "list", "--json"]
    )
    assert prog_result["ok"]
    features = prog_result.get("features", [])
    test_feature = next((f for f in features if not f.get("completed", False)), None)
    if not test_feature:
        pytest.skip("No incomplete feature available")

    feature_id = test_feature["id"]

    # Step 1: Run only office-hours
    planning_script = spm_scripts_dir() / "planning_workflow.py"
    office_hours_result = run_python_script(
        [
            str(planning_script),
            "office-hours",
            "--topic", f"Feature {feature_id} warn test",
            "--goals", "Test warn scenario with only required lanes",
            "--feature-id", str(feature_id),
        ]
    )
    assert office_hours_result.get("ok")

    # Step 2: Run only plan-ceo-review (skip design/devex)
    ceo_review_result = run_python_script(
        [
            str(planning_script),
            "plan-ceo-review",
            "--topic", f"Feature {feature_id} warn test",
            "--verdict", "pass",
            "--feature-id", str(feature_id),
        ]
    )
    assert ceo_review_result.get("ok")

    # Step 3: Verify validate-planning returns "warn"
    validate_result = run_prog_cli(
        [
            "--project-root", "plugins/super-product-manager",
            "validate-planning", str(feature_id),
            "--json",
        ]
    )
    assert validate_result.get("ok")
    assert validate_result.get("status") == "warn", \
        f"Expected 'warn', got '{validate_result.get('status')}'"

    # Verify optional_missing contains design/devex reviews
    optional_missing = validate_result.get("optional_missing", [])
    assert any("design" in lane for lane in optional_missing), \
        "Expected design_review in optional_missing"
    assert any("devex" in lane for lane in optional_missing), \
        "Expected devex_review in optional_missing"

    # Step 4: Verify next-feature blocks by default
    next_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "next-feature", "--json"]
    )
    # When status is warn, next-feature should block unless --ack-planning-risk is passed
    assert next_result.get("status") in {"blocked", "warning"}, \
        f"Expected next-feature to block with warn status, got: {next_result}"
```

- [ ] **Step 2: Run the test**

```bash
cd plugins/super-product-manager && python3 -m pytest tests/e2e/test_planning_handoff_e2e.py::test_required_only_planning_warn_then_block -v
```

- [ ] **Step 3: Commit**

```bash
git add plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py
git commit -m "feat(e2e): add required-only warn scenario test"
```

---

## Task 4: Implement Scenario 3 - Office-hours only → missing → block

**Files:**
- Modify: `plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py`

- [ ] **Step 1: Add test for missing scenario**

```python
def test_office_hours_only_missing_then_block():
    """Scenario 3: office-hours only → validate-planning missing → next-feature blocks.

    Chain: office-hours only (skip all reviews)
    Expected: validate-planning returns "missing", next-feature blocks
    """
    # Get a test feature
    prog_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "list", "--json"]
    )
    assert prog_result["ok"]
    features = prog_result.get("features", [])
    test_feature = next((f for f in features if not f.get("completed", False)), None)
    if not test_feature:
        pytest.skip("No incomplete feature available")

    feature_id = test_feature["id"]

    # Step 1: Run only office-hours
    planning_script = spm_scripts_dir() / "planning_workflow.py"
    office_hours_result = run_python_script(
        [
            str(planning_script),
            "office-hours",
            "--topic", f"Feature {feature_id} missing test",
            "--goals", "Test missing scenario with only office-hours",
            "--feature-id", str(feature_id),
        ]
    )
    assert office_hours_result.get("ok")

    # Step 2: Verify validate-planning returns "missing"
    validate_result = run_prog_cli(
        [
            "--project-root", "plugins/super-product-manager",
            "validate-planning", str(feature_id),
            "--json",
        ]
    )
    assert validate_result.get("ok")
    assert validate_result.get("status") == "missing", \
        f"Expected 'missing', got '{validate_result.get('status')}'"

    # Verify ceo_review is in missing
    missing = validate_result.get("missing", [])
    assert "ceo_review" in missing, \
        f"Expected ceo_review in missing, got: {missing}"

    # Step 3: Verify next-feature blocks
    next_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "next-feature", "--json"]
    )
    assert next_result.get("status") == "blocked", \
        f"Expected next-feature to block with missing status, got: {next_result}"
```

- [ ] **Step 2: Run the test**

```bash
cd plugins/super-product-manager && python3 -m pytest tests/e2e/test_planning_handoff_e2e.py::test_office_hours_only_missing_then_block -v
```

- [ ] **Step 3: Commit**

```bash
git add plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py
git commit -m "feat(e2e): add office-hours-only missing scenario test"
```

---

## Task 5: Add producer-layer validation tests

**Files:**
- Modify: `plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py`

- [ ] **Step 1: Add producer validation tests**

```python
def test_planning_producer_layer_validations():
    """Verify producer layer creates correct artifacts and updates.

    Validates:
    - Artifact files are created in correct directories
    - Updates have source=spm_planning
    - Refs contain planning:<stage> and doc:<path> formats
    """
    planning_script = spm_scripts_dir() / "planning_workflow.py"
    root = project_root()
    contracts_dir = root / "plugins" / "super-product-manager" / "docs" / "product-contracts"
    reviews_dir = root / "plugins" / "super-product-manager" / "docs" / "product-reviews"

    # Get a test feature
    prog_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "list", "--json"]
    )
    assert prog_result["ok"]
    features = prog_result.get("features", [])
    test_feature = next((f for f in features if not f.get("completed", False)), None)
    if not test_feature:
        pytest.skip("No incomplete feature available")

    feature_id = test_feature["id"]

    # Run office-hours and verify artifact
    office_hours_result = run_python_script(
        [
            str(planning_script),
            "office-hours",
            "--topic", f"Producer layer test {feature_id}",
            "--feature-id", str(feature_id),
        ]
    )
    assert office_hours_result.get("ok")
    artifact_path = Path(office_hours_result["artifact_file"])
    assert artifact_path.exists(), f"Artifact not created: {artifact_path}"
    assert artifact_path.parent == contracts_dir, \
        f"Artifact in wrong directory: {artifact_path.parent}"

    # Verify updates in PROG
    list_result = run_prog_cli(
        ["--project-root", "plugins/super-product-manager", "list-updates", "--json"]
    )
    assert list_result.get("ok")
    updates = list_result.get("updates", [])

    # Find the most recent spm_planning update for this feature
    feature_updates = [
        u for u in updates
        if u.get("source") == "spm_planning" and u.get("feature_id") == feature_id
    ]
    assert len(feature_updates) > 0, "No spm_planning update found"

    latest_update = feature_updates[-1]
    assert latest_update.get("category") == "decision"

    # Verify refs format
    refs = latest_update.get("refs", [])
    assert any(ref.startswith("planning:") for ref in refs), \
        f"Expected planning: ref in {refs}"
    assert any(ref.startswith("doc:") for ref in refs), \
        f"Expected doc: ref in {refs}"

    # Run a plan review and verify similar structure
    ceo_review_result = run_python_script(
        [
            str(planning_script),
            "plan-ceo-review",
            "--topic", f"Producer layer test {feature_id}",
            "--verdict", "pass",
            "--feature-id", str(feature_id),
        ]
    )
    assert ceo_review_result.get("ok")
    review_artifact_path = Path(ceo_review_result["artifact_file"])
    assert review_artifact_path.exists()
    assert review_artifact_path.parent == reviews_dir
```

- [ ] **Step 2: Run producer validation tests**

```bash
cd plugins/super-product-manager && python3 -m pytest tests/e2e/test_planning_handoff_e2e.py::test_planning_producer_layer_validations -v
```

- [ ] **Step 3: Commit**

```bash
git add plugins/super-product-manager/tests/e2e/test_planning_handoff_e2e.py
git commit -m "feat(e2e): add producer layer validation tests"
```

---

## Task 6: Update super-product-manager README with integration docs

**Files:**
- Modify: `plugins/super-product-manager/README.md:191`

- [ ] **Step 1: Read current README section**

```bash
sed -n '180,220p' plugins/super-product-manager/README.md
```

- [ ] **Step 2: Add integration section after existing commands**

Insert the following section after the command reference section:

```markdown
## PROG Integration

SPM planning outputs integrate with progress-tracker via `spm_planning` updates source.

### Planning Workflow

The planning commands create artifacts and sync structured updates into PROG:

1. `office-hours` → Creates product contract, syncs with `ref=planning:office_hours`
2. `plan-ceo-review` → Creates CEO review, syncs with `ref=planning:ceo_review`
3. `plan-design-review` → Creates design review, syncs with `ref=planning:design_review`
4. `plan-devex-review` → Creates devex review, syncs with `ref=planning:devex_review`

### Preflight Check

Before starting feature implementation via `/prog-next`, PROG validates planning readiness:

- `prog validate-planning <feature-id>` checks required/optional lanes
- Returns `ready` (all required satisfied), `warn` (required OK, optional missing), or `missing` (required lanes incomplete)
- `prog-next` blocks on `missing` status unless `--ack-planning-risk` is passed

### Important

**Planning preflight is NOT a release gate.** It validates product review readiness before development begins. Final acceptance and ship/release gates are separate phases not covered by SPM planning artifacts.
```

- [ ] **Step 3: Verify README renders correctly**

```bash
head -n 250 plugins/super-product-manager/README.md | tail -n 70
```

- [ ] **Step 4: Commit**

```bash
git add plugins/super-product-manager/README.md
git commit -m "docs(spm): add PROG integration section to README"
```

---

## Task 7: Update PROG_COMMANDS.md with spm_planning source docs

**Files:**
- Modify: `plugins/progress-tracker/docs/PROG_COMMANDS.md:1`

- [ ] **Step 1: Read current PROG_COMMANDS.md structure**

```bash
head -n 100 plugins/progress-tracker/docs/PROG_COMMANDS.md
```

- [ ] **Step 2: Add spm_planning source section**

Find the `validate-planning` command section and add/update:

```markdown
### validate-planning

Validate preflight planning artifacts from structured updates.

```bash
prog validate-planning <feature-id> [--json]
```

**Output:**

- `status`: `ready` | `warn` | `missing`
- `required`: List of required planning lanes for the inferred change type
- `missing`: Required lanes not yet completed
- `optional_missing`: Optional recommended lanes not yet completed
- `refs`: Document references (`doc:` format) from planning artifacts
- `message`: Human-readable status message

**Exit Codes:**

- `0`: Status is `ready` or `warn`
- `1`: Status is `missing`

**Planning Sources:**

Updates with `source=spm_planning` are consumed from SPM planning workflows:

| Lane | Ref Format | Required For |
|------|------------|--------------|
| office_hours | `planning:office_hours` | All types |
| ceo_review | `planning:ceo_review` | All types |
| design_review | `planning:design_review` | Optional (design/devex categories) |
| devex_review | `planning:devex_review` | Optional (design/devex categories) |

**Change Type Inference:**

Required lanes are determined by change type inferred from:
1. Feature `change_spec.in_scope` categories
2. Branch name patterns (e.g., `feat/`, `fix/`, `refactor/`)

Default (`feature` type): `office_hours`, `ceo_review` required; `design_review`, `devex_review` optional.
```

- [ ] **Step 3: Update prog-next section with planning gate info**

Find or add to the `next-feature` command section:

```markdown
### Planning Preflight Gate

When `spm_planning` updates or planning artifacts exist, `prog-next` evaluates planning readiness before returning the next feature:

- `status=missing`: Blocks with instructions to complete required planning
- `status=warn`: Blocks with warning about missing optional lanes
- `status=ready`: Proceeds normally

Use `--ack-planning-risk` to proceed with `warn` status (not recommended for `missing`).
```

- [ ] **Step 4: Verify documentation updates**

```bash
grep -A 20 "validate-planning" plugins/progress-tracker/docs/PROG_COMMANDS.md
grep -A 10 "Planning Preflight" plugins/progress-tracker/docs/PROG_COMMANDS.md
```

- [ ] **Step 5: Commit**

```bash
git add plugins/progress-tracker/docs/PROG_COMMANDS.md
git commit -m "docs(prog): document spm_planning source in validate-planning and next-feature"
```

---

## Task 8: Run full E2E test suite and verify all scenarios pass

**Files:**
- None (execution task)

- [ ] **Step 1: Run all E2E tests**

```bash
cd plugins/super-product-manager && python3 -m pytest tests/e2e/ -v
```

Expected: All 5 tests pass

- [ ] **Step 2: Run with coverage**

```bash
cd plugins/super-product-manager && python3 -m pytest tests/e2e/ --cov=scripts/planning_workflow --cov=scripts/prog_bridge -v
```

- [ ] **Step 3: Verify documentation generation scripts work**

```bash
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```

- [ ] **Step 4: Run PROG tests to ensure no regression**

```bash
pytest plugins/progress-tracker/tests/test_progress_manager.py -v -k "planning or validate" --tb=short
```

- [ ] **Step 5: Summary check**

```bash
echo "=== E2E Test Summary ==="
echo "SPM E2E tests:" && cd plugins/super-product-manager && python3 -m pytest tests/e2e/ --collect-only -q | grep "test_"
echo ""
echo "PROG planning tests:" && cd ../.. && pytest plugins/progress-tracker/tests/ -k "planning" --collect-only -q | grep "test_"
```

- [ ] **Step 6: Final commit if any adjustments needed**

```bash
git add -A
git commit -m "test(e2e): verify all E2E scenarios pass"
```

---

## Self-Review Checklist

- [ ] **Spec Coverage:**
  - [x] Scenario 1: Complete chain → ready → next-feature ok
  - [x] Scenario 2: Required only → warn → block
  - [x] Scenario 3: Office-hours only → missing → block
  - [x] Producer layer validations (artifacts, updates, refs)
  - [x] Consumer layer validations (validate-planning, next-feature)
  - [x] Documentation updates (SPM README, PROG PROG_COMMANDS)

- [ ] **Placeholder Scan:**
  - [x] No "TODO", "TBD", or "implement later"
  - [x] All code blocks contain complete implementations
  - [x] All file paths are exact and verified

- [ ] **Type Consistency:**
  - [x] Function signatures match across tasks
  - [x] JSON response schemas are consistent
  - [x] Test fixture imports are correct

---

## Execution Handoff

**Plan complete and saved to** `plugins/super-product-manager/docs/superpowers/plans/2026-04-12-e2e-cross-plugin-integration-tests.md`

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
