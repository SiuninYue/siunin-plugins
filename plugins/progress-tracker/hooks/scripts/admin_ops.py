#!/usr/bin/env python3
"""Administrative progress-tracking operations (reset, baseline recreation).

Business logic extracted from progress_manager.py per the modularization
boundary rule (see docs/progress-tracker/architecture/module-boundaries.md):
progress_manager.py is a thin shim; concrete logic lives here and receives
its dependencies via callback injection. This module MUST NOT import
progress_manager.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reset_tracking(
    *,
    force: bool,
    remove_active: bool,
    progress_dir: Path,
    tracked_files: List[Path],
    summary_file: Path,
    legacy_summary_file: Path,
    schema_version: str,
    root_route_code: str,
    logger,
    input_fn: Callable[[str], str],
    load_progress_json: Callable[[], Optional[Dict[str, Any]]],
    save_progress_json: Callable[[Dict[str, Any]], Any],
    save_progress_md: Callable[[str], Any],
    save_checkpoints: Callable[[Dict[str, Any]], Any],
    generate_progress_md: Callable[[Dict[str, Any]], str],
    archive_current_progress: Callable[[str], Optional[Dict[str, Any]]],
    record_reset_event: Callable[[], Any],
    find_project_root: Callable[[], Path],
    resolve_repo_root: Callable[[Path], Path],
    auto_discover_child_plugins: Callable[[Path, Path, Dict[str, Any]], Dict[str, Any]],
    load_status_summary_projection: Callable[[str], Any],
) -> bool:
    """Reset active progress tracking files while preserving archive/history.

    Default mode archives the current state, then recreates a clean empty
    baseline (preserving project metadata) and rebuilds the summary projection.
    With ``remove_active=True`` it instead deletes all active tracking and
    summary files outright.
    """
    summary_files = [summary_file, legacy_summary_file]

    # If no real tracked files remain, there is nothing to archive/recreate —
    # but still clean any orphaned summary projection so stale state cannot
    # "revive" (legacy reset deleted tracked files yet left the summary behind).
    if not progress_dir.exists() or not any(path.exists() for path in tracked_files):
        orphan_removed = []
        for path in summary_files:
            if path.exists():
                path.unlink()
                orphan_removed.append(path.name)
        if orphan_removed:
            print(
                "No active progress tracking found. "
                f"Cleaned orphaned summary: {', '.join(orphan_removed)}"
            )
        else:
            print("No progress tracking found to reset.")
        return True

    if not force:
        action_name = "remove" if remove_active else "reset (archive & recreate baseline)"
        confirm = input_fn(
            f"Are you sure you want to {action_name} active progress files at {progress_dir}? (y/N): "
        )
        if confirm.lower() != "y":
            print("Reset cancelled.")
            return False

    try:
        # 1. Read existing progress JSON metadata to preserve across recreation.
        project_name = "Unknown"
        tracker_role = None
        project_code = None
        parent_project_root = None
        settings = {"auto_state_commit": True}

        if (progress_dir / tracked_files[0].name).exists():
            try:
                existing = load_progress_json()
                if isinstance(existing, dict):
                    project_name = existing.get("project_name", project_name)
                    tracker_role = existing.get("tracker_role", tracker_role)
                    project_code = existing.get("project_code", project_code)
                    parent_project_root = existing.get("parent_project_root", parent_project_root)
                    settings = existing.get("settings") or settings
            except Exception as e:
                logger.warning(f"Could not load metadata from existing progress.json: {e}")

        # 2. Archive current progress and append the reset audit event (must run
        #    before files are deleted so audit_log can still write).
        archived_entry = archive_current_progress("reset")
        record_reset_event()

        # 3. Clear active tracking and summary files.
        for path in tracked_files + summary_files:
            if path.exists():
                path.unlink()

        if remove_active:
            print("Progress tracking completely removed.")
            _print_archive_note(archived_entry)
            return True

        # 4. Recreate a clean empty baseline, preserving project metadata.
        now = _iso_now()
        data: Dict[str, Any] = {
            "schema_version": schema_version,
            "project_name": project_name,
            "created_at": now,
            "updated_at": now,
            "features": [],
            "current_feature_id": None,
            "settings": settings or {"auto_state_commit": True},
        }
        if tracker_role:
            data["tracker_role"] = tracker_role
        if project_code:
            data["project_code"] = project_code
        if parent_project_root:
            data["parent_project_root"] = parent_project_root

        # Parent-tracker defaults: a root containing plugins/ is a parent.
        target_root = find_project_root()
        is_parent_root = (target_root / "plugins").is_dir()
        if is_parent_root or tracker_role == "parent":
            data["tracker_role"] = "parent"
            data["project_code"] = root_route_code
            data["routing_queue"] = [root_route_code]

        save_progress_json(data)
        save_progress_md(generate_progress_md(data))
        save_checkpoints(
            {
                "last_checkpoint_at": None,
                "max_entries": 10,
                "entries": [],
            }
        )

        # 5. Parent trackers re-discover child plugins so routing is rebuilt.
        if data.get("tracker_role") == "parent":
            try:
                repo_root = resolve_repo_root(target_root)
                discover_result = auto_discover_child_plugins(target_root, repo_root, data)
                if discover_result.get("added_codes"):
                    save_progress_json(data)
                    save_progress_md(generate_progress_md(data))
            except Exception as exc:
                logger.warning(f"Child discovery during reset failed: {exc}")

        # 6. Rebuild the status summary projection (status_summary.v1.json).
        try:
            load_status_summary_projection(str(target_root))
        except Exception as exc:
            logger.warning(f"Failed to rebuild status summary projection on reset: {exc}")

        print(
            "Progress tracking reset successfully. "
            f"Recreated empty baseline for project '{project_name}'."
        )
        print("Active files archived, cleared, and reinitialized.")
        _print_archive_note(archived_entry)
        return True
    except Exception as e:
        print(f"Error resetting progress tracking: {e}")
        return False


def _print_archive_note(archived_entry: Optional[Dict[str, Any]]) -> None:
    if archived_entry:
        print(
            "Archived previous progress as "
            f"{archived_entry.get('archive_id')} "
            f"(reason={archived_entry.get('reason')})"
        )
