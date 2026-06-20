# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("progress_tracker.doc_generator")

import state_io
from state_io import (
    OWNER_ROLES,
    _atomic_write_text,
    _default_change_spec,
    _default_acceptance_scenarios,
    compare_contexts,
)
import prog_paths
from git_utils import _format_context_summary
from worktree_handler import _is_feature_deferred


def _format_feature_owners(feature: Dict[str, Any]) -> Optional[str]:
    """Format non-empty feature owners as a compact status string."""
    owners = feature.get("owners")
    if not isinstance(owners, dict):
        return None
    populated = []
    for role in OWNER_ROLES:
        value = owners.get(role)
        if isinstance(value, str) and value.strip():
            populated.append(f"{role}={value.strip()}")
    if not populated:
        return None
    return ", ".join(populated)


def _slugify(text: Optional[str], fallback: str = "project") -> str:
    """Create a filesystem-safe slug from free-form text."""
    if not text:
        return fallback
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:48] if slug else fallback


PLAN_PATH_PREFIX = "docs/plans/"
SUPERPOWERS_PLAN_PATH_PREFIX = "docs/superpowers/plans/"
VALID_PLAN_PREFIXES = (PLAN_PATH_PREFIX, SUPERPOWERS_PLAN_PATH_PREFIX)


def validate_plan_path(
    plan_path: Optional[str],
    require_exists: bool = False,
    target_root: Optional[Path] = None,
    *,
    find_project_root_fn: Optional[Callable[[], Path]] = None,
) -> Dict[str, Optional[str]]:
    """
    Validate workflow plan path shape and optional existence.

    Accepted formats:
    - docs/plans/<YYYY-MM-DD-name>.md
    - docs/superpowers/plans/<YYYY-MM-DD-name>.md  (writing-plans skill)
    """
    if plan_path is None:
        return {"valid": True, "normalized_path": None, "error": None}

    normalized = plan_path.strip().replace("\\", "/")
    if normalized == "":
        return {"valid": True, "normalized_path": "", "error": None}

    if Path(normalized).is_absolute():
        return {
            "valid": False,
            "normalized_path": None,
            "error": "plan_path must be relative (absolute paths are not allowed)",
        }

    if not any(normalized.startswith(prefix) for prefix in VALID_PLAN_PREFIXES):
        return {
            "valid": False,
            "normalized_path": None,
            "error": (
                f"plan_path must be under '{PLAN_PATH_PREFIX}' or "
                f"'{SUPERPOWERS_PLAN_PATH_PREFIX}' ending with .md"
            ),
        }

    if not normalized.endswith(".md"):
        return {
            "valid": False,
            "normalized_path": None,
            "error": "plan_path must end with .md",
        }

    if ".." in Path(normalized).parts:
        return {
            "valid": False,
            "normalized_path": None,
            "error": "plan_path cannot contain '..' segments",
        }

    if require_exists:
        base_root = (target_root or (find_project_root_fn() if find_project_root_fn else prog_paths.find_project_root())).resolve()
        absolute_path = base_root / normalized
        if not absolute_path.exists():
            # Walk up to git root to find plan files written by writing-plans
            # skill at the repo/worktree root level (e.g. docs/superpowers/plans/).
            found = False
            try:
                git_root = prog_paths.resolve_repo_root(base_root).resolve()
            except Exception:
                git_root = None
            cursor = base_root
            while True:
                cursor = cursor.parent
                if (cursor / normalized).exists():
                    found = True
                    break
                # Stop after checking git root (or filesystem root).
                if (git_root is not None and cursor == git_root) or cursor == cursor.parent:
                    break
            if not found:
                return {
                    "valid": False,
                    "normalized_path": None,
                    "error": f"plan_path does not exist: {normalized}",
                }

    return {"valid": True, "normalized_path": normalized, "error": None}


def validate_plan_document(
    plan_path: str,
    target_root: Optional[Path] = None,
    *,
    find_project_root_fn: Optional[Callable[[], Path]] = None,
    validate_plan_path_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Validate minimum plan structure for feature execution.

    Supports two compatible formats:

    1) Progress-tracker strict template:
       - Tasks
       - Acceptance mapping
       - Risks

    2) Superpowers writing-plans template:
       - Goal (header field)
       - Architecture (header field)
       - Tasks

    In format (2), missing strict sections are treated as warnings.
    """
    val_fn = validate_plan_path_fn or validate_plan_path
    path_validation = val_fn(
        plan_path,
        require_exists=True,
        target_root=target_root,
        find_project_root_fn=find_project_root_fn,
    )
    if not path_validation["valid"]:
        return {
            "valid": False,
            "errors": [path_validation["error"]],
            "missing_sections": [],
            "warnings": [],
            "profile": "invalid",
        }

    base_root = target_root or (find_project_root_fn() if find_project_root_fn else prog_paths.find_project_root())
    absolute_path = base_root / path_validation["normalized_path"]
    try:
        content = absolute_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "valid": False,
            "errors": [f"Unable to read plan: {exc}"],
            "missing_sections": [],
            "warnings": [],
            "profile": "invalid",
        }

    checks = {
        # Match both "## Tasks" (list style) and "## Task 1: name" (Superpowers individual tasks)
        "tasks": re.search(r"^##+\s+Tasks?\b", content, flags=re.IGNORECASE | re.MULTILINE),
        "acceptance_mapping": re.search(
            r"^##+\s+Acceptance(\s+Criteria)?(\s+Mapping)?\b",
            content,
            flags=re.IGNORECASE | re.MULTILINE,
        ),
        "risks": re.search(r"^##+\s+Risks?\b", content, flags=re.IGNORECASE | re.MULTILINE),
    }
    superpowers_checks = {
        # Accept English and Chinese field labels (writing-plans generates Chinese when prompted in Chinese)
        "goal": re.search(r"^\*\*(Goal|目标):\*\*\s+.+", content, flags=re.MULTILINE),
        "architecture": re.search(r"^\*\*(Architecture|架构):\*\*\s+.+", content, flags=re.MULTILINE),
    }

    missing_sections = [name for name, found in checks.items() if not found]

    # Tasks are mandatory for all plan formats.
    if "tasks" in missing_sections:
        return {
            "valid": False,
            "errors": ["Missing required plan sections: tasks"],
            "missing_sections": missing_sections,
            "warnings": [],
            "profile": "invalid",
        }

    # Strict format fully satisfied.
    if not missing_sections:
        return {
            "valid": True,
            "errors": [],
            "missing_sections": [],
            "warnings": [],
            "profile": "strict",
        }

    # Superpowers-compatible format.
    if superpowers_checks["goal"] and superpowers_checks["architecture"]:
        advisory_missing = [s for s in missing_sections if s in ("acceptance_mapping", "risks")]
        warnings = []
        if advisory_missing:
            warnings.append(
                "Superpowers plan accepted; recommended sections missing: "
                f"{', '.join(advisory_missing)}"
            )
        return {
            "valid": True,
            "errors": [],
            "missing_sections": advisory_missing,
            "warnings": warnings,
            "profile": "superpowers",
        }

    return {
        "valid": False,
        "errors": [f"Missing required plan sections: {', '.join(missing_sections)}"],
        "missing_sections": missing_sections,
        "warnings": [],
        "profile": "invalid",
    }


def generate_direct_tdd_note(
    *,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    find_project_root_fn: Callable[[], Path],
    validate_plan_document_fn: Callable[[str], Dict[str, Any]],
    set_workflow_state_fn: Callable[..., bool],
    validate_plan_path_fn: Callable[..., Dict[str, Any]],
) -> bool:
    """Generate a lightweight execution note for direct_tdd features.

    Creates a strict-profile plan document from feature metadata so that
    validate-plan always finds a valid plan_path. File writes are idempotent
    (existing valid notes are preserved via state-path and deterministic-path
    fallback), but workflow_state convergence always runs.

    Returns:
        bool: True on success, False on error.
    """
    data = load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    current_id = data.get("current_feature_id")
    if current_id is None:
        print("Error: No feature currently in progress")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == current_id), None)
    if feature is None:
        print(f"Error: Feature {current_id} not found")
        return False

    def _normalize_text_list(value: Any, fallback: List[str]) -> List[str]:
        """Normalize metadata fields to a non-empty list of strings."""
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            return normalized or fallback
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return [stripped]
        return fallback

    feature_name = str(feature.get("name") or "Unnamed feature").strip()
    change_spec = feature.get("change_spec")
    if not isinstance(change_spec, dict) or not change_spec:
        change_spec = _default_change_spec(feature)

    why = str(change_spec.get("why") or f"Deliver {feature_name}.")
    in_scope = _normalize_text_list(change_spec.get("in_scope"), [feature_name])
    out_of_scope = _normalize_text_list(
        change_spec.get("out_of_scope"),
        ["Unrelated refactors and behavior changes outside this feature."],
    )
    risks = _normalize_text_list(
        change_spec.get("risks"),
        ["Potential regression in adjacent workflows"],
    )

    test_steps = feature.get("test_steps")
    if isinstance(test_steps, list) and test_steps:
        task_lines = [
            f"- [ ] {str(step).strip()}" for step in test_steps if str(step).strip()
        ]
    else:
        task_lines = [f"- [ ] Implement {feature_name}"]
    if not task_lines:
        task_lines = [f"- [ ] Implement {feature_name}"]

    acceptance = feature.get("acceptance_scenarios")
    if not isinstance(acceptance, list) or not acceptance:
        acceptance = _default_acceptance_scenarios(feature)
    acceptance_lines = [f"- {str(item).strip()}" for item in acceptance if str(item).strip()]
    if not acceptance_lines:
        acceptance_lines = [
            f"- Scenario: {feature_name} baseline behavior works as expected."
        ]

    risk_lines = [f"- {str(risk).strip()}" for risk in risks if str(risk).strip()]
    if not risk_lines:
        risk_lines = ["- Potential regression in adjacent workflows"]

    in_scope_text = ", ".join(in_scope)
    out_of_scope_text = ", ".join(out_of_scope)

    base_root = find_project_root_fn()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slugify(feature_name)
    plan_rel = f"docs/plans/{today}-feature-{current_id}-{slug}.md"

    workflow_state_raw = data.get("workflow_state")
    needs_workflow_state_repair = (
        "workflow_state" in data and not isinstance(workflow_state_raw, dict)
    )
    workflow_state = workflow_state_raw if isinstance(workflow_state_raw, dict) else {}
    existing_plan_path = workflow_state.get("plan_path")
    if isinstance(existing_plan_path, str):
        existing_plan_path = existing_plan_path.strip() or None
    else:
        existing_plan_path = None

    candidate_paths: List[str] = []
    if existing_plan_path:
        candidate_paths.append(existing_plan_path)
    if plan_rel not in candidate_paths:
        candidate_paths.append(plan_rel)

    plans_dir = base_root / "docs" / "plans"
    if plans_dir.exists():
        pattern = f"*-feature-{current_id}-{slug}.md"
        for matched in sorted(plans_dir.glob(pattern), reverse=True):
            rel = matched.relative_to(base_root).as_posix()
            if rel not in candidate_paths:
                candidate_paths.append(rel)

    need_write = True
    for candidate in candidate_paths:
        absolute_candidate = base_root / candidate
        if not absolute_candidate.exists():
            continue
        validation = validate_plan_document_fn(candidate)
        if validation["valid"]:
            need_write = False
            plan_rel = candidate
            print(f"Execution note already exists: {plan_rel} (state converged)")
            break
        print(f"Warning: existing note invalid ({candidate}), regenerating")

    if need_write:
        note_content = (
            f"# {feature_name} -- direct_tdd execution note\n"
            f"\n"
            f"**Goal:** {why}\n"
            f"\n"
            f"**Architecture:** Direct TDD implementation of {in_scope_text}. "
            f"Out of scope: {out_of_scope_text}.\n"
            f"\n"
            f"---\n"
            f"\n"
            f"## Tasks\n"
            f"\n"
            + "\n".join(task_lines)
            + "\n"
            f"\n"
            f"## Acceptance Mapping\n"
            f"\n"
            + "\n".join(acceptance_lines)
            + "\n"
            f"\n"
            f"## Risks\n"
            f"\n"
            + "\n".join(risk_lines)
            + "\n"
        )
        absolute_path = base_root / plan_rel
        _atomic_write_text(absolute_path, note_content)
        print(f"Generated direct_tdd execution note: {plan_rel}")

    # set_workflow_state() assumes persisted workflow_state has dict semantics.
    # Missing workflow_state is legal and is initialized by set_workflow_state().
    if needs_workflow_state_repair:
        data["workflow_state"] = {}
        save_progress_json_fn(data)

    result = set_workflow_state_fn(
        phase="execution",
        plan_path=plan_rel,
        next_action="direct_tdd",
    )
    if not result:
        print("Error: Failed to converge workflow_state")
        return False

    return True


def generate_progress_md(data: Dict[str, Any]) -> str:
    """Deprecated: progress.md generation is disabled."""
    return ""

    project_name = data.get("project_name", "Unknown Project")
    features = data.get("features", [])
    bugs = data.get("bugs", [])
    current_id = data.get("current_feature_id")
    created_at = data.get("created_at", "")
    workflow_state = data.get("workflow_state", {})
    if not isinstance(workflow_state, dict):
        workflow_state = {}
    runtime_context = data.get("runtime_context")

    md_lines = [
        f"# Project Progress: {project_name}",
        "",
        f"**Created**: {created_at}",
        "",
    ]

    completed = [f for f in features if f.get("completed", False)]
    in_progress = [f for f in features if f.get("id") == current_id]
    deferred = [
        f
        for f in features
        if not f.get("completed", False)
        and f.get("id") != current_id
        and _is_feature_deferred(f)
    ]
    pending = [
        f
        for f in features
        if not f.get("completed", False) and f.get("id") != current_id
        and not _is_feature_deferred(f)
    ]

    total = len(features)
    completed_count = len(completed)

    md_lines.append(f"**Status**: {completed_count}/{total} completed")
    md_lines.append("")

    if completed:
        md_lines.append("## Completed")
        for f in completed:
            md_lines.append(f"- [x] {f.get('name', 'Unknown')}")
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
        md_lines.append("")

    if in_progress:
        md_lines.append("## In Progress")
        for f in in_progress:
            md_lines.append(f"- [ ] {f.get('name', 'Unknown')}")
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
            test_steps = f.get("test_steps", [])
            if test_steps:
                md_lines.append("  **Test steps**:")
                for step in test_steps:
                    md_lines.append(f"  - {step}")
        md_lines.append("")

    if pending:
        md_lines.append("## Pending")
        for f in pending:
            md_lines.append(f"- [ ] {f.get('name', 'Unknown')}")
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
        md_lines.append("")

    if deferred:
        md_lines.append("## Deferred")
        for f in deferred:
            reason = f.get("defer_reason") or "No reason provided"
            group = f.get("defer_group")
            line = f"- [~] {f.get('name', 'Unknown')} — {reason}"
            if group:
                line += f" (group: {group})"
            md_lines.append(line)
            owner_summary = _format_feature_owners(f)
            if owner_summary:
                md_lines.append(f"  Owners: {owner_summary}")
        md_lines.append("")

    if current_id is not None and workflow_state:
        phase = workflow_state.get("phase", "unknown")
        current_task = workflow_state.get("current_task")
        total_tasks = workflow_state.get("total_tasks")
        next_action = workflow_state.get("next_action")
        execution_context = workflow_state.get("execution_context")
        context_hint = compare_contexts(execution_context, runtime_context)

        md_lines.append("## Workflow Context")
        md_lines.append(f"- Phase: {phase}")

        if current_task is not None or total_tasks is not None:
            task_progress = f"{current_task if current_task is not None else '?'}"
            if total_tasks is not None:
                task_progress += f"/{total_tasks}"
            md_lines.append(f"- Task progress: {task_progress}")

        if next_action:
            md_lines.append(f"- Next action: {next_action}")

        if execution_context:
            md_lines.append(f"- Execution context: {_format_context_summary(execution_context)}")
        if runtime_context:
            md_lines.append(f"- Current session context: {_format_context_summary(runtime_context)}")

        if context_hint.get("status") in {"mismatch", "path_mismatch", "branch_mismatch"}:
            md_lines.append(
                "- Context mismatch: "
                f"{context_hint.get('message')} "
                f"(expected {context_hint.get('expected_branch') or '?'} @ "
                f"{context_hint.get('expected_worktree_path') or '?'})"
            )
        md_lines.append("")

    updates = data.get("updates", [])
    if updates:
        md_lines.append("## Recent Updates")
        for update in updates[-5:]:
            line = (
                f"- [{update.get('id', 'UPD-???')}] "
                f"{update.get('category', 'status')}: {update.get('summary', '')}"
            )
            if update.get("feature_id") is not None:
                line += f" (feature:{update['feature_id']})"
            if update.get("role") and update.get("owner"):
                line += f" [{update['role']}={update['owner']}]"
            md_lines.append(line)
            if update.get("next_action"):
                md_lines.append(f"  Next: {update['next_action']}")
        md_lines.append("")

    # Add bugs section if any exist
    if bugs:
        status_icons = {
            "pending_investigation": "🔴",
            "investigating": "🟡",
            "confirmed": "🟢",
            "fixing": "🔧",
            "fixed": "✅",
            "false_positive": "❌"
        }

        # Group bugs by status
        pending_bugs = [b for b in bugs if b.get("status") in ["pending_investigation", "investigating", "confirmed", "fixing"]]
        fixed_bugs = [b for b in bugs if b.get("status") == "fixed"]

        # Group pending bugs by priority
        high_pending = [b for b in pending_bugs if b.get("priority") == "high"]
        medium_pending = [b for b in pending_bugs if b.get("priority") == "medium"]
        low_pending = [b for b in pending_bugs if b.get("priority") == "low"]

        if pending_bugs:
            md_lines.append("## Bug Backlog")

            if high_pending:
                md_lines.append("### High Priority (🔴)")
                for bug in high_pending:
                    icon = status_icons.get(bug.get("status"), "❓")
                    category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                    md_lines.append(
                        f"- [{icon}] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                    )
                    scheduled = bug.get("scheduled_position", {})
                    if scheduled:
                        reason = scheduled.get("reason", "")
                        md_lines.append(f"  Status: {bug.get('status')} | 📍 {reason}")
                md_lines.append("")

            if medium_pending:
                md_lines.append("### Medium Priority (🟡)")
                for bug in medium_pending:
                    icon = status_icons.get(bug.get("status"), "❓")
                    category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                    md_lines.append(
                        f"- [{icon}] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                    )
                    if bug.get("root_cause"):
                        md_lines.append(f"  Root cause: {bug['root_cause']}")
                    scheduled = bug.get("scheduled_position", {})
                    if scheduled:
                        reason = scheduled.get("reason", "")
                        md_lines.append(f"  📍 {reason}")
                md_lines.append("")

            if low_pending:
                md_lines.append("### Low Priority (🟢)")
                for bug in low_pending:
                    icon = status_icons.get(bug.get("status"), "❓")
                    category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                    md_lines.append(
                        f"- [{icon}] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                    )
                md_lines.append("")

        if fixed_bugs:
            md_lines.append("### Fixed (✅)")
            for bug in fixed_bugs:
                category_prefix = "[DEBT] " if bug.get("category") == "technical_debt" else ""
                md_lines.append(
                    f"- [x] [{bug.get('id')}] {category_prefix}{bug.get('description', 'No description')}"
                )
                if bug.get("fix_summary"):
                    md_lines.append(f"  Fix: {bug['fix_summary']}")
            md_lines.append("")

    return "\n".join(md_lines)


def archive_feature_docs(
    feature_id: int,
    feature_name: Optional[str] = None,
    *,
    find_project_root_fn: Callable[[], Path],
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    is_immutable_protected_fn: Callable[[Path, Path], bool],
) -> Dict[str, Any]:
    """
    Archive testing and plan documents for a completed feature.

    Moves documents from:
    - docs/plans/ (Superpowers writing-plans standard location for plan files)
    - docs/testing/ (bug fix reports and test documentation)

    To:
    - docs/archive/plans/
    - docs/archive/testing/

    Supports naming patterns:
    - Primary: Reads plan_path from feature object (preserved before completion)
    - Fallback: feature-{feature_id}-*.md (legacy pattern)
    - Fallback: bug-*-fix-report.md (testing reports)

    Args:
        feature_id: The ID of the completed feature
        feature_name: Optional feature name for logging

    Returns:
        Dict with archive results including success status, files moved, and any errors
    """
    result = {
        "success": True,
        "archived_files": [],
        "skipped_files": [],
        "errors": []
    }

    try:
        project_root = find_project_root_fn()

        # Plans live at docs/plans/ (Superpowers standard)
        # Testing reports live at docs/testing/
        plans_src = project_root / "docs" / "plans"
        testing_src = project_root / "docs" / "testing"
        plans_archive = project_root / "docs" / "archive" / "plans"
        testing_archive = project_root / "docs" / "archive" / "testing"

        # Create archive directories if they don't exist
        testing_archive.mkdir(parents=True, exist_ok=True)
        plans_archive.mkdir(parents=True, exist_ok=True)

        # Try to get plan_path from feature object (preserved before workflow_state clear)
        data = load_progress_json_fn()
        feature = next((f for f in data.get("features", []) if f.get("id") == feature_id), None) if data else None
        plan_path_from_feature = feature.get("plan_path") if feature else None

        # Archive plan file if plan_path is available
        if plan_path_from_feature:
            try:
                plan_file = project_root / plan_path_from_feature
                if plan_file.exists():
                    # Guard: never archive immutable protected files
                    if is_immutable_protected_fn(plan_file, project_root):
                        logger.warning(
                            "Skipping immutable protected file from archival: %s",
                            plan_path_from_feature,
                        )
                        result["skipped_files"].append(f"Protected: {plan_path_from_feature}")
                    else:
                        dst_file = plans_archive / plan_file.name

                        # Handle filename conflicts
                        if dst_file.exists():
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            stem = plan_file.stem
                            suffix = plan_file.suffix
                            new_name = f"{stem}_{timestamp}{suffix}"
                            dst_file = plans_archive / new_name

                        shutil.move(str(plan_file), str(dst_file))
                        result["archived_files"].append({
                            "from": plan_path_from_feature,
                            "to": str(dst_file.relative_to(project_root))
                        })
                        logger.info(f"Archived plan: {plan_path_from_feature} -> {dst_file.relative_to(project_root)}")
            except Exception as e:
                error_msg = f"Failed to archive plan {plan_path_from_feature}: {e}"
                result["errors"].append(error_msg)
                logger.warning(error_msg)

        # Collect all patterns to try for this feature (fallback)
        patterns = [
            # Legacy pattern: feature-{feature_id}-*.md
            (testing_src, testing_archive, f"feature-{feature_id}-*.md"),
            (plans_src, plans_archive, f"feature-{feature_id}-*.md"),
            # Modern pattern: bug-NNN-*.md for testing reports
            (testing_src, testing_archive, f"bug-*-fix-report.md"),
        ]

        for src_dir, dst_dir, pattern in patterns:
            if not src_dir.exists():
                result["skipped_files"].append(f"Source directory not found: {src_dir}")
                continue

            # Find matching files
            matching_files = list(src_dir.glob(pattern))

            if not matching_files:
                # Debug log but don't report to user (too verbose)
                logger.debug(f"No files found matching {pattern} in {src_dir}")
                continue

            # Move each matching file
            for src_file in matching_files:
                # Guard: never archive immutable protected files
                if is_immutable_protected_fn(src_file, project_root):
                    logger.warning(
                        "Skipping immutable protected file from archival: %s",
                        src_file,
                    )
                    result["skipped_files"].append(f"Protected: {src_file.name}")
                    continue
                try:
                    dst_file = dst_dir / src_file.name

                    # Handle filename conflicts by adding timestamp
                    if dst_file.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        stem = src_file.stem
                        suffix = src_file.suffix
                        new_name = f"{stem}_{timestamp}{suffix}"
                        dst_file = dst_dir / new_name

                    # Move the file
                    shutil.move(str(src_file), str(dst_file))
                    result["archived_files"].append({
                        "from": str(src_file.relative_to(project_root)),
                        "to": str(dst_file.relative_to(project_root))
                    })
                    logger.info(f"Archived: {src_file.name} -> {dst_file.relative_to(project_root)}")

                except Exception as e:
                    error_msg = f"Failed to move {src_file.name}: {e}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg)

        # Log summary
        if result["archived_files"]:
            logger.info(f"Archived {len(result['archived_files'])} file(s) for feature {feature_id}")
            for file_info in result["archived_files"]:
                print(f"  Archived: {file_info['from']} -> {file_info['to']}")

        if result["errors"]:
            result["success"] = False
            for error in result["errors"]:
                logger.warning(error)

    except Exception as e:
        result["success"] = False
        error_msg = f"Archive operation failed: {e}"
        result["errors"].append(error_msg)
        logger.error(error_msg)

    return result
