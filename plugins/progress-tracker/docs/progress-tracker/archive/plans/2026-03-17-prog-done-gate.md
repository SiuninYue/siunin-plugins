# Feature 8: /prog-done 收尾门禁 Implementation Plan (SUPERSEDED)

> **Superseded by:** docs/superpowers/plans/2026-03-17-prog-done-gate-v2.md
> **Reason:** Multiple P1 issues identified and fixed in v2:
> 1. CLI 测试调用方式不匹配（python3 -m vs patch sys.argv）
> 2. "done" 未纳入 MUTATING_COMMANDS 集合
> 3. get_state_dir() API 调用不兼容
> 4. 验收测试目录使用 os.getcwd() 而非 find_project_root()
> 5. 与 /prog-done skill 契约分叉
> 6. 报告目录不一致
> 7. Task 1 测试逻辑矛盾

> **NOTE:** This file is preserved for historical reference only. Use v2 for implementation.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `/prog done` command with comprehensive gatekeeping: preconditions validation, acceptance test execution, test reporting, and finish_pending state tracking.

**Architecture:** Add `done` subcommand to progress_manager.py that validates preconditions, runs acceptance tests from feature's test_steps, saves detailed test reports, and either completes the feature (calling existing `complete_feature`) or records finish_pending status with failure reasons.

**Tech Stack:** Python 3.14, pytest, subprocess, datetime, pathlib

---

## File Structure

**Modify:**
- `plugins/progress-tracker/hooks/scripts/progress_manager.py` - Add done command, validation functions, test execution logic
- `plugins/progress-tracker/tests/test_feature_completion_state_transition.py` - Update tests to use actual done command
- `plugins/progress-tracker/tests/test_progress_manager.py` - Add tests for done command
- `plugins/progress-tracker/tests/test_integration.py` - Update integration tests

**Create:**
- `plugins/progress-tracker/hooks/scripts/test_reports/` - Directory for test reports (created dynamically)

**Dependencies:**
- Existing `complete_feature` function (line 3440)
- Existing `load_progress_json`, `save_progress_json` functions
- Existing test infrastructure (temp_dir fixtures)

---

### Task 1: Add done command parser and main entry point

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:5060-5065` (after complete parser)
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:5294-5299` (after complete command handler)

- [ ] **Step 1: Write the failing test**

```python
# In test_progress_manager.py
def test_done_command_no_active_feature(temp_dir):
    """Test done command fails when no active feature."""
    # Setup empty progress state
    data = {
        "project_name": "Test",
        "created_at": "2026-03-17T00:00:00Z",
        "features": [],
        "current_feature_id": None,
        "schema_version": "2.0"
    }
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(json.dumps(data, indent=2))

    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        # Run done command
        result = subprocess.run(
            ["python3", "-m", "progress_manager", "done"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "无活动功能" in result.stdout or "no active feature" in result.stdout
    finally:
        os.chdir(original_cwd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_no_active_feature -v`
Expected: FAIL with "python3: can't open file '-m': [Errno 2] No such file or directory" or similar (command not implemented)

- [ ] **Step 3: Add done command parser**

```python
# After complete_parser (around line 5060)
done_parser = subparsers.add_parser("done", help="Complete current feature with acceptance tests")
done_parser.add_argument("--commit", help="Git commit hash (default: HEAD)")
done_parser.add_argument("--run-all", action="store_true",
                         help="Run all tests even if some fail (default: stop on first failure)")
done_parser.add_argument("--skip-archive", action="store_true",
                         help="Skip document archiving")
```

- [ ] **Step 4: Add done command handler**

```python
# After complete command handler (around line 5294)
if args.command == "done":
    return cmd_done(
        commit_hash=args.commit,
        run_all=args.run_all,
        skip_archive=args.skip_archive
    )
```

- [ ] **Step 5: Add stub cmd_done function**

```python
# Before complete_feature function (around line 3430)
def cmd_done(commit_hash=None, run_all=False, skip_archive=False):
    """Complete current feature with acceptance tests."""
    print("[DONE] Not implemented yet")
    return False
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_no_active_feature -v`
Expected: PASS (command exists but returns False)

- [ ] **Step 7: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git add plugins/progress-tracker/tests/test_progress_manager.py
git commit -m "feat: add done command stub"
```

---

### Task 2: Implement preconditions validation

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3430-3500` (add validation functions before cmd_done)

- [ ] **Step 1: Write the failing test**

```python
def test_done_command_wrong_workflow_phase(temp_dir):
    """Test done command fails when workflow phase is not execution_complete."""
    data = {
        "project_name": "Test",
        "created_at": "2026-03-17T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Test Feature",
                "test_steps": ["echo 'test'"],
                "completed": False,
                "development_stage": "developing"
            }
        ],
        "current_feature_id": 1,
        "workflow_state": {
            "phase": "execution",
            "next_action": "Implement feature"
        },
        "schema_version": "2.0"
    }
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(json.dumps(data, indent=2))

    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        result = subprocess.run(
            ["python3", "-m", "progress_manager", "done"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 2
        assert "工作流阶段" in result.stdout or "workflow phase" in result.stdout
    finally:
        os.chdir(original_cwd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_wrong_workflow_phase -v`
Expected: FAIL (validation not implemented)

- [ ] **Step 3: Implement _validate_done_preconditions function**

```python
def _validate_done_preconditions(data):
    """
    Validate done command preconditions.
    Returns: (is_valid, reason, error_code)
    """
    # Check 1: current_feature_id
    current_id = data.get("current_feature_id")
    if current_id is None:
        return False, "无活动功能，请先运行 /prog next", 1

    # Check 2: workflow_state.phase
    workflow_state = data.get("workflow_state", {})
    phase = workflow_state.get("phase")
    if phase != "execution_complete":
        return False, f"工作流阶段为 '{phase}'，需先完成实现（phase=execution_complete）", 2

    # Check 3: feature exists
    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == current_id), None)
    if not feature:
        return False, f"Feature {current_id} 不存在", 4

    # Check 4: feature not already completed
    if feature.get("completed", False):
        return False, f"Feature {current_id} 已完成", 5

    return True, "", 0
```

- [ ] **Step 4: Update cmd_done to use validation**

```python
def cmd_done(commit_hash=None, run_all=False, skip_archive=False):
    """Complete current feature with acceptance tests."""
    data = load_progress_json()
    if not data:
        print("[DONE] No progress tracking found")
        return 4

    valid, reason, code = _validate_done_preconditions(data)
    if not valid:
        print(f"[DONE] BLOCKED: {reason}")
        return code

    print("[DONE] Preconditions satisfied")
    return 0  # Temporary
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_wrong_workflow_phase -v`
Expected: PASS (returns error code 2)

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git add plugins/progress-tracker/tests/test_progress_manager.py
git commit -m "feat: add done preconditions validation"
```

---

### Task 3: Implement acceptance test execution

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3430-3600` (add test execution functions)

- [ ] **Step 1: Write the failing test**

```python
def test_done_command_runs_acceptance_tests(temp_dir):
    """Test done command runs acceptance tests from test_steps."""
    data = {
        "project_name": "Test",
        "created_at": "2026-03-17T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Test Feature",
                "test_steps": [
                    "echo 'test step 1'",
                    "echo 'test step 2'",
                    "DoD: Manual verification"
                ],
                "completed": False,
                "development_stage": "completed",
                "lifecycle_state": "verified"
            }
        ],
        "current_feature_id": 1,
        "workflow_state": {
            "phase": "execution_complete",
            "next_action": "Run acceptance tests"
        },
        "schema_version": "2.0"
    }
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(json.dumps(data, indent=2))

    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        result = subprocess.run(
            ["python3", "-m", "progress_manager", "done", "--run-all"],
            capture_output=True,
            text=True
        )
        # Should run tests but not complete (tests pass but we're not implementing completion yet)
        assert result.returncode == 0 or result.returncode == 3
        assert "test step 1" in result.stdout or "test step 2" in result.stdout
    finally:
        os.chdir(original_cwd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_runs_acceptance_tests -v`
Expected: FAIL (test execution not implemented)

- [ ] **Step 3: Implement _is_executable_step helper**

```python
def _is_executable_step(step):
    """Check if a test step is executable (not a DoD or comment)."""
    step = step.strip()
    if not step:
        return False
    if step.startswith("DoD:"):
        return False
    if step.startswith("#"):
        return False
    if step.startswith("//"):
        return False
    return True
```

- [ ] **Step 4: Implement _run_acceptance_tests function**

```python
import time
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class TestResult:
    step: str
    command: str
    success: bool
    output: str
    duration_ms: int
    error: str = None

def _run_acceptance_tests(feature_id: int, run_all: bool = False) -> Tuple[bool, List[TestResult]]:
    """Run acceptance tests from feature's test_steps."""
    data = load_progress_json()
    if not data:
        return False, []

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        return False, []

    test_steps = feature.get("test_steps", [])
    results = []
    all_passed = True

    for step in test_steps:
        if not _is_executable_step(step):
            continue

        start_time = time.time()
        try:
            result = subprocess.run(
                step,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
                cwd=os.getcwd()
            )
            success = result.returncode == 0
            error_output = result.stderr if not success else None
        except subprocess.TimeoutExpired:
            success = False
            error_output = "Timeout after 300 seconds"
            result = type('obj', (object,), {'stdout': '', 'stderr': error_output})()
        except Exception as e:
            success = False
            error_output = str(e)
            result = type('obj', (object,), {'stdout': '', 'stderr': error_output})()

        duration_ms = int((time.time() - start_time) * 1000)

        # Combine stdout and stderr for output summary
        combined_output = result.stdout[:500] + result.stderr[:500]

        results.append(TestResult(
            step=step,
            command=step,
            success=success,
            output=combined_output,
            duration_ms=duration_ms,
            error=error_output
        ))

        if not success:
            all_passed = False
            if not run_all:
                break  # Early stop on first failure

    return all_passed, results
```

- [ ] **Step 5: Update cmd_done to run tests**

```python
def cmd_done(commit_hash=None, run_all=False, skip_archive=False):
    """Complete current feature with acceptance tests."""
    data = load_progress_json()
    if not data:
        print("[DONE] No progress tracking found")
        return 4

    valid, reason, code = _validate_done_preconditions(data)
    if not valid:
        print(f"[DONE] BLOCKED: {reason}")
        return code

    feature_id = data["current_feature_id"]

    # Run acceptance tests
    print(f"[DONE] 运行验收测试 (Feature {feature_id})...")
    all_passed, test_results = _run_acceptance_tests(feature_id, run_all)

    if not all_passed:
        failed_count = sum(1 for r in test_results if not r.success)
        total_count = len(test_results)
        print(f"[DONE] FAILED: 验收测试失败 ({total_count - failed_count}/{total_count} 通过)")
        for result in test_results:
            if not result.success:
                print(f"  - {result.command}")
                print(f"    → exit code {result.returncode if hasattr(result, 'returncode') else 'N/A'}, 耗时 {result.duration_ms}ms")
                if result.error:
                    print(f"    → {result.error[:200]}")
        return 3

    print("[DONE] 所有验收测试通过")
    return 0  # Temporary
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_runs_acceptance_tests -v`
Expected: PASS (runs tests and returns 0)

- [ ] **Step 7: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git add plugins/progress-tracker/tests/test_progress_manager.py
git commit -m "feat: implement acceptance test execution"
```

---

### Task 4: Implement test report saving

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3600-3700` (add report saving functions)

- [ ] **Step 1: Write the failing test**

```python
def test_done_command_saves_test_report(temp_dir):
    """Test done command saves test report to file."""
    data = {
        "project_name": "Test",
        "created_at": "2026-03-17T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Test Feature",
                "test_steps": ["echo 'test report'"],
                "completed": False,
                "development_stage": "completed",
                "lifecycle_state": "verified"
            }
        ],
        "current_feature_id": 1,
        "workflow_state": {
            "phase": "execution_complete",
            "next_action": "Run acceptance tests"
        },
        "schema_version": "2.0"
    }
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(json.dumps(data, indent=2))

    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        result = subprocess.run(
            ["python3", "-m", "progress_manager", "done"],
            capture_output=True,
            text=True
        )
        # Check if report file was created
        report_dir = state_dir / "test_reports"
        report_files = list(report_dir.glob("feature-1-done-attempt-*.json"))
        assert len(report_files) > 0
        # Check report content
        report = json.loads(report_files[0].read_text())
        assert report["feature_id"] == 1
        assert "results" in report
    finally:
        os.chdir(original_cwd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_saves_test_report -v`
Expected: FAIL (report saving not implemented)

- [ ] **Step 3: Implement _save_test_report function**

```python
import shutil
from pathlib import Path

def _save_test_report(feature_id: int, results: List[TestResult], success: bool):
    """Save test report to state directory."""
    data = load_progress_json()
    if not data:
        return

    report = {
        "feature_id": feature_id,
        "done_attempt_at": datetime.now().isoformat(),
        "overall_success": success,
        "results": [
            {
                "step": r.step,
                "command": r.command,
                "success": r.success,
                "output_summary": r.output[:200],
                "duration_ms": r.duration_ms,
                "error": r.error[:200] if r.error else None
            }
            for r in results
        ]
    }

    # Get state directory
    try:
        state_dir = get_state_dir()
    except:
        # Fallback: current directory
        state_dir = Path.cwd() / "docs" / "progress-tracker" / "state"

    report_dir = state_dir / "test_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp for filename
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    report_path = report_dir / f"feature-{feature_id}-done-attempt-{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2))

    # Clean up old reports (keep last 5)
    _cleanup_old_reports(report_dir, feature_id)

def _cleanup_old_reports(report_dir: Path, feature_id: int):
    """Keep only the 5 most recent test reports for a feature."""
    pattern = f"feature-{feature_id}-done-attempt-*.json"
    reports = sorted(report_dir.glob(pattern), key=lambda p: p.name, reverse=True)

    for old_report in reports[5:]:
        try:
            old_report.unlink()
        except:
            pass  # Ignore errors
```

- [ ] **Step 4: Update cmd_done to save reports**

```python
def cmd_done(commit_hash=None, run_all=False, skip_archive=False):
    """Complete current feature with acceptance tests."""
    data = load_progress_json()
    if not data:
        print("[DONE] No progress tracking found")
        return 4

    valid, reason, code = _validate_done_preconditions(data)
    if not valid:
        print(f"[DONE] BLOCKED: {reason}")
        return code

    feature_id = data["current_feature_id"]

    # Run acceptance tests
    print(f"[DONE] 运行验收测试 (Feature {feature_id})...")
    all_passed, test_results = _run_acceptance_tests(feature_id, run_all)

    # Save test report
    _save_test_report(feature_id, test_results, all_passed)

    if not all_passed:
        failed_count = sum(1 for r in test_results if not r.success)
        total_count = len(test_results)
        print(f"[DONE] FAILED: 验收测试失败 ({total_count - failed_count}/{total_count} 通过)")
        # ... (rest of failure output)

        # Record finish_pending state
        features = data.get("features", [])
        feature = next((f for f in features if f.get("id") == feature_id), None)
        if feature:
            failure_reason = _format_failure_reason(test_results)
            feature["finish_pending_reason"] = failure_reason
            feature["last_done_attempt_at"] = datetime.now().isoformat()
            save_progress_json(data)

        print(f"详细报告: docs/progress-tracker/state/test_reports/feature-{feature_id}-done-attempt-*.json")
        return 3

    print("[DONE] 所有验收测试通过")
    return 0  # Temporary
```

- [ ] **Step 5: Implement _format_failure_reason helper**

```python
def _format_failure_reason(test_results):
    """Format failure reason from test results."""
    failed_tests = [r for r in test_results if not r.success]
    if not failed_tests:
        return "未知原因"

    reasons = []
    for result in failed_tests[:3]:  # Limit to 3 failures
        reason = f"{result.command}"
        if result.error:
            reason += f" → {result.error[:100]}"
        reasons.append(reason)

    if len(failed_tests) > 3:
        reasons.append(f"...等 {len(failed_tests)} 个失败测试")

    return "; ".join(reasons)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_saves_test_report -v`
Expected: PASS (saves report file)

- [ ] **Step 7: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git add plugins/progress-tracker/tests/test_progress_manager.py
git commit -m "feat: implement test report saving"
```

---

### Task 5: Integrate with complete_feature and cleanup

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3440-3530` (update complete_feature)
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3700-3800` (finish cmd_done)

- [ ] **Step 1: Write the failing test**

```python
def test_done_command_completes_feature(temp_dir):
    """Test done command successfully completes feature when tests pass."""
    data = {
        "project_name": "Test",
        "created_at": "2026-03-17T00:00:00Z",
        "features": [
            {
                "id": 1,
                "name": "Test Feature",
                "test_steps": ["true"],  # Always succeeds
                "completed": False,
                "development_stage": "completed",
                "lifecycle_state": "verified"
            }
        ],
        "current_feature_id": 1,
        "workflow_state": {
            "phase": "execution_complete",
            "next_action": "Run acceptance tests"
        },
        "schema_version": "2.0"
    }
    state_dir = temp_dir / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "progress.json").write_text(json.dumps(data, indent=2))

    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        result = subprocess.run(
            ["python3", "-m", "progress_manager", "done"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "已完成" in result.stdout or "completed" in result.stdout

        # Verify feature is marked completed
        updated_data = json.loads((state_dir / "progress.json").read_text())
        feature = next(f for f in updated_data["features"] if f["id"] == 1)
        assert feature["completed"] == True
        assert feature["development_stage"] == "completed"
        assert updated_data["current_feature_id"] is None
    finally:
        os.chdir(original_cwd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_completes_feature -v`
Expected: FAIL (doesn't call complete_feature yet)

- [ ] **Step 3: Update complete_feature to clean finish_pending fields**

```python
def complete_feature(feature_id, commit_hash=None, skip_archive=False):
    """Mark a feature as completed."""
    # ... existing code until line 3490 ...

    feature["completed"] = True
    feature["development_stage"] = "completed"
    feature["lifecycle_state"] = "verified"
    feature["completed_at"] = _iso_now()
    _clear_feature_defer_state(feature)

    # Clean up finish_pending fields
    if "finish_pending_reason" in feature:
        del feature["finish_pending_reason"]
    if "last_done_attempt_at" in feature:
        del feature["last_done_attempt_at"]

    # ... rest of existing code ...
```

- [ ] **Step 4: Update cmd_done to call complete_feature**

```python
def cmd_done(commit_hash=None, run_all=False, skip_archive=False):
    """Complete current feature with acceptance tests."""
    # ... existing code until tests pass ...

    print("[DONE] 所有验收测试通过")

    # Get commit hash (default: HEAD)
    if not commit_hash:
        try:
            if GIT_VALIDATOR_AVAILABLE:
                commit_hash = get_current_commit_hash()
            else:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", "HEAD"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    commit_hash = result.stdout.strip()
        except Exception as e:
            print(f"[DONE] WARNING: 无法获取当前提交哈希: {e}")
            commit_hash = None

    # Complete the feature
    success = complete_feature(
        feature_id,
        commit_hash=commit_hash,
        skip_archive=skip_archive
    )

    if success:
        print(f"[DONE] Feature {feature_id} 已完成")
        if commit_hash:
            print(f"        提交: {commit_hash}")
        print(f"        下一步: /prog next")
        return 0
    else:
        print("[DONE] 完成功能时出错")
        return 4
```

- [ ] **Step 5: Implement _get_head_commit helper**

```python
def _get_head_commit():
    """Get current HEAD commit hash."""
    try:
        if GIT_VALIDATOR_AVAILABLE:
            return get_current_commit_hash()
        else:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
    except Exception:
        return None
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest plugins/progress-tracker/tests/test_progress_manager.py::test_done_command_completes_feature -v`
Expected: PASS (completes feature successfully)

- [ ] **Step 7: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git add plugins/progress-tracker/tests/test_progress_manager.py
git commit -m "feat: integrate done with complete_feature"
```

---

### Task 6: Update existing tests to use new done command

**Files:**
- Modify: `plugins/progress-tracker/tests/test_feature_completion_state_transition.py`
- Modify: `plugins/progress-tracker/tests/test_integration.py`

- [ ] **Step 1: Update test_feature_completion_state_transition.py**

```python
# Update test to use actual done command instead of skill
def test_complete_feature_via_done_command(self, feature_in_planning):
    """Feature should transition from planning → developing → completed via done command."""
    # ... existing setup ...

    # Instead of calling skill, use done command
    result = subprocess.run(
        ["python3", "-m", "progress_manager", "done"],
        capture_output=True,
        text=True,
        cwd=temp_dir
    )
    assert result.returncode == 0, f"done command failed: {result.stderr}"

    # ... rest of assertions ...
```

- [ ] **Step 2: Run updated tests**

Run: `pytest plugins/progress-tracker/tests/test_feature_completion_state_transition.py -v`
Expected: PASS (tests updated to use new command)

- [ ] **Step 3: Update test_integration.py**

Search for tests that use "prog_done" or "complete" and update to use actual command if needed.

- [ ] **Step 4: Run integration tests**

Run: `pytest plugins/progress-tracker/tests/test_integration.py -k "prog_done or complete" -v`
Expected: PASS or appropriate failures that need fixing

- [ ] **Step 5: Run all acceptance tests for Feature 8**

Run the 3 acceptance test suites specified in Feature 8:
1. `pytest tests/test_feature_completion_state_transition.py -q`
2. `pytest tests/test_progress_manager.py -q -k "finish or cleanup or worktree or next"`
3. `pytest tests/test_integration.py -q -k "prog_done or complete"`

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/tests/test_feature_completion_state_transition.py
git add plugins/progress-tracker/tests/test_integration.py
git commit -m "test: update existing tests to use done command"
```

---

### Task 7: Final verification and documentation

**Files:**
- Modify: `plugins/progress-tracker/commands/prog-done.md` (update to reflect actual implementation)

- [ ] **Step 1: Test CLI output formatting**

Create a simple test to verify all output formats:
- Success case
- Precondition failures (error codes 1, 2, 4, 5)
- Test failure (error code 3)
- System error (error code 4)

- [ ] **Step 2: Verify error code contract**

Ensure error codes match design:
- 0: Success
- 1: No active feature
- 2: Wrong workflow phase
- 3: Acceptance tests failed
- 4: System error / feature not found
- 5: Feature already completed

- [ ] **Step 3: Update prog-done.md documentation**

```markdown
---
description: Complete current feature with acceptance tests
version: "1.0.0"
scope: command
inputs:
  - User request to complete current feature
outputs:
  - Test execution results
  - Feature marked as completed
  - Git commit with changes
  - Next step recommendation
evidence: optional
references: []
model: sonnet
---

`/prog done` completes the currently active feature after running acceptance tests.

**Behavior:**
1. Validates preconditions (active feature, workflow phase = execution_complete)
2. Runs acceptance tests from feature's `test_steps`
3. Saves detailed test report to `docs/progress-tracker/state/test_reports/`
4. If tests pass: marks feature as completed, records commit hash
5. If tests fail: records `finish_pending_reason` for next attempt

**Options:**
- `--commit <hash>`: Specify commit hash (default: current HEAD)
- `--run-all`: Run all tests even if some fail (default: stop on first failure)
- `--skip-archive`: Skip document archiving

**Exit Codes:**
- 0: Success
- 1: No active feature
- 2: Wrong workflow phase (not execution_complete)
- 3: Acceptance tests failed
- 4: System error / feature not found
- 5: Feature already completed
```

- [ ] **Step 4: Run final comprehensive test suite**

Run all tests related to feature completion:
```bash
pytest plugins/progress-tracker/tests/ -v
```

Expected: All tests pass

- [ ] **Step 5: Commit final changes**

```bash
git add plugins/progress-tracker/commands/prog-done.md
git commit -m "docs: update prog-done command documentation"
```

---

## Plan Review

This plan implements the full `/prog done` command with:
1. Preconditions validation with clear error codes
2. Acceptance test execution with early stopping (configurable)
3. Test report saving with cleanup (keep last 5 reports)
4. Finish_pending state tracking (without new lifecycle_state)
5. Integration with existing `complete_feature` function
6. Updated tests to use actual command instead of skill

The implementation follows TDD with small, testable steps and frequent commits.