"""
route_preflight.py - Parent/child route ownership guard.

Extracted from route_commands.py during F18 modularisation. Keeps fail-closed
route checks separate from route CLI commands while preserving
progress_manager re-export names.
"""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from route_sync import (
    _iter_linked_project_specs,
    _load_progress_payload_at_root,
    _normalize_project_code,
    _resolve_linked_project_root,
)
from state_io import DEFAULT_TRACKER_ROLE, _normalize_route_schema
from pm_runtime import get_progress_manager_module


def _pm():
    """Return the active progress_manager module for CLI scope and test patches."""
    return get_progress_manager_module()


# ---------------------------------------------------------------------------
# Route preflight guard
# ---------------------------------------------------------------------------


def _scope_hint(path: Path, repo_root: Path) -> str:
    """Render a path as repo-relative when possible for CLI guidance."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _extract_command_tail(argv: Sequence[str], command: str) -> List[str]:
    """Extract command + args tail from argv for retry hints."""
    try:
        index = list(argv).index(command)
    except ValueError:
        return [command]
    return list(argv[index:])


def _discover_parent_route_bindings_for_child(
    child_project_root: Path,
    repo_root: Path,
) -> List[Dict[str, Any]]:
    """Discover parent trackers that link to the given child tracker root."""
    pm = _pm()
    candidate_roots: List[Path] = [repo_root]
    plugins_dir = repo_root / "plugins"
    if plugins_dir.is_dir():
        candidate_roots.extend(sorted(path for path in plugins_dir.iterdir() if path.is_dir()))

    discovered: List[Dict[str, Any]] = []
    seen_roots: Set[Path] = set()
    child_resolved = child_project_root.resolve()
    repo_resolved = repo_root.resolve()

    for candidate_root in candidate_roots:
        resolved_root = candidate_root.resolve()
        if resolved_root in seen_roots or resolved_root == child_resolved:
            continue
        seen_roots.add(resolved_root)

        payload, _ = _load_progress_payload_at_root(resolved_root)
        if not isinstance(payload, dict):
            continue
        _normalize_route_schema(payload)
        tracker_role = str(payload.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
        if tracker_role != "parent":
            continue

        matched_entry: Optional[Dict[str, Any]] = None
        for spec in _iter_linked_project_specs(payload):
            linked_root = _resolve_linked_project_root(
                spec["raw_project_root"],
                resolved_root,
                repo_resolved,
            )
            if linked_root == child_resolved or pm._resolve_main_repo_path(linked_root) == pm._resolve_main_repo_path(child_resolved):
                entry = spec.get("entry")
                matched_entry = entry if isinstance(entry, dict) else {}
                break

        if matched_entry is None:
            continue

        active_routes = payload.get("active_routes")
        if not isinstance(active_routes, list):
            active_routes = []

        discovered.append(
            {
                "project_root": resolved_root,
                "linked_entry": matched_entry,
                "active_routes": active_routes,
            }
        )

    return discovered


def _print_route_preflight_block(
    *,
    reason: str,
    command: str,
    argv: Sequence[str],
    child_project_root: Path,
    repo_root: Path,
    child_code: Optional[str],
    parent_project_root: Optional[Path],
) -> None:
    """Print deterministic route preflight recovery guidance."""
    command_tail = _extract_command_tail(argv, command)
    command_tail_text = " ".join(shlex.quote(token) for token in command_tail) if command_tail else command
    child_scope = shlex.quote(_scope_hint(child_project_root, repo_root))
    code_hint = child_code or "<PROJECT_CODE>"

    print(f"[Route Preflight] BLOCKED: {reason}")
    print(f"Current tracker: {child_project_root}")
    if parent_project_root is not None:
        print(f"Detected parent tracker: {parent_project_root}")

    print("Recovery:")
    print(f"  cd {repo_root}")
    if parent_project_root is None:
        print(
            '  # Identify parent tracker root: directory whose progress.json has tracker_role="parent"'
        )
        print(
            "  plugins/progress-tracker/prog "
            f"--project-root {child_scope} link-project --code {code_hint} "
            "--parent-root <parent_tracker_root>"
        )
        print(
            "  plugins/progress-tracker/prog --project-root <parent_tracker_root> "
            f"route-select --project {code_hint} --feature-ref {code_hint}-F<number>"
        )
    else:
        parent_scope = shlex.quote(_scope_hint(parent_project_root, repo_root))
        print(
            "  plugins/progress-tracker/prog "
            f"--project-root {parent_scope} route-select --project {code_hint} "
            f"--feature-ref {code_hint}-F<number>"
        )
    print(f"  cd {child_project_root}")
    print(
        "  plugins/progress-tracker/prog "
        f"--project-root {child_scope} {command_tail_text}"
    )


def enforce_route_preflight(command: str, argv: Sequence[str]) -> bool:
    """Fail-closed preflight for child tracker mutating commands."""
    pm = _pm()
    if command in pm.ROUTE_PREFLIGHT_EXEMPT_COMMANDS:
        return True

    data = pm.load_progress_json()
    if not isinstance(data, dict):
        return True

    tracker_role = str(data.get("tracker_role") or DEFAULT_TRACKER_ROLE).strip().lower()
    if tracker_role != "child":
        return True

    child_project_root = pm.find_project_root().resolve()
    repo_root = Path(pm._REPO_ROOT or child_project_root).resolve()
    child_code_raw = data.get("project_code")
    child_code = _normalize_project_code(child_code_raw) if isinstance(child_code_raw, str) else None

    parent_bindings = _discover_parent_route_bindings_for_child(
        child_project_root=child_project_root,
        repo_root=repo_root,
    )

    if child_code is None:
        _print_route_preflight_block(
            reason="Child tracker has no project_code; route ownership cannot be verified.",
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=None,
            parent_project_root=parent_bindings[0]["project_root"] if parent_bindings else None,
        )
        return False

    if not parent_bindings:
        _print_route_preflight_block(
            reason=(
                f"Child project_code={child_code} is not registered in any parent linked_projects. "
                "Mutating command denied."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=None,
        )
        return False

    if len(parent_bindings) > 1:
        _print_route_preflight_block(
            reason=(
                f"Child project_code={child_code} is linked by multiple parent trackers "
                f"({len(parent_bindings)} matches). Mutating command denied until routing is unambiguous."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=parent_bindings[0]["project_root"],
        )
        return False

    parent_binding = parent_bindings[0]
    parent_project_root = parent_binding["project_root"]
    linked_entry = parent_binding.get("linked_entry", {})
    linked_code_raw = linked_entry.get("project_code") if isinstance(linked_entry, dict) else None
    linked_code = _normalize_project_code(linked_code_raw) if isinstance(linked_code_raw, str) else None
    if linked_code is not None and linked_code != child_code:
        _print_route_preflight_block(
            reason=(
                f"Parent registration mismatch: child reports {child_code}, "
                f"but parent linked_projects expects {linked_code}."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=parent_project_root,
        )
        return False

    active_route_codes: List[str] = []
    for route in parent_binding.get("active_routes", []):
        if not isinstance(route, dict):
            continue
        route_code_raw = route.get("project_code")
        if not isinstance(route_code_raw, str):
            continue
        route_code = _normalize_project_code(route_code_raw)
        if route_code is not None:
            active_route_codes.append(route_code)

    if child_code not in active_route_codes:
        # Bootstrap exception (F17): set-current is the command that creates the
        # active_routes entry.  Only exempt when active_routes is EMPTY — meaning
        # no other project has claimed the slot.  If another project is active
        # (route mismatch), set-current must still be blocked like every other
        # mutating command.
        if command == "set-current" and not active_route_codes:
            print(
                f"[WARNING] Route preflight bootstrap: {child_code} not in parent "
                "active_routes (empty). Allowing set-current to bootstrap the route entry."
            )
            return True

        active_display = ", ".join(sorted(set(active_route_codes))) if active_route_codes else "(none)"
        _print_route_preflight_block(
            reason=(
                f"Parent active route mismatch: expected {child_code}, current active routes: {active_display}. "
                "Mutating command denied."
            ),
            command=command,
            argv=argv,
            child_project_root=child_project_root,
            repo_root=repo_root,
            child_code=child_code,
            parent_project_root=parent_project_root,
        )
        return False

    return True
