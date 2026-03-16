#!/usr/bin/env python3
"""
Shared path and migration helpers for progress-tracker storage.

Storage layout:
  <target_project_root>/
    docs/
      plans/              <- Feature implementation plans (Superpowers standard)
      archive/
        plans/            <- Completed feature plans
        testing/          <- Archived test reports
      progress-tracker/   <- Internal progress-tracker state (not plans)
        state/            <- progress.json, checkpoints.json, etc.
        architecture/     <- architecture.md
        testing/          <- Active bug fix reports
        cache/            <- Complexity cache
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROG_DOCS_DIRNAME = "progress-tracker"
LEGACY_CLAUDE_DIR = ".claude"

PROGRESS_JSON = "progress.json"
PROGRESS_MD = "progress.md"
CHECKPOINTS_JSON = "checkpoints.json"
PROJECT_MEMORY_JSON = "project_memory.json"
PROGRESS_HISTORY_JSON = "progress_history.json"
PROGRESS_ARCHIVE_DIR = "progress_archive"
MIGRATION_LOG_JSON = "migration_log.json"
ARCHITECTURE_MD = "architecture.md"
COMPLEXITY_CACHE_JSON = "complexity_cache.json"

PLAN_PREFIX = "docs/plans/"
# Legacy paths kept for migration detection only
LEGACY_PLAN_PREFIX = "docs/progress-tracker/plans/"
OLD_TESTING_PREFIX = "docs/testing/"
NEW_TESTING_PREFIX = "docs/progress-tracker/testing/"


class ProjectRootResolutionError(RuntimeError):
    """Raised when target project root cannot be resolved safely."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_root(cwd: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def resolve_repo_root(cwd: Optional[Path] = None) -> Path:
    current = (cwd or Path.cwd()).resolve()
    git_root = _git_root(current)
    return git_root if git_root else current


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _detect_plugin_root(repo_root: Path, cwd: Path) -> Optional[Path]:
    plugins_dir = repo_root / "plugins"
    if not plugins_dir.exists() or not plugins_dir.is_dir():
        return None

    try:
        rel = cwd.resolve().relative_to(plugins_dir.resolve())
    except Exception:
        return None

    if not rel.parts:
        return None

    candidate = plugins_dir / rel.parts[0]
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    return None


def resolve_target_project_root(
    project_root_arg: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Tuple[Path, Path]:
    """
    Resolve (target_project_root, repo_root) under strict monorepo rules.

    Rules:
    - if --project-root is provided: must exist and be inside repo root
    - else if cwd is under repo/plugins/<name>: select that plugin root
    - else if repo has plugins/: fail (ambiguous)
    - else: use repo root (single-project repo)
    """
    current = (cwd or Path.cwd()).resolve()
    repo_root = resolve_repo_root(current)

    if project_root_arg:
        raw_candidate = Path(project_root_arg)
        candidate_paths: List[Path] = []
        if raw_candidate.is_absolute():
            candidate_paths.append(raw_candidate.resolve())
        else:
            # Prefer cwd-relative semantics for explicit user input like `--project-root .`,
            # while preserving repo-root-relative compatibility for older invocations.
            cwd_candidate = (current / raw_candidate).resolve()
            repo_candidate = (repo_root / raw_candidate).resolve()
            candidate_paths.append(cwd_candidate)
            if repo_candidate != cwd_candidate:
                candidate_paths.append(repo_candidate)

        for candidate in candidate_paths:
            if not candidate.exists() or not candidate.is_dir():
                continue
            if not _is_relative_to(candidate, repo_root):
                raise ProjectRootResolutionError(
                    f"--project-root must be inside repository root: {repo_root}"
                )
            return candidate, repo_root

        tried = ", ".join(str(path) for path in candidate_paths)
        raise ProjectRootResolutionError(
            "--project-root does not exist or is not a directory: "
            f"{project_root_arg} (tried: {tried})"
        )

    plugin_root = _detect_plugin_root(repo_root, current)
    if plugin_root:
        return plugin_root, repo_root

    if (repo_root / "plugins").is_dir():
        raise ProjectRootResolutionError(
            "Ambiguous monorepo scope. Run inside plugins/<name> or pass "
            "--project-root plugins/<name>."
        )

    return repo_root, repo_root


def get_tracker_docs_root(target_root: Path) -> Path:
    return target_root / "docs" / PROG_DOCS_DIRNAME


def get_state_dir(target_root: Path) -> Path:
    return get_tracker_docs_root(target_root) / "state"


def get_plans_dir(target_root: Path) -> Path:
    return get_tracker_docs_root(target_root) / "plans"


def get_testing_dir(target_root: Path) -> Path:
    return get_tracker_docs_root(target_root) / "testing"


def get_architecture_dir(target_root: Path) -> Path:
    return get_tracker_docs_root(target_root) / "architecture"


def get_cache_dir(target_root: Path) -> Path:
    return get_tracker_docs_root(target_root) / "cache"


def get_progress_json_path(target_root: Path) -> Path:
    return get_state_dir(target_root) / PROGRESS_JSON


def get_progress_md_path(target_root: Path) -> Path:
    return get_state_dir(target_root) / PROGRESS_MD


def get_checkpoints_path(target_root: Path) -> Path:
    return get_state_dir(target_root) / CHECKPOINTS_JSON


def get_project_memory_path(target_root: Path) -> Path:
    return get_state_dir(target_root) / PROJECT_MEMORY_JSON


def get_progress_history_path(target_root: Path) -> Path:
    return get_state_dir(target_root) / PROGRESS_HISTORY_JSON


def get_progress_archive_dir(target_root: Path) -> Path:
    return get_state_dir(target_root) / PROGRESS_ARCHIVE_DIR


def get_migration_log_path(target_root: Path) -> Path:
    return get_state_dir(target_root) / MIGRATION_LOG_JSON


def get_architecture_path(target_root: Path) -> Path:
    return get_architecture_dir(target_root) / ARCHITECTURE_MD


def get_complexity_cache_path(target_root: Path) -> Path:
    return get_cache_dir(target_root) / COMPLEXITY_CACHE_JSON


def ensure_tracker_layout(target_root: Path) -> None:
    for directory in (
        get_state_dir(target_root),
        get_plans_dir(target_root),
        get_testing_dir(target_root),
        get_architecture_dir(target_root),
        get_cache_dir(target_root),
        get_progress_archive_dir(target_root),
    ):
        directory.mkdir(parents=True, exist_ok=True)


def rel_progress_path(filename: str) -> str:
    return f"docs/{PROG_DOCS_DIRNAME}/state/{filename}"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _deep_replace_paths(value: Any) -> Any:
    if isinstance(value, str):
        replacements = (
            (LEGACY_PLAN_PREFIX, PLAN_PREFIX),
            (OLD_TESTING_PREFIX, NEW_TESTING_PREFIX),
            (".claude/architecture.md", "docs/progress-tracker/architecture/architecture.md"),
            (".claude/progress.json", "docs/progress-tracker/state/progress.json"),
            (".claude/checkpoints.json", "docs/progress-tracker/state/checkpoints.json"),
            (".claude/project_memory.json", "docs/progress-tracker/state/project_memory.json"),
        )
        out = value
        for old, new in replacements:
            out = out.replace(old, new)
        return out
    if isinstance(value, list):
        return [_deep_replace_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: _deep_replace_paths(item) for key, item in value.items()}
    return value


def _rewrite_json_file_paths(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    rewritten = _deep_replace_paths(payload)
    if rewritten == payload:
        return False
    path.write_text(json.dumps(rewritten, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def _unique_conflict_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 10000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return parent / f"{stem}-{timestamp}{suffix}"


def _move_with_conflict(
    src: Path,
    dst: Path,
    conflict_root: Path,
    operations: List[Dict[str, str]],
    conflicts: List[Dict[str, str]],
) -> None:
    if not src.exists() or not src.is_file():
        return
    _ensure_parent(dst)
    if dst.exists():
        conflict_target = _unique_conflict_target(conflict_root / src.name)
        _ensure_parent(conflict_target)
        shutil.move(str(src), str(conflict_target))
        conflicts.append({"from": str(src), "to": str(conflict_target)})
        return
    shutil.move(str(src), str(dst))
    operations.append({"from": str(src), "to": str(dst)})


def _move_tree_contents(
    src_dir: Path,
    dst_dir: Path,
    conflict_root: Path,
    operations: List[Dict[str, str]],
    conflicts: List[Dict[str, str]],
) -> None:
    if not src_dir.exists() or not src_dir.is_dir():
        return
    for file_path in sorted(src_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(src_dir)
        dst = dst_dir / rel
        _move_with_conflict(file_path, dst, conflict_root / rel.parent, operations, conflicts)

    for directory in sorted(src_dir.rglob("*"), reverse=True):
        if directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                pass
    try:
        src_dir.rmdir()
    except OSError:
        pass


def _append_migration_log(target_root: Path, entry: Dict[str, Any]) -> None:
    log_path = get_migration_log_path(target_root)
    existing: List[Dict[str, Any]] = []
    if log_path.exists():
        try:
            loaded = json.loads(log_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = [item for item in loaded if isinstance(item, dict)]
        except Exception:
            existing = []
    existing.append(entry)
    _ensure_parent(log_path)
    log_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_storage_migrated(target_root: Path) -> Dict[str, Any]:
    """
    Perform one-time migration from legacy `.claude` and `docs/plans|testing`.

    No legacy read fallback is used after migration. This function is idempotent.
    """
    ensure_tracker_layout(target_root)
    new_progress_path = get_progress_json_path(target_root)

    if new_progress_path.exists():
        return {"migrated": False, "reason": "already_initialized", "operations": [], "conflicts": []}

    operations: List[Dict[str, str]] = []
    conflicts: List[Dict[str, str]] = []
    conflict_root = get_state_dir(target_root) / "legacy_conflicts" / datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    legacy_claude = target_root / LEGACY_CLAUDE_DIR

    file_moves = [
        (legacy_claude / PROGRESS_JSON, get_progress_json_path(target_root)),
        (legacy_claude / PROGRESS_MD, get_progress_md_path(target_root)),
        (legacy_claude / CHECKPOINTS_JSON, get_checkpoints_path(target_root)),
        (legacy_claude / PROJECT_MEMORY_JSON, get_project_memory_path(target_root)),
        (legacy_claude / ARCHITECTURE_MD, get_architecture_path(target_root)),
    ]

    for src, dst in file_moves:
        _move_with_conflict(src, dst, conflict_root, operations, conflicts)

    legacy_docs = target_root / "docs"
    _move_tree_contents(
        legacy_docs / "plans",
        get_plans_dir(target_root),
        conflict_root / "plans",
        operations,
        conflicts,
    )
    _move_tree_contents(
        legacy_docs / "testing",
        get_testing_dir(target_root),
        conflict_root / "testing",
        operations,
        conflicts,
    )

    _rewrite_json_file_paths(get_progress_json_path(target_root))
    _rewrite_json_file_paths(get_checkpoints_path(target_root))

    migrated = bool(operations or conflicts)
    entry = {
        "timestamp": utc_now_iso(),
        "target_root": str(target_root),
        "status": "migrated" if migrated else "noop",
        "operations": operations,
        "conflicts": conflicts,
    }
    _append_migration_log(target_root, entry)

    return {"migrated": migrated, "operations": operations, "conflicts": conflicts}
