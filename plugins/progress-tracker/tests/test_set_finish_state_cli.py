#!/usr/bin/env python3
"""CLI contract for `prog set-finish-state` resolver."""

import json
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
PROGRESS_MANAGER = PLUGIN_ROOT / "hooks" / "scripts" / "progress_manager.py"


def _run(args, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROGRESS_MANAGER), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "docs" / "progress-tracker" / "state" / "progress.json"


def _load_feature(tmp_path: Path, feature_id: int = 1) -> dict:
    data = json.loads(_state_path(tmp_path).read_text(encoding="utf-8"))
    return next(feature for feature in data["features"] if feature.get("id") == feature_id)


def test_set_finish_state_rejects_unknown_status(tmp_path):
    _run(["init", "Resolver Project"], cwd=tmp_path)
    _run(["add-feature", "Feature A", "step 1"], cwd=tmp_path)

    result = _run(
        ["set-finish-state", "--feature-id", "1", "--status", "bogus"],
        cwd=tmp_path,
    )

    assert result.returncode != 0
    assert "invalid choice" in result.stderr.lower() or "usage:" in result.stderr.lower()


def test_set_finish_state_clears_finish_pending_to_merged_and_cleaned(tmp_path):
    _run(["init", "Resolver Project"], cwd=tmp_path)
    _run(["add-feature", "Feature A", "step 1"], cwd=tmp_path)

    state_path = _state_path(tmp_path)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    feature = data["features"][0]
    feature["lifecycle_state"] = "verified"
    feature["integration_status"] = "finish_pending"
    feature["finish_pending_reason"] = "worktree cleanup required"
    state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    result = _run(
        [
            "set-finish-state",
            "--feature-id",
            "1",
            "--status",
            "merged_and_cleaned",
            "--reason",
            "manual resolution",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0

    feature = _load_feature(tmp_path, feature_id=1)
    assert feature["integration_status"] == "merged_and_cleaned"
    assert "finish_pending_reason" not in feature
    assert feature["finish_state_resolved_reason"] == "manual resolution"


def test_set_finish_state_refuses_when_feature_not_in_finish_pending(tmp_path):
    _run(["init", "Resolver Project"], cwd=tmp_path)
    _run(["add-feature", "Feature A", "step 1"], cwd=tmp_path)

    result = _run(
        ["set-finish-state", "--feature-id", "1", "--status", "merged_and_cleaned"],
        cwd=tmp_path,
    )

    assert result.returncode == 4
    assert "not in finish_pending" in result.stderr.lower()


def test_set_finish_state_writes_audit_log_entry(tmp_path):
    _run(["init", "Resolver Project"], cwd=tmp_path)
    _run(["add-feature", "Feature A", "step 1"], cwd=tmp_path)

    state_path = _state_path(tmp_path)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    feature = data["features"][0]
    feature["integration_status"] = "finish_pending"
    feature["finish_pending_reason"] = "manual"
    state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    result = _run(
        [
            "set-finish-state",
            "--feature-id",
            "1",
            "--status",
            "pr_open",
            "--reason",
            "PR filed",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0

    audit_path = tmp_path / "docs" / "progress-tracker" / "state" / "audit.log"
    assert audit_path.exists()
    entries = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching = [entry for entry in entries if entry.get("event_type") == "set_finish_state"]
    assert matching
    assert matching[-1]["feature_id"] == 1
    assert matching[-1]["details"]["to_status"] == "pr_open"
