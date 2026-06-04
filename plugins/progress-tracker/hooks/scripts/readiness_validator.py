"""
readiness_validator.py — Feature readiness validation and remediation commands.

Extracted from progress_manager.py (F21 Round 2 modularisation).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from state_io import _normalize_feature_contract, _normalize_ref_tokens
from prog_paths import find_project_root

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROG_CLI_COMMAND = "plugins/progress-tracker/prog"

PLANNING_SCHEMA_VERSION = "1.0"
PLANNING_SOURCE = "spm_planning"
PLANNING_REQUIRED_REFS = ("office_hours", "ceo_review")
PLANNING_OPTIONAL_REFS = ("design_review", "devex_review")
PLANNING_ARTIFACT_DIRS = ("docs/product-contracts", "docs/product-reviews")
PLANNING_MESSAGE_KEYS = {
    "gate_disabled": "planning.gate_disabled",
    "missing": "planning.missing",
    "optional_missing": "planning.optional_missing",
    "ready": "planning.ready",
}


# ---------------------------------------------------------------------------
# Injected-services container
# ---------------------------------------------------------------------------

@dataclass
class ReadinessValidatorServices:
    """Bundle of callbacks injected from progress_manager to avoid reverse imports."""

    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    save_progress_json_fn: Callable[[Dict[str, Any]], None]
    generate_progress_md_fn: Callable[[Dict[str, Any]], str]
    save_progress_md_fn: Callable[[str], None]


# ---------------------------------------------------------------------------
# Planning validation core business logic
# ---------------------------------------------------------------------------

def _collect_update_refs(update_item: Dict[str, Any]) -> List[str]:
    """Collect refs and overflow refs from one update item."""
    refs: List[str] = []
    inline_refs = update_item.get("refs")
    if isinstance(inline_refs, list):
        refs.extend([ref for ref in inline_refs if isinstance(ref, str)])
    overflow_refs = update_item.get("refs_overflow")
    if isinstance(overflow_refs, list):
        refs.extend([ref for ref in overflow_refs if isinstance(ref, str)])
    return _normalize_ref_tokens(refs)


def _planning_gate_enabled(data: Dict[str, Any]) -> bool:
    """Return whether preflight planning gate should be evaluated for this project."""
    updates = data.get("updates", [])
    if isinstance(updates, list):
        for item in updates:
            if not isinstance(item, dict):
                continue
            if str(item.get("source") or "").strip().lower() == PLANNING_SOURCE:
                return True

    project_root = find_project_root()
    for rel_path in PLANNING_ARTIFACT_DIRS:
        if (project_root / rel_path).exists():
            return True
    return False


def _evaluate_planning_readiness(
    data: Dict[str, Any],
    feature_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Evaluate preflight planning readiness from updates + refs without schema changes.

    Contract:
      {
        "ok": true,
        "status": "ready|warn|missing",
        "required": ["office_hours", "ceo_review"],
        "missing": [...],
        "optional_missing": [...],
        "refs": ["doc:..."],
        "message": "..."
      }
    """
    required = list(PLANNING_REQUIRED_REFS)
    optional = list(PLANNING_OPTIONAL_REFS)

    planning_refs: List[str] = []
    updates = data.get("updates", [])
    if isinstance(updates, list):
        for item in updates:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip().lower()
            if source != PLANNING_SOURCE:
                continue
            item_feature_id = item.get("feature_id")
            if feature_id is not None and item_feature_id not in (None, feature_id):
                continue
            planning_refs.extend(_collect_update_refs(item))

    normalized_planning_refs = set(_normalize_ref_tokens(planning_refs))
    doc_refs = sorted([ref for ref in normalized_planning_refs if ref.startswith("doc:")])

    if not _planning_gate_enabled(data):
        return {
            "ok": True,
            "status": "ready",
            "required": required,
            "missing": [],
            "optional_missing": [],
            "refs": doc_refs,
            "message": PLANNING_MESSAGE_KEYS["gate_disabled"],
            "schema_version": PLANNING_SCHEMA_VERSION,
        }

    missing = [name for name in required if f"planning:{name}" not in normalized_planning_refs]
    optional_missing = [
        name for name in optional if f"planning:{name}" not in normalized_planning_refs
    ]

    if missing:
        status = "missing"
        message = PLANNING_MESSAGE_KEYS["missing"]
    elif optional_missing:
        status = "warn"
        message = PLANNING_MESSAGE_KEYS["optional_missing"]
    else:
        status = "ready"
        message = PLANNING_MESSAGE_KEYS["ready"]

    return {
        "ok": True,
        "status": status,
        "required": required,
        "missing": missing,
        "optional_missing": optional_missing,
        "refs": doc_refs,
        "message": message,
        "schema_version": PLANNING_SCHEMA_VERSION,
    }


# ---------------------------------------------------------------------------
# Self-contained readiness helpers
# ---------------------------------------------------------------------------

def _has_non_empty_list_items(value: Any) -> bool:
    """Return True when value is a list containing at least one non-empty item."""
    return isinstance(value, list) and any(str(item).strip() for item in value)


def validate_feature_readiness(feature: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate feature contract readiness using blocking and warning checks.

    Contract:
      {
        "valid": bool,
        "errors": [str],      # blocking checks
        "warnings": [str],    # advisory checks
      }
    """
    blockers: List[str] = []
    warnings: List[str] = []

    if not _has_non_empty_list_items(feature.get("requirement_ids")):
        blockers.append("requirement_ids cannot be empty")

    change_spec = feature.get("change_spec")
    if not isinstance(change_spec, dict):
        change_spec = {}

    why = str(change_spec.get("why") or "").strip()
    if not why:
        blockers.append("change_spec.why cannot be empty")
    elif len(why) <= 10:
        warnings.append("change_spec.why should be longer than 10 characters")

    if not _has_non_empty_list_items(feature.get("acceptance_scenarios")):
        blockers.append("acceptance_scenarios cannot be empty")

    if not _has_non_empty_list_items(feature.get("test_steps")):
        warnings.append("test_steps is empty")

    name = str(feature.get("name") or "").strip()
    if len(name) < 5:
        warnings.append("name should be at least 5 characters")

    # Keep readiness warning semantics aligned with done gate contract checks.
    sprint_contract = feature.get("sprint_contract")
    missing: List[str] = []
    if not isinstance(sprint_contract, dict):
        missing = ["scope", "done_criteria", "test_plan"]
    else:
        if not str(sprint_contract.get("scope") or "").strip():
            missing.append("scope")
        done_criteria = sprint_contract.get("done_criteria")
        if not _has_non_empty_list_items(done_criteria):
            missing.append("done_criteria")
        test_plan = sprint_contract.get("test_plan")
        if not _has_non_empty_list_items(test_plan):
            missing.append("test_plan")
    if missing:
        warnings.append(
            "sprint_contract incomplete: "
            + ", ".join(missing)
            + " are empty or missing. Fill before /prog done."
        )

    return {
        "valid": len(blockers) == 0,
        "errors": blockers,
        "warnings": warnings,
    }


def print_readiness_warnings(report: Dict[str, Any]) -> None:
    """Print non-blocking readiness warnings."""
    warnings = report.get("warnings", [])
    if not warnings:
        return

    print("Warnings (non-blocking):")
    for warning in warnings:
        print(f"  - {warning}")


def _build_readiness_fix_commands(feature_id: int, errors: List[str]) -> List[str]:
    """Build deterministic one-line fix commands from blocking errors."""
    commands: List[str] = []
    seen: Set[str] = set()
    default_req = f"REQ-{feature_id:03d}"

    def _add(command: str) -> None:
        if command in seen:
            return
        seen.add(command)
        commands.append(command)

    for error in errors:
        if "requirement_ids" in error:
            _add(
                f"{PROG_CLI_COMMAND} fix-readiness {feature_id} --add-requirement {default_req}"
            )
        elif "change_spec.why" in error:
            _add(
                f"{PROG_CLI_COMMAND} fix-readiness {feature_id} --set-why \"Detailed explanation...\""
            )
        elif "acceptance_scenarios" in error:
            _add(
                f"{PROG_CLI_COMMAND} fix-readiness {feature_id} --add-acceptance \"Scenario: ...\""
            )

    return commands


def print_readiness_error(feature: Dict[str, Any], report: Dict[str, Any]) -> None:
    """Print readiness blockers and actionable fix commands."""
    feature_id = feature.get("id", "?")
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])

    print(f"Feature #{feature_id} cannot start: readiness check failed")
    print("")
    print("Blockers:")
    for error in errors:
        print(f"  - {error}")

    if warnings:
        print("")
        print_readiness_warnings(report)

    fix_commands = _build_readiness_fix_commands(
        feature_id if isinstance(feature_id, int) else 0,
        [str(item) for item in errors],
    )
    if fix_commands:
        print("")
        print("Suggested fixes:")
        for command in fix_commands:
            print(f"  {command}")

    print("")
    print(f"Retry: plugins/progress-tracker/prog set-current {feature_id}")


# ---------------------------------------------------------------------------
# Command functions (require injected services)
# ---------------------------------------------------------------------------

def validate_readiness_command(
    feature_id: int,
    *,
    services: ReadinessValidatorServices,
) -> int:
    """Read-only readiness validation. Returns 0 when no blockers, otherwise 1."""
    data = services.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return 1

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return 1

    report = validate_feature_readiness(feature)
    if report["valid"]:
        print(f"Feature #{feature_id} readiness check passed")
        if report["warnings"]:
            print("")
            print_readiness_warnings(report)
        return 0

    print_readiness_error(feature, report)
    return 1


def validate_planning_command(
    feature_id: int,
    *,
    services: ReadinessValidatorServices,
    output_json: bool = False,
) -> bool:
    """Validate preflight planning artifacts from structured updates.

    Returns:
        True (exit code 0) for ready/warn status
        False (exit code 1) for missing status
    """
    data = services.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])
    target_feature = next((f for f in features if f.get("id") == feature_id), None)
    if target_feature is None:
        print(f"Feature ID {feature_id} not found")
        return False

    report = _evaluate_planning_readiness(data, feature_id=feature_id)
    if output_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(
            f"Planning preflight for feature #{feature_id}: {report['status']} - "
            f"{report['message']}"
        )
        if report.get("refs"):
            print("Refs:")
            for ref in report["refs"]:
                print(f"- {ref}")

    # Return exit code: 0 (True) for ready/warn, 1 (False) for missing
    status = report.get("status", "ready")
    return status != "missing"


def fix_readiness_command(
    feature_id: int,
    *,
    services: ReadinessValidatorServices,
    add_requirement: Optional[str] = None,
    set_why: Optional[str] = None,
    add_acceptance: Optional[str] = None,
) -> bool:
    """
    Apply structured contract fixes for readiness blockers.

    Returns False for invalid input/feature-not-found; True for successful (including idempotent) runs.
    """
    data = services.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    feature = next((f for f in data.get("features", []) if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    operations = [add_requirement, set_why, add_acceptance]
    if not any(item is not None for item in operations):
        print(
            "Error: At least one operation required "
            "(--add-requirement / --set-why / --add-acceptance)"
        )
        return False

    changed = False

    if add_requirement is not None:
        requirement = str(add_requirement).strip()
        if not requirement:
            print("Error: --add-requirement cannot be empty")
            return False
        if not requirement.startswith("REQ-"):
            print(f"Warning: '{requirement}' does not match REQ- format")

        requirement_ids = feature.get("requirement_ids")
        if not isinstance(requirement_ids, list):
            requirement_ids = []
            feature["requirement_ids"] = requirement_ids
        if requirement not in requirement_ids:
            requirement_ids.append(requirement)
            changed = True

    if set_why is not None:
        why = str(set_why).strip()
        if not why:
            print("Error: --set-why cannot be empty")
            return False
        change_spec = feature.get("change_spec")
        if not isinstance(change_spec, dict):
            change_spec = {}
            feature["change_spec"] = change_spec
        if change_spec.get("why") != why:
            change_spec["why"] = why
            changed = True

    if add_acceptance is not None:
        acceptance = str(add_acceptance).strip()
        if not acceptance:
            print("Error: --add-acceptance cannot be empty")
            return False
        acceptance_scenarios = feature.get("acceptance_scenarios")
        if not isinstance(acceptance_scenarios, list):
            acceptance_scenarios = []
            feature["acceptance_scenarios"] = acceptance_scenarios
        if acceptance not in acceptance_scenarios:
            acceptance_scenarios.append(acceptance)
            changed = True

    if changed:
        _normalize_feature_contract(feature)
        services.save_progress_json_fn(data)
        services.save_progress_md_fn(services.generate_progress_md_fn(data))
        print(f"Feature #{feature_id} updated")
    else:
        print(f"No changes needed for feature #{feature_id}")

    report = validate_feature_readiness(feature)
    if report["valid"]:
        print("All blockers resolved. Ready to start.")
    else:
        print("Remaining blockers:")
        for error in report["errors"]:
            print(f"  - {error}")

    if report["warnings"]:
        print("")
        print_readiness_warnings(report)

    return True
