#!/usr/bin/env python3
"""E2E integration tests for SPM -> PROG planning handoff.

These tests validate the full chain: SPM planning workflow output is correctly
consumed by PROG validate-planning and prog-next (next-feature) commands.

Each test uses an isolated temp directory inside the repo (required by prog) to
avoid polluting the real project state.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[4]
SPM_PLUGIN_DIR = REPO_ROOT / "plugins" / "super-product-manager"
PROG_CLI = REPO_ROOT / "plugins" / "progress-tracker" / "prog"
# Scratch area inside the repo (required: project-root must be inside repo)
SCRATCH_BASE = REPO_ROOT / "plugins" / ".e2e-test-spm-scratch"


def _run_prog(
    project_root_rel: str,
    args: List[str],
    *,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Run prog CLI with --project-root and return parsed JSON (stdout) or raw result."""
    cmd = [str(PROG_CLI), "--project-root", project_root_rel, *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}

    # Try stdout JSON first (validate-planning --json / next-feature --json write to stdout)
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            pass

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _init_temp_project(scratch_dir: Path, project_name: str) -> str:
    """Initialize a temp PROG project inside the repo and return its relative path."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    rel_path = str(scratch_dir.relative_to(REPO_ROOT))
    result = _run_prog(rel_path, ["init", project_name])
    assert result.get("ok") is not False, f"init failed: {result}"
    return rel_path


def _add_feature(rel_path: str, name: str, test_step: str = "verify output") -> int:
    """Add a feature and return its ID."""
    result = _run_prog(rel_path, ["add-feature", name, test_step])
    # add-feature doesn't output JSON; check ok flag
    assert result.get("ok") is True, f"add-feature failed: {result}"
    # Parse ID from stdout e.g. "Added feature: name (ID: 3)"
    stdout = result.get("stdout", "")
    for token in stdout.split():
        if token.rstrip(")").isdigit():
            return int(token.rstrip(")"))
    raise RuntimeError(f"Could not parse feature ID from: {stdout!r}")


def _add_planning_update(
    rel_path: str,
    feature_id: int,
    stage: str,
    summary: str,
    doc_path: str,
) -> None:
    """Add a spm_planning update with planning:<stage> and doc: refs."""
    result = _run_prog(
        rel_path,
        [
            "add-update",
            "--category", "decision",
            "--summary", summary,
            "--source", "spm_planning",
            "--feature-id", str(feature_id),
            "--ref", f"planning:{stage}",
            "--ref", f"doc:{doc_path}",
        ],
    )
    assert result.get("ok") is True, f"add-update ({stage}) failed: {result}"


def _validate_planning(rel_path: str, feature_id: int) -> Dict[str, Any]:
    """Run validate-planning --json and return the parsed result."""
    result = _run_prog(
        rel_path, ["validate-planning", "--feature-id", str(feature_id), "--json"]
    )
    # validate-planning outputs JSON to stdout regardless of exit code
    assert "status" in result, f"validate-planning missing 'status': {result}"
    return result


def _next_feature(rel_path: str) -> Dict[str, Any]:
    """Run next-feature --json and return parsed result."""
    return _run_prog(rel_path, ["next-feature", "--json"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_project(tmp_path: Path):
    """Create an isolated PROG project inside the repo, yield rel path, then clean up."""
    # Use a unique dir under the repo-internal scratch area to satisfy the
    # "must be inside repo" constraint.  tmp_path itself is outside the repo.
    unique_name = f".e2e-{tmp_path.name}"
    scratch_dir = REPO_ROOT / "plugins" / unique_name
    rel_path = _init_temp_project(scratch_dir, "E2E Scratch")
    yield rel_path
    shutil.rmtree(scratch_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 1: complete planning chain -> "ready" and next-feature unblocked
# ---------------------------------------------------------------------------


def test_complete_planning_chain_happy_path(isolated_project: str) -> None:
    """Running the full 4-stage planning chain should produce status=ready and
    allow next-feature to return the feature without blocking."""
    rel_path = isolated_project

    feature_id = _add_feature(rel_path, "Feature Full Planning")

    _add_planning_update(
        rel_path, feature_id, "office_hours",
        "office-hours complete: Feature Full Planning",
        "docs/product-contracts/full-feature-office-hours.md",
    )
    _add_planning_update(
        rel_path, feature_id, "ceo_review",
        "plan-ceo-review complete: Feature Full Planning (approved)",
        "docs/product-reviews/full-feature-ceo-review.md",
    )
    _add_planning_update(
        rel_path, feature_id, "design_review",
        "plan-design-review complete: Feature Full Planning (score=8/10)",
        "docs/product-reviews/full-feature-design-review.md",
    )
    _add_planning_update(
        rel_path, feature_id, "devex_review",
        "plan-devex-review complete: Feature Full Planning (score=7/10)",
        "docs/product-reviews/full-feature-devex-review.md",
    )

    vp = _validate_planning(rel_path, feature_id)
    assert vp["ok"] is True
    assert vp["status"] == "ready", f"Expected 'ready', got {vp['status']!r}: {vp}"
    assert vp["missing"] == []
    assert vp["optional_missing"] == []
    assert vp["schema_version"] == "1.0"
    assert any("doc:" in r for r in vp["refs"]), "Expected doc: refs in result"

    nf = _next_feature(rel_path)
    assert nf.get("status") == "ok", f"Expected next-feature status=ok, got: {nf}"
    assert nf.get("feature_id") == feature_id


# ---------------------------------------------------------------------------
# Test 2: required only (office_hours + ceo_review) -> "warn" and next-feature blocks
# ---------------------------------------------------------------------------


def test_required_only_planning_warn_then_block(isolated_project: str) -> None:
    """Running only required planning stages (office_hours + ceo_review) should
    produce status=warn and cause next-feature to block with reason=planning_warn."""
    rel_path = isolated_project

    feature_id = _add_feature(rel_path, "Feature Required Only")

    _add_planning_update(
        rel_path, feature_id, "office_hours",
        "office-hours complete: Feature Required Only",
        "docs/product-contracts/req-only-office-hours.md",
    )
    _add_planning_update(
        rel_path, feature_id, "ceo_review",
        "plan-ceo-review complete: Feature Required Only (approved)",
        "docs/product-reviews/req-only-ceo-review.md",
    )
    # Deliberately NOT adding design_review or devex_review

    vp = _validate_planning(rel_path, feature_id)
    assert vp["ok"] is True
    assert vp["status"] == "warn", f"Expected 'warn', got {vp['status']!r}: {vp}"
    assert vp["missing"] == [], "Required stages should all be present"
    assert set(vp["optional_missing"]) == {"design_review", "devex_review"}

    nf = _next_feature(rel_path)
    assert nf.get("status") == "blocked", f"Expected blocked, got: {nf}"
    assert nf.get("reason") == "planning_warn", f"Expected reason=planning_warn: {nf}"
    assert nf.get("feature_id") == feature_id
    assert nf.get("optional_missing") == ["design_review", "devex_review"]


# ---------------------------------------------------------------------------
# Test 3: office_hours only -> "missing" and next-feature blocks
# ---------------------------------------------------------------------------


def test_office_hours_only_missing_then_block(isolated_project: str) -> None:
    """Running only office_hours should produce status=missing and cause
    next-feature to block."""
    rel_path = isolated_project

    feature_id = _add_feature(rel_path, "Feature Office Hours Only")

    _add_planning_update(
        rel_path, feature_id, "office_hours",
        "office-hours complete: Feature Office Hours Only",
        "docs/product-contracts/oh-only-office-hours.md",
    )
    # Deliberately NOT adding ceo_review, design_review, or devex_review

    vp = _validate_planning(rel_path, feature_id)
    assert vp["ok"] is True
    assert vp["status"] == "missing", f"Expected 'missing', got {vp['status']!r}: {vp}"
    assert "ceo_review" in vp["missing"], f"ceo_review should be in missing: {vp}"
    assert vp["message"] == "planning.missing"

    nf = _next_feature(rel_path)
    assert nf.get("status") == "blocked", f"Expected blocked, got: {nf}"


# ---------------------------------------------------------------------------
# Test 4: producer layer validations (artifact files + source + refs format)
# ---------------------------------------------------------------------------


def test_planning_producer_layer_validations() -> None:
    """Verify that the SPM planning_workflow Python API:
    - Creates artifact files in the correct directories
    - Syncs updates with source=spm_planning
    - Creates refs in 'planning:<stage>' and 'doc:<path>' format

    This test runs against REAL SPM project state (feature 5 / SPM-2) which is
    known to have all 4 planning stages completed.
    """
    # Verify PROG CLI is accessible
    if not PROG_CLI.exists():
        pytest.skip(f"prog CLI not found at {PROG_CLI}")

    # Use feature 5 (SPM-2) which already has all 4 planning stages done
    vp = _validate_planning(
        "plugins/super-product-manager", feature_id=5
    )
    assert vp["ok"] is True
    assert vp["status"] == "ready", f"Feature 5 should be ready: {vp}"

    # Verify refs include both planning: and doc: formats
    refs = vp.get("refs", [])
    doc_refs = [r for r in refs if r.startswith("doc:")]
    assert len(doc_refs) >= 4, (
        f"Expected at least 4 doc: refs for all planning stages, got: {refs}"
    )

    # Verify the doc: refs point to files that actually exist
    for ref in doc_refs:
        rel_path = ref[len("doc:"):]
        artifact_path = SPM_PLUGIN_DIR / rel_path
        assert artifact_path.exists(), (
            f"Artifact referenced in planning ref does not exist: {artifact_path}"
        )

    # Verify artifact files are in the correct directories
    contracts_dir = SPM_PLUGIN_DIR / "docs" / "product-contracts"
    reviews_dir = SPM_PLUGIN_DIR / "docs" / "product-reviews"

    office_hours_refs = [r for r in doc_refs if "office-hours" in r]
    ceo_review_refs = [r for r in doc_refs if "ceo-review" in r]
    design_review_refs = [r for r in doc_refs if "design-review" in r]
    devex_review_refs = [r for r in doc_refs if "devex-review" in r]

    assert office_hours_refs, "Expected at least one office-hours doc ref"
    assert ceo_review_refs, "Expected at least one ceo-review doc ref"
    assert design_review_refs, "Expected at least one design-review doc ref"
    assert devex_review_refs, "Expected at least one devex-review doc ref"

    # Office-hours artifacts go into product-contracts
    for ref in office_hours_refs:
        rel = ref[len("doc:"):]
        assert rel.startswith("docs/product-contracts/"), (
            f"office-hours artifact should be in product-contracts: {rel}"
        )

    # Review artifacts go into product-reviews
    for ref in ceo_review_refs + design_review_refs + devex_review_refs:
        rel = ref[len("doc:"):]
        assert rel.startswith("docs/product-reviews/"), (
            f"review artifact should be in product-reviews: {rel}"
        )

    # Verify source=spm_planning in progress.json updates
    progress_json = SPM_PLUGIN_DIR / "docs" / "progress-tracker" / "state" / "progress.json"
    assert progress_json.exists(), f"progress.json not found at {progress_json}"

    data = json.loads(progress_json.read_text(encoding="utf-8"))
    updates = data.get("updates", [])
    spm_planning_updates = [
        u for u in updates
        if u.get("source") == "spm_planning" and u.get("feature_id") == 5
    ]
    assert spm_planning_updates, "Expected spm_planning updates for feature 5"

    # Verify refs contain both planning: and doc: formats
    for upd in spm_planning_updates:
        upd_refs = upd.get("refs", [])
        planning_refs = [r for r in upd_refs if r.startswith("planning:")]
        doc_refs_in_upd = [r for r in upd_refs if r.startswith("doc:")]
        assert planning_refs, f"Update {upd['id']} missing planning: ref"
        assert doc_refs_in_upd, f"Update {upd['id']} missing doc: ref"

        # Validate planning: ref is a known stage
        for pref in planning_refs:
            stage = pref[len("planning:"):]
            assert stage in {"office_hours", "ceo_review", "design_review", "devex_review"}, (
                f"Unknown planning stage in ref: {pref}"
            )
