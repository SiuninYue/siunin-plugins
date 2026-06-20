"""Work-item mutation commands extracted from ``progress_manager.py``.

This module owns backlog and intake mutations while keeping
``progress_manager.py`` as a thin facade. It imports only leaf modules
directly and receives progress_manager-owned side effects via
``WorkItemCommandsServices``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from contract_importer import ContractImporter, ContractImportError
from progress_prompt_builders import _is_deferred as _is_feature_deferred
from state_io import (
    OWNER_ROLES,
    _clear_feature_defer_state,
    _default_owners,
    _normalize_feature_contract,
    _normalize_feature_owners,
    _normalize_optional_string,
    _normalize_ref_tokens,
)


WORK_ITEM_TAXONOMY = frozenset(
    ["epic", "feature", "task", "bug", "spike", "risk", "decision", "update"]
)
WORKFLOW_PROFILE_VALUES = frozenset(
    ["quick_task", "standard_task", "feature_delivery", "hotfix"]
)
WORKFLOW_PROFILE_DEFAULT = "standard_task"
UPDATE_CATEGORIES = (
    "status",
    "decision",
    "risk",
    "handoff",
    "assignment",
    "meeting",
)
UPDATE_SOURCES = (
    "prog_update",
    "spm_meeting",
    "spm_assign",
    "spm_planning",
    "manual",
)
UPDATE_REFS_INLINE_LIMIT = 12
_SMART_INTAKE_PRIORITY_MAP = {"P0": "high", "P1": "medium", "P2": "low"}


@dataclass
class WorkItemCommandsServices:
    """Injected callbacks used by work-item mutation commands."""

    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]]
    save_progress_json_fn: Callable[[Dict[str, Any]], None]
    generate_progress_md_fn: Callable[[Dict[str, Any]], str]
    save_progress_md_fn: Callable[[str], None]
    update_runtime_context_fn: Callable[[Dict[str, Any], str], bool]
    notify_parent_sync_fn: Callable[[str], None]
    add_bug_internal_fn: Callable[..., Tuple[bool, Optional[str]]]
    find_project_root_fn: Callable[[], Path]


def _iso_now() -> str:
    """Return current local timestamp with trailing Z for compatibility."""
    return datetime.now().isoformat() + "Z"


def _persist_progress(data: Dict[str, Any], svc: WorkItemCommandsServices) -> None:
    svc.save_progress_json_fn(data)
    svc.save_progress_md_fn("")


def _next_update_id(updates: List[Dict[str, Any]]) -> str:
    """Generate the next UPD-XXX identifier."""
    max_num = 0
    for item in updates:
        update_id = str(item.get("id", ""))
        match = re.match(r"^UPD-(\d+)$", update_id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"UPD-{max_num + 1:03d}"


def _collect_auto_update_refs(feature: Dict[str, Any]) -> List[str]:
    """Collect deterministic auto refs from a feature contract payload."""
    refs: List[str] = []
    for req_id in feature.get("requirement_ids", []):
        if isinstance(req_id, str) and req_id.strip():
            refs.append(f"req:{req_id.strip()}")

    change_spec = feature.get("change_spec")
    if isinstance(change_spec, dict):
        change_id = change_spec.get("change_id")
        if isinstance(change_id, str) and change_id.strip():
            refs.append(f"change:{change_id.strip()}")

    normalized = _normalize_ref_tokens(refs)
    normalized.sort()
    return normalized


def _compact_update_refs(refs: List[str]) -> Tuple[List[str], List[str]]:
    """Split refs into inline and overflow buckets without dropping data."""
    if len(refs) <= UPDATE_REFS_INLINE_LIMIT:
        return refs, []
    return refs[:UPDATE_REFS_INLINE_LIMIT], refs[UPDATE_REFS_INLINE_LIMIT:]


def _apply_imported_feature_contract(feature: Dict[str, Any], contract: Dict[str, Any]) -> None:
    """Apply imported contract payload onto a feature record."""
    feature["requirement_ids"] = contract["requirement_ids"]
    feature["change_spec"] = contract["change_spec"]
    feature["acceptance_scenarios"] = contract["acceptance_scenarios"]
    _normalize_feature_contract(feature)


def _import_contract_for_feature(
    feature_id: int,
    svc: WorkItemCommandsServices,
) -> Optional[Dict[str, Any]]:
    importer = ContractImporter(svc.find_project_root_fn())
    return importer.import_for_feature(feature_id)


def _push_bug_to_routing_queue(data: Dict[str, Any], bug_id: str, priority: str) -> None:
    """Insert bug_id into routing_queue at the position matching its priority tier."""
    queue = data.setdefault("routing_queue", [])
    if not isinstance(queue, list):
        queue = []
        data["routing_queue"] = queue

    if bug_id in queue:
        return

    priority_to_weight = {"high": 0.0, "medium": 1.0, "low": 2.0}
    new_weight = priority_to_weight.get(priority, 1.0)

    bug_priority_map: Dict[str, str] = {}
    for bug in data.get("bugs") or []:
        if isinstance(bug, dict):
            bug_item_id = bug.get("id")
            bug_priority = bug.get("priority")
            if isinstance(bug_item_id, str) and isinstance(bug_priority, str):
                bug_priority_map[bug_item_id] = bug_priority

    def _entry_weight(entry: str) -> float:
        if isinstance(entry, str) and entry.startswith("BUG-"):
            existing_priority = bug_priority_map.get(entry, "medium")
            return priority_to_weight.get(existing_priority, 1.0)
        return 1.5

    insert_idx = len(queue)
    for idx, entry in enumerate(queue):
        if _entry_weight(entry) >= new_weight:
            insert_idx = idx
            break

    queue.insert(insert_idx, bug_id)


def add_update_command(
    category: str,
    summary: str,
    *,
    svc: WorkItemCommandsServices,
    details: Optional[str] = None,
    feature_id: Optional[int] = None,
    bug_id: Optional[str] = None,
    role: Optional[str] = None,
    owner: Optional[str] = None,
    source: str = "prog_update",
    next_action: Optional[str] = None,
    refs: Optional[List[str]] = None,
) -> bool:
    """Append a structured update entry into progress.json."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_category = (category or "").strip().lower()
    if normalized_category not in UPDATE_CATEGORIES:
        print(
            "Error: Invalid category "
            f"'{category}'. Allowed: {', '.join(UPDATE_CATEGORIES)}"
        )
        return False

    normalized_summary = (summary or "").strip()
    if not normalized_summary:
        print("Error: summary cannot be empty")
        return False

    normalized_role = None
    if role:
        normalized_role = role.strip().lower()
        if normalized_role not in OWNER_ROLES:
            print(f"Error: Invalid role '{role}'. Allowed: {', '.join(OWNER_ROLES)}")
            return False

    normalized_owner = owner.strip() if isinstance(owner, str) else owner
    if normalized_owner and not normalized_role:
        print("Error: owner requires role")
        return False

    normalized_source = (source or "").strip().lower()
    if normalized_source not in UPDATE_SOURCES:
        print(
            "Error: Invalid source "
            f"'{source}'. Allowed: {', '.join(UPDATE_SOURCES)}"
        )
        return False

    target_feature: Optional[Dict[str, Any]] = None
    if feature_id is not None:
        features = data.get("features", [])
        target_feature = next((f for f in features if f.get("id") == feature_id), None)
        if target_feature is None:
            print(f"Error: Feature ID {feature_id} not found")
            return False

    normalized_manual_refs = _normalize_ref_tokens(refs)
    selected_refs = normalized_manual_refs
    if feature_id is not None and not normalized_manual_refs and target_feature is not None:
        selected_refs = _collect_auto_update_refs(target_feature)

    refs_inline, refs_overflow = _compact_update_refs(selected_refs)

    updates = data.setdefault("updates", [])
    update_item = {
        "id": _next_update_id(updates),
        "created_at": _iso_now(),
        "category": normalized_category,
        "summary": normalized_summary,
        "details": details.strip() if isinstance(details, str) and details.strip() else None,
        "feature_id": feature_id,
        "bug_id": bug_id.strip() if isinstance(bug_id, str) and bug_id.strip() else None,
        "role": normalized_role,
        "owner": normalized_owner if normalized_owner else None,
        "source": normalized_source,
        "next_action": (
            next_action.strip()
            if isinstance(next_action, str) and next_action.strip()
            else None
        ),
        "refs": refs_inline,
    }
    if refs_overflow:
        update_item["refs_overflow"] = refs_overflow
        update_item["refs_overflow_count"] = len(refs_overflow)
    updates.append(update_item)

    _persist_progress(data, svc)
    print(
        f"Added update {update_item['id']}: "
        f"{update_item['category']} - {update_item['summary']}"
    )
    return True


def list_updates_command(limit: int = 0, *, svc: WorkItemCommandsServices) -> bool:
    """List the latest structured updates. limit=0 means show all."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found")
        return False

    if limit < 0:
        print("Error: --limit must be 0 (all) or a positive integer")
        return False

    updates = data.get("updates", [])
    if not updates:
        print("No updates recorded.")
        return True

    safe_limit = len(updates) if limit == 0 else min(len(updates), limit)
    print(f"Showing {safe_limit} of {len(updates)} update(s):")
    for item in updates[-safe_limit:]:
        line = (
            f"- [{item.get('id', 'UPD-???')}] "
            f"{item.get('category', 'status')}: {item.get('summary', '')}"
        )
        item_source = str(item.get("source") or "").strip()
        if item_source:
            line += f" [source={item_source}]"
        if item.get("feature_id") is not None:
            line += f" (feature:{item['feature_id']})"
        if item.get("role") and item.get("owner"):
            line += f" [{item['role']}={item['owner']}]"
        overflow_count = item.get("refs_overflow_count", 0) or 0
        if overflow_count > 0:
            line += f" [+{overflow_count} refs overflow]"
        print(line)
    return True


def add_retro_command(
    feature_id: int,
    summary: str,
    root_cause: str,
    *,
    svc: WorkItemCommandsServices,
    action_items: Optional[List[str]] = None,
) -> bool:
    """Add a retrospective entry for a feature."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])
    if not any(f.get("id") == feature_id for f in features):
        print(f"Error: Feature ID {feature_id} not found")
        return False

    normalized_summary = (summary or "").strip()
    if not normalized_summary:
        print("Error: summary cannot be empty")
        return False

    normalized_root_cause = (root_cause or "").strip()
    if not normalized_root_cause:
        print("Error: root_cause cannot be empty")
        return False

    retrospectives = data.setdefault("retrospectives", [])
    retro_id = f"RETRO-{feature_id}-{len(retrospectives) + 1:03d}"
    retro_item = {
        "id": retro_id,
        "created_at": _iso_now(),
        "feature_id": feature_id,
        "summary": normalized_summary,
        "root_cause": normalized_root_cause,
        "action_items": [
            item.strip()
            for item in (action_items or [])
            if isinstance(item, str) and item.strip()
        ],
    }

    retrospectives.append(retro_item)
    _persist_progress(data, svc)
    print(f"Added retrospective {retro_id}: {normalized_summary}")
    return True


def set_feature_owner_command(
    feature_id: int,
    role: str,
    owner: Optional[str],
    *,
    svc: WorkItemCommandsServices,
) -> bool:
    """Set feature owner for a specific role."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_role = (role or "").strip().lower()
    if normalized_role not in OWNER_ROLES:
        print(f"Error: Invalid role '{role}'. Allowed: {', '.join(OWNER_ROLES)}")
        return False

    normalized_owner = (owner or "").strip() if owner is not None else ""
    owner_value = (
        None
        if normalized_owner.lower() in {"", "-", "none", "null"}
        else normalized_owner
    )

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    _normalize_feature_owners(feature)
    feature["owners"][normalized_role] = owner_value

    _persist_progress(data, svc)
    assigned = owner_value if owner_value is not None else "None"
    print(f"Set owner: feature {feature_id} {normalized_role} -> {assigned}")
    return True


def add_feature_command(
    name: str,
    test_steps: List[str],
    *,
    svc: WorkItemCommandsServices,
    workflow_profile: Optional[str] = None,
) -> bool:
    """Add a new feature to the tracking."""
    if workflow_profile is None:
        workflow_profile = WORKFLOW_PROFILE_DEFAULT

    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])
    max_id = max([f.get("id", 0) for f in features], default=0)
    new_id = max_id + 1

    new_feature = {
        "id": new_id,
        "name": name,
        "test_steps": test_steps,
        "workflow_profile": workflow_profile,
        "completed": False,
        "deferred": False,
        "defer_reason": None,
        "deferred_at": None,
        "defer_group": None,
        "owners": _default_owners(),
    }
    _normalize_feature_contract(new_feature)

    try:
        imported_contract = _import_contract_for_feature(new_id, svc)
    except ContractImportError as exc:
        print(f"Error: Failed to import contract for feature {new_id}: {exc}")
        return False
    if imported_contract:
        _apply_imported_feature_contract(new_feature, imported_contract)

    features.append(new_feature)
    svc.save_progress_json_fn(data)
    svc.save_progress_md_fn("")

    print(f"Added feature: {name} (ID: {new_id})")
    svc.notify_parent_sync_fn("refresh")
    return True


def update_feature_command(
    feature_id: int,
    name: str,
    *,
    svc: WorkItemCommandsServices,
    test_steps: Optional[List[str]] = None,
) -> bool:
    """Update an existing feature's name and optional test steps."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    normalized_name = name.strip()
    if not normalized_name:
        print("Feature name cannot be empty")
        return False

    feature["name"] = normalized_name
    if test_steps:
        feature["test_steps"] = test_steps
    _normalize_feature_contract(feature)

    try:
        imported_contract = _import_contract_for_feature(feature_id, svc)
    except ContractImportError as exc:
        print(f"Error: Failed to import contract for feature {feature_id}: {exc}")
        return False
    if imported_contract:
        _apply_imported_feature_contract(feature, imported_contract)

    _persist_progress(data, svc)
    print(f"Updated feature {feature_id}: {normalized_name}")
    if test_steps:
        print(f"Updated test steps ({len(test_steps)} step(s))")
    return True


def defer_features_command(
    feature_id: Optional[int],
    all_pending: bool,
    reason: str,
    *,
    svc: WorkItemCommandsServices,
    defer_group: Optional[str] = None,
) -> bool:
    """Defer one feature or all pending features without losing tracker state."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_reason = _normalize_optional_string(reason)
    if not normalized_reason:
        print("Error: --reason is required and cannot be empty.")
        return False

    normalized_group = _normalize_optional_string(defer_group)
    features = data.get("features", [])
    targets: List[Dict[str, Any]] = []

    if all_pending:
        targets = [
            feature
            for feature in features
            if isinstance(feature, dict) and not feature.get("completed", False)
        ]
        if not targets:
            print("No pending features to defer.")
            return False
    else:
        if feature_id is None:
            print("Error: --feature-id is required when --all-pending is not set.")
            return False
        feature = next((f for f in features if f.get("id") == feature_id), None)
        if not feature:
            print(f"Feature ID {feature_id} not found")
            return False
        if feature.get("completed", False):
            print(f"Feature ID {feature_id} is already completed and cannot be deferred.")
            return False
        targets = [feature]

    now = _iso_now()
    target_ids = {feature.get("id") for feature in targets}
    for feature in targets:
        feature["deferred"] = True
        feature["defer_reason"] = normalized_reason
        feature["deferred_at"] = now
        feature["defer_group"] = normalized_group

    cleared_active = False
    if data.get("current_feature_id") in target_ids:
        data["current_feature_id"] = None
        if "workflow_state" in data:
            del data["workflow_state"]
        cleared_active = True

    svc.update_runtime_context_fn(data, source="defer")
    _persist_progress(data, svc)

    print(f"Deferred {len(targets)} feature(s).")
    print(f"Reason: {normalized_reason}")
    if normalized_group:
        print(f"Group: {normalized_group}")
    if cleared_active:
        print(
            "Cleared active feature and workflow_state because the active feature was deferred."
        )
    return True


def resume_deferred_features_command(
    defer_group: Optional[str],
    resume_all: bool,
    *,
    svc: WorkItemCommandsServices,
) -> bool:
    """Resume deferred features by group or resume all deferred features."""
    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    normalized_group = _normalize_optional_string(defer_group)
    features = data.get("features", [])
    targets: List[Dict[str, Any]] = []

    for feature in features:
        if not isinstance(feature, dict):
            continue
        if feature.get("completed", False):
            continue
        if not _is_feature_deferred(feature):
            continue
        if not resume_all and feature.get("defer_group") != normalized_group:
            continue
        targets.append(feature)

    if not targets:
        if resume_all:
            print("No deferred pending features to resume.")
        else:
            print(f"No deferred pending features found for group: {normalized_group}")
        return False

    for feature in targets:
        _clear_feature_defer_state(feature)

    svc.update_runtime_context_fn(data, source="resume")
    _persist_progress(data, svc)

    print(f"Resumed {len(targets)} deferred feature(s).")
    if not resume_all:
        print(f"Group: {normalized_group}")
    return True


def add_task_item_command(
    description: str,
    *,
    svc: WorkItemCommandsServices,
    details: str = "",
    refs: Optional[List[str]] = None,
    next_action: str = "",
    priority: str = "P1",
    workflow_profile: str = WORKFLOW_PROFILE_DEFAULT,
    parent_feature_id: Optional[int] = None,
) -> Optional[str]:
    """Write a standalone task item to tasks[]."""
    if not description or not description.strip():
        raise ValueError("Description cannot be empty")

    description = description.strip()
    if len(description) > 2000:
        raise ValueError(f"Description too long ({len(description)} chars, max 2000)")

    valid_priorities = ["P0", "P1", "P2"]
    if priority not in valid_priorities:
        raise ValueError(
            f"Invalid priority '{priority}'. Must be one of: {valid_priorities}"
        )

    if workflow_profile not in WORKFLOW_PROFILE_VALUES:
        raise ValueError(
            f"Invalid workflow_profile '{workflow_profile}'. "
            f"Allowed: {sorted(WORKFLOW_PROFILE_VALUES)}"
        )

    description = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", description)
    if details:
        details = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", details)

    refs = list(refs) if refs else []

    data = svc.load_progress_json_fn()
    if not data:
        print("No progress tracking found. Use init first.")
        return None

    if parent_feature_id is not None:
        features = data.get("features", [])
        if not any(feature.get("id") == parent_feature_id for feature in features):
            print(f"Error: feature {parent_feature_id} not found")
            return None

    tasks = data.setdefault("tasks", [])
    existing_ids = [task.get("id", "") for task in tasks if isinstance(task, dict)]
    next_index = len(tasks) + 1
    while f"TASK-{next_index:03d}" in existing_ids:
        next_index += 1
    task_id = f"TASK-{next_index:03d}"

    new_task = {
        "id": task_id,
        "type": "task",
        "description": description,
        "workflow_profile": workflow_profile,
        "status": "pending",
        "priority": priority,
        "details": details.strip() if details else "",
        "refs": refs,
        "next_action": next_action.strip() if next_action else "",
        "created_at": _iso_now(),
        "parent_feature_id": parent_feature_id,
    }

    tasks.append(new_task)
    data["tasks"] = tasks

    _persist_progress(data, svc)
    print(f"Task recorded: {task_id}")
    print(f"Description: {description}")
    print(f"workflow_profile: {workflow_profile}")
    return task_id


def smart_intake_command(
    candidate_json: str,
    *,
    svc: WorkItemCommandsServices,
    commit: Optional[str] = None,
    workflow_profile: str = WORKFLOW_PROFILE_DEFAULT,
) -> bool:
    """Deterministic work-item intake executor."""
    try:
        candidate = json.loads(candidate_json)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"Error: invalid candidate JSON: {exc}")
        return False

    if not isinstance(candidate, dict):
        print("Error: candidate JSON must be an object")
        return False

    item_type = candidate.get("type", "")
    try:
        confidence = float(candidate.get("confidence", 0.0))
    except (TypeError, ValueError):
        print("Error: confidence must be a number")
        return False

    profile = candidate.get("profile", {})
    if not isinstance(profile, dict):
        print("Error: profile must be an object")
        return False

    description = (profile.get("description") or "").strip()
    if not description:
        print("Error: profile.description is required")
        return False

    if item_type not in WORK_ITEM_TAXONOMY:
        print(
            f"Error: invalid type '{item_type}'. "
            f"Must be one of: {sorted(WORK_ITEM_TAXONOMY)}"
        )
        return False

    if not commit:
        print("[候选工作项]")
        print(f"  type:        {item_type}")
        print(f"  confidence:  {confidence:.2f}")
        print("  profile:")
        print(f"    description: {description}")
        for key in ("priority", "details", "refs", "next_action"):
            value = profile.get(key)
            if value:
                print(f"    {key}: {value}")

        if confidence < 0.6:
            print()
            print(
                "needs_clarification: 请补充信息 — 这条记录更接近 bug、"
                "feature、task 还是 update？"
            )
            print("  → 确认后用 --commit <type> 重新提交")
            return True

        print()
        print(f"→ 使用 --commit {item_type} 写入，或指定其他类型")
        return True

    if commit == "bug":
        priority_str = profile.get("priority", "P1")
        bug_priority = _SMART_INTAKE_PRIORITY_MAP.get(priority_str, "medium")
        try:
            success, bug_id = svc.add_bug_internal_fn(
                description=description,
                priority=bug_priority,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return False
        if success and bug_id:
            data = svc.load_progress_json_fn()
            if not isinstance(data, dict):
                print("No progress tracking found. Use init first.")
                return False
            _push_bug_to_routing_queue(data, bug_id, bug_priority)
            _persist_progress(data, svc)
        return success

    if commit == "task":
        raw_priority = profile.get("priority", "P1")
        if raw_priority not in ("P0", "P1", "P2"):
            raw_priority = "P1"
        task_id = add_task_item_command(
            description=description,
            svc=svc,
            details=profile.get("details", "") or "",
            refs=profile.get("refs") or [],
            next_action=profile.get("next_action", "") or "",
            priority=raw_priority,
            workflow_profile=workflow_profile,
        )
        return task_id is not None

    if commit == "feature":
        return bool(
            add_feature_command(
                name=description,
                test_steps=[],
                svc=svc,
                workflow_profile=workflow_profile,
            )
        )

    if commit == "update":
        raw_category = profile.get("category", "status")
        category = raw_category if raw_category in UPDATE_CATEGORIES else "status"
        return add_update_command(
            category=category,
            summary=description,
            svc=svc,
            details=profile.get("details") or None,
            next_action=profile.get("next_action") or None,
            refs=profile.get("refs") or None,
        )

    print(f"Error: unknown commit type '{commit}'")
    return False
