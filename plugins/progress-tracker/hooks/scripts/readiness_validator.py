"""
readiness_validator.py — Feature readiness validation and remediation commands.

Extracted from progress_manager.py (F21 Round 2 modularisation).

This module owns the readiness validation command cluster:
- _has_non_empty_list_items
- validate_feature_readiness
- print_readiness_warnings
- _build_readiness_fix_commands
- print_readiness_error
- validate_readiness_command
- validate_planning_command
- fix_readiness_command

All progress_manager-owned helpers that cannot be imported directly are
injected via a ReadinessValidatorServices dataclass. Submodule helpers
(_normalize_feature_contract) are imported directly from state_io.

This module must NOT import progress_manager (no reverse dependency).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

from state_io import _normalize_feature_contract


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
    evaluate_planning_readiness_fn: Callable[..., Dict[str, Any]]


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
                f"plugins/progress-tracker/prog fix-readiness {feature_id} --add-requirement {default_req}"
            )
        elif "change_spec.why" in error:
            _add(
                f"plugins/progress-tracker/prog fix-readiness {feature_id} --set-why \"Detailed explanation...\""
            )
        elif "acceptance_scenarios" in error:
            _add(
                f"plugins/progress-tracker/prog fix-readiness {feature_id} --add-acceptance \"Scenario: ...\""
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

    report = services.evaluate_planning_readiness_fn(data, feature_id=feature_id)
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
