"""
summary_projector.py — Status summary projection read path.

Extracted from progress_manager.py (F20 Round 1 modularisation).

This module owns the status/summary projection cluster:
- Source fingerprinting and drift detection
- Summary core field computation
- Projection cache build/load with self-healing
- Relative time formatting

Public entry point:
  load_status_summary_projection(project_root, *, apply_schema_defaults_fn, load_checkpoints_fn,
                                  validate_plan_path_fn, validate_plan_document_fn)

All injected callbacks (suffixed *_fn) are passed in from the progress_manager facade
to avoid importing progress_manager (no reverse dependency).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from prog_paths import (
    ensure_storage_migrated,
    ensure_tracker_layout,
    get_checkpoints_path,
    get_progress_json_path,
    get_state_dir,
    rel_progress_path,
    find_project_root,
)
from state_io import _atomic_write_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (mirrors of progress_manager constants; kept here to avoid import)
# ---------------------------------------------------------------------------
PROGRESS_JSON = "progress.json"
CHECKPOINTS_JSON = "checkpoints.json"
STATUS_SUMMARY_FILE = "status_summary.v1.json"
STATUS_SUMMARY_LEGACY_FILE = "status_summary.json"
STATUS_SUMMARY_SCHEMA_VERSION = "status_summary.v1"
STATUS_SUMMARY_CORE_FIELDS: Tuple[str, ...] = (
    "progress",
    "next_action",
    "plan_health",
    "risk_blocker",
    "recent_snapshot",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    """Return current UTC timestamp in ISO 8601 format with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    """Read JSON object from disk and return None on parse/shape errors."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _status_source_snapshot(path: Path, rel_path: str) -> Dict[str, Any]:
    """Return lightweight source-file fingerprint for drift detection."""
    if not path.exists():
        return {
            "path": rel_path,
            "exists": False,
            "mtime_ns": None,
            "size": None,
        }
    stat = path.stat()
    return {
        "path": rel_path,
        "exists": True,
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
    }


def _status_summary_source_fingerprint(target_root: Path) -> Dict[str, Any]:
    """Collect input fingerprints for progress/checkpoints source files."""
    progress_path = get_progress_json_path(target_root)
    checkpoints_path = get_checkpoints_path(target_root)
    return {
        "progress": _status_source_snapshot(
            progress_path, rel_progress_path(PROGRESS_JSON)
        ),
        "checkpoints": _status_source_snapshot(
            checkpoints_path, rel_progress_path(CHECKPOINTS_JSON)
        ),
    }


def _load_progress_data_for_summary(
    progress_path: Path,
    *,
    apply_schema_defaults_fn: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Load progress payload for summary projection with graceful fallback."""
    payload = _read_json_dict(progress_path)
    if payload is None:
        return {"features": [], "current_feature_id": None, "bugs": []}
    apply_schema_defaults_fn(payload)
    return payload


def _format_relative_time_for_summary(iso_timestamp: Optional[str]) -> str:
    """Format ISO timestamp into compact relative text for status summary."""
    if not iso_timestamp:
        return "暂无快照"
    try:
        timestamp = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - timestamp
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "刚刚"
        if total_seconds >= 86400:
            return f"{total_seconds // 86400} 天前"
        if total_seconds >= 3600:
            return f"{total_seconds // 3600} 小时前"
        if total_seconds >= 60:
            return f"{total_seconds // 60} 分钟前"
        return "刚刚"
    except Exception:
        return iso_timestamp


def _normalize_feature_stage_for_summary(feature: Dict[str, Any]) -> str:
    """Normalize development_stage for summary rendering."""
    if feature.get("completed", False):
        return "completed"
    stage = feature.get("development_stage")
    if stage in {"planning", "developing", "completed"}:
        return stage
    return "developing"


def _stage_label_for_summary(stage: Optional[str]) -> Optional[str]:
    """Localize status stage labels used by summary payload."""
    if stage is None:
        return None
    return {
        "planning": "规划中",
        "developing": "开发中",
        "completed": "已完成",
        "pending": "待开始",
    }.get(stage, "未知")


def _determine_next_action_for_summary(
    features: List[Dict[str, Any]], progress_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Build next_action summary field from active/pending feature state."""
    current_id = progress_data.get("current_feature_id")
    if current_id is not None:
        feature = next(
            (
                f
                for f in features
                if isinstance(f, dict) and f.get("id") == current_id
            ),
            None,
        )
        if feature:
            stage = _normalize_feature_stage_for_summary(feature)
            return {
                "type": "feature",
                "feature_id": current_id,
                "feature_name": feature.get("name", "Unknown"),
                "development_stage": stage,
                "stage_label": _stage_label_for_summary(stage),
            }

    pending = [
        f for f in features if isinstance(f, dict) and not f.get("completed", False)
    ]
    if pending:
        next_feature = pending[0]
        return {
            "type": "feature",
            "feature_id": next_feature.get("id"),
            "feature_name": next_feature.get("name", "Unknown"),
            "development_stage": "pending",
            "stage_label": _stage_label_for_summary("pending"),
        }

    return {
        "type": "none",
        "feature_id": None,
        "feature_name": "无待办功能",
        "development_stage": None,
        "stage_label": None,
    }


def _check_plan_health_for_summary(
    progress_data: Dict[str, Any],
    target_root: Path,
    *,
    validate_plan_path_fn: Callable[..., Dict[str, Any]],
    validate_plan_document_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate active plan path/document health for summary projection."""
    workflow_state = progress_data.get("workflow_state")
    if not isinstance(workflow_state, dict) or not workflow_state.get("plan_path"):
        return {"status": "N/A", "plan_path": None, "message": "无活跃计划"}

    plan_path = str(workflow_state.get("plan_path"))
    try:
        path_result = validate_plan_path_fn(
            plan_path, require_exists=True, target_root=target_root
        )
        if not path_result["valid"]:
            return {
                "status": "WARN",
                "plan_path": plan_path,
                "message": path_result["error"],
            }

        doc_result = validate_plan_document_fn(plan_path, target_root=target_root)
        if not doc_result["valid"]:
            missing = ", ".join(doc_result.get("missing_sections", []))
            return {
                "status": "INVALID",
                "plan_path": plan_path,
                "message": f"缺少必需章节: {missing}" if missing else "计划文档验证失败",
            }

        return {
            "status": "OK",
            "plan_path": plan_path,
            "message": "计划文件完整且符合规范",
        }
    except Exception as exc:
        return {
            "status": "WARN",
            "plan_path": plan_path,
            "message": f"验证失败: {exc}",
        }


def _check_risk_blocker_for_summary(progress_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate high-priority/blocked bug signals for status summary."""
    bugs = progress_data.get("bugs", [])
    if not isinstance(bugs, list):
        bugs = []

    high_priority = [
        bug
        for bug in bugs
        if isinstance(bug, dict)
        and bug.get("priority") == "high"
        and bug.get("status") != "fixed"
    ]
    blocked = [
        bug for bug in bugs if isinstance(bug, dict) and bug.get("status") == "blocked"
    ]

    if high_priority or blocked:
        return {
            "has_risk": True,
            "high_priority_bugs": len(high_priority),
            "blocked_count": len(blocked),
            "message": f"{len(high_priority)} 个高优先级 bug",
        }

    return {
        "has_risk": False,
        "high_priority_bugs": 0,
        "blocked_count": 0,
        "message": "正常",
    }


def _load_recent_snapshot_for_summary(
    checkpoints_data: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build recent_snapshot field from checkpoints payload."""
    if not isinstance(checkpoints_data, dict):
        return {"exists": False, "timestamp": None, "relative_time": "暂无快照"}

    last_time = checkpoints_data.get("last_checkpoint_at")
    if not last_time:
        return {"exists": False, "timestamp": None, "relative_time": "暂无快照"}

    return {
        "exists": True,
        "timestamp": last_time,
        "relative_time": _format_relative_time_for_summary(last_time),
    }


def _build_status_summary_core(
    progress_data: Dict[str, Any],
    checkpoints_data: Dict[str, Any],
    target_root: Path,
    *,
    validate_plan_path_fn: Callable[..., Dict[str, Any]],
    validate_plan_document_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute the shared status summary core fields."""
    features_raw = progress_data.get("features", [])
    features = [item for item in features_raw if isinstance(item, dict)]
    completed = sum(1 for feature in features if feature.get("completed", False))
    total = len(features)
    percentage = int((completed / total) * 100) if total > 0 else 0

    return {
        "progress": {
            "completed": completed,
            "total": total,
            "percentage": percentage,
        },
        "next_action": _determine_next_action_for_summary(features, progress_data),
        "plan_health": _check_plan_health_for_summary(
            progress_data,
            target_root,
            validate_plan_path_fn=validate_plan_path_fn,
            validate_plan_document_fn=validate_plan_document_fn,
        ),
        "risk_blocker": _check_risk_blocker_for_summary(progress_data),
        "recent_snapshot": _load_recent_snapshot_for_summary(checkpoints_data),
    }


def _extract_projection_source_fingerprint(
    projection: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Extract persisted inputs fingerprint from projection payload."""
    inputs = projection.get("inputs")
    return inputs if isinstance(inputs, dict) else None


def _projection_has_required_core_fields(projection: Dict[str, Any]) -> bool:
    """Check whether projection carries all required summary fields."""
    return all(field in projection for field in STATUS_SUMMARY_CORE_FIELDS)


def _projection_needs_rebuild(
    projection: Optional[Dict[str, Any]],
    current_inputs: Dict[str, Any],
) -> bool:
    """Determine whether cached projection is stale or malformed."""
    if not isinstance(projection, dict):
        return True
    if projection.get("schema_version") != STATUS_SUMMARY_SCHEMA_VERSION:
        return True
    if not _projection_has_required_core_fields(projection):
        return True
    persisted_inputs = _extract_projection_source_fingerprint(projection)
    if persisted_inputs != current_inputs:
        return True
    return False


def _legacy_summary_migration_info(legacy_path: Path) -> Optional[Dict[str, Any]]:
    """Read legacy summary metadata for migration traceability."""
    legacy_payload = _read_json_dict(legacy_path)
    if legacy_payload is None:
        return None
    from_version = legacy_payload.get("schema_version")
    if not isinstance(from_version, str) or not from_version.strip():
        from_version = "unknown"
    return {
        "from_schema_version": from_version,
        "from_path": rel_progress_path(STATUS_SUMMARY_LEGACY_FILE),
        "migrated_at": _iso_now(),
    }


def _resolve_status_summary_target_root(project_root: Optional[str]) -> Path:
    """Resolve summary projection target root from optional explicit path."""
    if project_root is None:
        return find_project_root()
    root = Path(project_root).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root.resolve()


def get_status_summary_projection_path(project_root: Optional[str] = None) -> Path:
    """Return status summary projection path for the resolved target root."""
    target_root = _resolve_status_summary_target_root(project_root)
    return get_state_dir(target_root) / STATUS_SUMMARY_FILE


def _build_status_summary_projection(
    target_root: Path,
    current_inputs: Dict[str, Any],
    *,
    apply_schema_defaults_fn: Callable[[Dict[str, Any]], None],
    load_checkpoints_fn: Callable[..., Dict[str, Any]],
    validate_plan_path_fn: Callable[..., Dict[str, Any]],
    validate_plan_document_fn: Callable[..., Dict[str, Any]],
    migration_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Recompute and persist status summary projection for a target root."""
    progress_path = get_progress_json_path(target_root)
    checkpoints_path = get_checkpoints_path(target_root)
    projection_path = get_status_summary_projection_path(str(target_root))

    progress_data = _load_progress_data_for_summary(
        progress_path, apply_schema_defaults_fn=apply_schema_defaults_fn
    )
    checkpoints_data = load_checkpoints_fn(path=checkpoints_path)
    core = _build_status_summary_core(
        progress_data,
        checkpoints_data,
        target_root,
        validate_plan_path_fn=validate_plan_path_fn,
        validate_plan_document_fn=validate_plan_document_fn,
    )

    projection: Dict[str, Any] = {
        "schema_version": STATUS_SUMMARY_SCHEMA_VERSION,
        "projection_path": rel_progress_path(STATUS_SUMMARY_FILE),
        "updated_at": _iso_now(),
        "source": {
            "generator": "summary_projector.load_status_summary_projection",
            "progress_path": rel_progress_path(PROGRESS_JSON),
            "checkpoints_path": rel_progress_path(CHECKPOINTS_JSON),
        },
        "inputs": current_inputs,
        **core,
    }
    if migration_info:
        projection["migration"] = migration_info

    _atomic_write_text(
        projection_path,
        json.dumps(projection, indent=2, ensure_ascii=False),
    )
    return projection


def load_status_summary_projection(
    project_root: Optional[str] = None,
    *,
    apply_schema_defaults_fn: Callable[[Dict[str, Any]], None],
    load_checkpoints_fn: Callable[..., Dict[str, Any]],
    validate_plan_path_fn: Callable[..., Dict[str, Any]],
    validate_plan_document_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Load shared status summary projection with drift detection and self-healing.

    The projection is persisted at docs/progress-tracker/state/status_summary.v1.json
    and rebuilt automatically when source files drift, projection is missing/corrupt,
    or schema/core fields mismatch.

    Callbacks are injected to avoid importing progress_manager (no reverse dependency):
      apply_schema_defaults_fn   — progress_manager._apply_schema_defaults
      load_checkpoints_fn        — progress_manager.load_checkpoints
      validate_plan_path_fn      — progress_manager.validate_plan_path
      validate_plan_document_fn  — progress_manager.validate_plan_document
    """
    target_root = _resolve_status_summary_target_root(project_root)
    ensure_tracker_layout(target_root)
    ensure_storage_migrated(target_root)

    projection_path = get_status_summary_projection_path(str(target_root))
    legacy_path = get_state_dir(target_root) / STATUS_SUMMARY_LEGACY_FILE
    current_inputs = _status_summary_source_fingerprint(target_root)
    projection = _read_json_dict(projection_path)

    migration_info: Optional[Dict[str, Any]] = None
    if projection is None and legacy_path.exists():
        migration_info = _legacy_summary_migration_info(legacy_path)

    if _projection_needs_rebuild(projection, current_inputs):
        try:
            return _build_status_summary_projection(
                target_root=target_root,
                current_inputs=current_inputs,
                apply_schema_defaults_fn=apply_schema_defaults_fn,
                load_checkpoints_fn=load_checkpoints_fn,
                validate_plan_path_fn=validate_plan_path_fn,
                validate_plan_document_fn=validate_plan_document_fn,
                migration_info=migration_info,
            )
        except Exception as exc:
            logger.warning(f"Failed to persist status summary projection: {exc}")
            progress_data = _load_progress_data_for_summary(
                get_progress_json_path(target_root),
                apply_schema_defaults_fn=apply_schema_defaults_fn,
            )
            checkpoints_data = load_checkpoints_fn(
                path=get_checkpoints_path(target_root)
            )
            core = _build_status_summary_core(
                progress_data,
                checkpoints_data,
                target_root,
                validate_plan_path_fn=validate_plan_path_fn,
                validate_plan_document_fn=validate_plan_document_fn,
            )
            return {
                "schema_version": STATUS_SUMMARY_SCHEMA_VERSION,
                "projection_path": rel_progress_path(STATUS_SUMMARY_FILE),
                "updated_at": _iso_now(),
                "source": {
                    "generator": "summary_projector.load_status_summary_projection",
                    "progress_path": rel_progress_path(PROGRESS_JSON),
                    "checkpoints_path": rel_progress_path(CHECKPOINTS_JSON),
                },
                "inputs": current_inputs,
                "repair": {
                    "status": "degraded",
                    "reason": str(exc),
                },
                **core,
            }

    # projection is guaranteed dict and schema-valid by _projection_needs_rebuild.
    return projection  # type: ignore[return-value]
