# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("progress_tracker.bug_tracker")


def list_bugs(
    *,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
) -> bool:
    """List all bugs in progress tracking."""
    data = load_progress_json_fn()
    if not data:
        print("No progress tracking found.")
        return False

    bugs = data.get("bugs", [])
    if not bugs:
        print("No bugs recorded.")
        return True

    print(f"\n## Bug Backlog ({len(bugs)} total)\n")

    # Group by status
    status_icons = {
        "pending_investigation": "🔴",
        "investigating": "🟡",
        "confirmed": "🟢",
        "fixing": "🔧",
        "fixed": "✅",
        "false_positive": "❌"
    }

    # Sort by priority and status
    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = ["pending_investigation", "investigating", "confirmed", "fixing", "fixed", "false_positive"]

    def sort_key(bug):
        priority = bug.get("priority", "medium")
        status = bug.get("status", "pending_investigation")
        return (
            status_order.index(status) if status in status_order else 99,
            priority_order.get(priority, 1),
            bug.get("created_at", "")
        )

    sorted_bugs = sorted(bugs, key=sort_key)

    for bug in sorted_bugs:
        bug_id = bug.get("id", "Unknown")
        description = bug.get("description", "No description")
        status = bug.get("status", "unknown")
        priority = bug.get("priority", "medium")
        category = bug.get("category", "bug")
        created_at = bug.get("created_at", "")
        scheduled = bug.get("scheduled_position", {})

        icon = status_icons.get(status, "❓")

        # Calculate time ago
        time_ago = ""
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                now = datetime.now(created_dt.tzinfo)
                diff = now - created_dt
                hours = diff.total_seconds() / 3600
                if hours < 1:
                    time_ago = f"{int(diff.total_seconds() / 60)}m ago"
                elif hours < 24:
                    time_ago = f"{int(hours)}h ago"
                else:
                    time_ago = f"{int(hours / 24)}d ago"
            except (ValueError, AttributeError, OSError) as e:
                logger.debug(f"Error parsing date '{created_at}': {e}")
                time_ago = "unknown"

        print(f"- [{bug_id}] {description}")
        print(
            f"  Status: {icon} {status} | Priority: {priority} | "
            f"Category: {category} | Created: {time_ago}"
        )

        if scheduled:
            pos_type = scheduled.get("type", "")
            feature_id = scheduled.get("feature_id")
            reason = scheduled.get("reason", "")
            if pos_type == "before_feature" and feature_id:
                print(f"  📍 Before Feature {feature_id} ({reason})")
            elif pos_type == "after_feature" and feature_id:
                print(f"  📍 After Feature {feature_id} ({reason})")
            elif pos_type == "last":
                print(f"  📍 Last ({reason})")

        # Show root cause if confirmed
        if status in ["confirmed", "fixing", "fixed"] and "root_cause" in bug:
            print(f"  Root cause: {bug['root_cause']}")

        # Show fix summary if fixed
        if status == "fixed" and "fix_summary" in bug:
            print(f"  Fix: {bug['fix_summary']}")

        print()

    return True


def _add_bug_internal(
    description: str,
    status: str = "pending_investigation",
    priority: str = "medium",
    category: str = "bug",
    scheduled_position: Optional[str] = None,
    verification_results: Optional[str] = None,
    *,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    get_next_bug_id_fn: Callable[[], str],
    generate_progress_md_fn: Callable[[Dict[str, Any]], str],
    save_progress_md_fn: Callable[[str], None],
) -> Tuple[bool, Optional[str]]:
    """Add a new bug to the tracking with validation (internal)."""
    # Validate description
    if not description or not description.strip():
        raise ValueError("Description cannot be empty")

    description = description.strip()

    if len(description) > 2000:
        raise ValueError(f"Description too long ({len(description)} chars, max 2000)")

    # Validate status
    valid_statuses = ["pending_investigation", "investigating", "confirmed",
                     "fixing", "fixed", "false_positive"]
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

    # Validate priority
    valid_priorities = ["high", "medium", "low"]
    if priority not in valid_priorities:
        raise ValueError(f"Invalid priority '{priority}'. Must be one of: {valid_priorities}")

    valid_categories = ["bug", "technical_debt"]
    if category not in valid_categories:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {valid_categories}")

    # Sanitize description (remove control characters except newline/tab)
    description = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', description)

    data = load_progress_json_fn()
    if not data:
        raise ValueError("No progress tracking found. Use '/prog init' first.")

    bugs = data.get("bugs", [])
    if bugs is None:
        bugs = []
        data["bugs"] = bugs

    # Check for duplicate bugs (case-insensitive, normalized whitespace)
    normalized_desc = re.sub(r'\s+', ' ', description.lower())
    for bug in bugs:
        if bug.get("status") == "false_positive":
            continue
        bug_desc = bug.get("description", "")
        normalized_bug_desc = re.sub(r'\s+', ' ', bug_desc.lower())
        if normalized_bug_desc == normalized_desc:
            print(f"Duplicate bug detected: {bug.get('id')}")
            print("Use 'update-bug' to add more information or different bug.")
            return False, None

    # Generate new bug ID
    bug_id = get_next_bug_id_fn()

    # Parse scheduled position
    scheduled_pos = None
    if scheduled_position:
        if scheduled_position == "last":
            scheduled_pos = {"type": "last", "reason": "Non-urgent, defer to later"}
        elif ":" in scheduled_position:
            pos_type, feature_id = scheduled_position.split(":", 1)
            try:
                scheduled_pos = {
                    "type": f"{pos_type}_feature",
                    "feature_id": int(feature_id),
                    "reason": "Smart scheduling based on impact"
                }
            except ValueError:
                raise ValueError(f"Invalid scheduled position format: {scheduled_position}")

    # Parse verification results if provided with validation
    quick_verification = {}
    if verification_results:
        # Check size limit (10KB)
        if len(verification_results) > 10240:
            raise ValueError(f"Verification results too large ({len(verification_results)} bytes, max 10KB)")

        try:
            quick_verification = json.loads(verification_results)

            # Validate structure
            if not isinstance(quick_verification, dict):
                raise ValueError("Verification results must be a JSON object")

            # Limit nesting depth to prevent stack overflow
            def check_depth(obj, current_depth=0, max_depth=10):
                if current_depth > max_depth:
                    raise ValueError("JSON nesting too deep (max 10 levels)")
                if isinstance(obj, dict):
                    for v in obj.values():
                        check_depth(v, current_depth + 1, max_depth)
                elif isinstance(obj, list):
                    for v in obj:
                        check_depth(v, current_depth + 1, max_depth)

            check_depth(quick_verification)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid verification results JSON: {e}")

    new_bug = {
        "id": bug_id,
        "description": description,
        "status": status,
        "priority": priority,
        "category": category,
        "created_at": datetime.now().isoformat() + "Z",
        "quick_verification": quick_verification,
    }

    if scheduled_pos:
        new_bug["scheduled_position"] = scheduled_pos

    bugs.append(new_bug)
    data["bugs"] = bugs

    save_progress_json_fn(data)

    # Update progress.md
    md_content = generate_progress_md_fn(data)
    save_progress_md_fn(md_content)

    logger.info(f"Bug {bug_id} added successfully")
    print(f"Bug recorded: {bug_id}")
    print(f"Description: {description}")
    print(f"Status: {status}")
    print(f"Priority: {priority}")
    print(f"Category: {category}")
    if scheduled_pos:
        print(f"Scheduled: {scheduled_pos}")
    return True, bug_id


def add_bug(
    description: str,
    status: str = "pending_investigation",
    priority: str = "medium",
    category: str = "bug",
    scheduled_position: Optional[str] = None,
    verification_results: Optional[str] = None,
    *,
    add_bug_internal_fn: Callable[..., Tuple[bool, Optional[str]]],
) -> bool:
    """Public wrapper around _add_bug_internal preserving the bool return type."""
    success, _ = add_bug_internal_fn(
        description=description,
        status=status,
        priority=priority,
        category=category,
        scheduled_position=scheduled_position,
        verification_results=verification_results,
    )
    return success


def update_bug(
    bug_id: str,
    status: Optional[str] = None,
    root_cause: Optional[str] = None,
    fix_summary: Optional[str] = None,
    *,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    generate_progress_md_fn: Callable[[Dict[str, Any]], str],
    save_progress_md_fn: Callable[[str], None],
    auto_state_commit_fn: Callable[[str, str], None],
) -> bool:
    """Update bug status and/or add investigation/fix information."""
    data = load_progress_json_fn()
    if not data:
        print("No progress tracking found.")
        return False

    bugs = data.get("bugs", [])
    if not bugs:
        print(f"No bugs found. Bug {bug_id} does not exist.")
        return False

    bug = next((b for b in bugs if b.get("id") == bug_id), None)
    if not bug:
        print(f"Bug {bug_id} not found.")
        return False

    updated = False

    if status:
        bug["status"] = status
        bug["updated_at"] = datetime.now().isoformat() + "Z"
        updated = True

        # Set current bug if starting investigation/fixing
        if status in ["investigating", "fixing"]:
            data["current_bug_id"] = bug_id
        elif status == "fixed":
            data["current_bug_id"] = None

    if root_cause:
        bug["root_cause"] = root_cause
        if "investigation" not in bug:
            bug["investigation"] = {}
        bug["investigation"]["root_cause"] = root_cause
        bug["investigation"]["confirmed_at"] = datetime.now().isoformat() + "Z"
        updated = True

    if fix_summary:
        bug["fix_summary"] = fix_summary
        bug["fixed_at"] = datetime.now().isoformat() + "Z"
        updated = True

    if updated:
        save_progress_json_fn(data)
        md_content = generate_progress_md_fn(data)
        save_progress_md_fn(md_content)
        if status == "fixed":
            auto_state_commit_fn(bug_id, "fix")
        print(f"Bug {bug_id} updated.")
        if status:
            print(f"Status: {status}")
        if root_cause:
            print(f"Root cause: {root_cause}")
        if fix_summary:
            print(f"Fix summary: {fix_summary}")
        return True
    else:
        print("No updates provided. Use --status, --root-cause, or --fix-summary")
        return False
