#!/usr/bin/env python3
"""Project memory data layer for progress-tracker.

This module intentionally keeps only data concerns:
- Read/write `.claude/project_memory.json`
- Fingerprint-based idempotent writes
- Retention policies
- Corruption recovery with backup

No semantic similarity algorithm is implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_CLAUDE_DIR = ".claude"
PROJECT_MEMORY_JSON = "project_memory.json"
SCHEMA_VERSION = "1.0"
DEFAULT_MAX_SYNC_HISTORY = 50
DEFAULT_MAX_REJECTED_FINGERPRINTS = 500


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 with trailing Z."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_memory() -> Dict[str, Any]:
    now = utc_now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "next_capability_seq": 1,
        "last_synced_commit": None,
        "capabilities": [],
        "rejected_fingerprints": [],
        "sync_history": [],
        "limits": {
            "max_sync_history": DEFAULT_MAX_SYNC_HISTORY,
            "max_rejected_fingerprints": DEFAULT_MAX_REJECTED_FINGERPRINTS,
        },
    }


def find_project_root() -> Path:
    """Find project root via git root, `.claude` parents, then cwd."""
    cwd = Path.cwd()

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except Exception:
        pass

    current = cwd
    while current != current.parent:
        if (current / DEFAULT_CLAUDE_DIR).exists():
            return current
        current = current.parent
    return cwd


def get_memory_path(path: Optional[Path] = None) -> Path:
    """Resolve project memory path."""
    if path is not None:
        return path
    return find_project_root() / DEFAULT_CLAUDE_DIR / PROJECT_MEMORY_JSON


def normalize_text(value: Any) -> str:
    """Normalize text for stable hashing."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def compute_fingerprint(title: Any, commit_hash: Any = "", feature_id: Any = "") -> str:
    """Compute capability fingerprint using SHA1 and return first 16 hex chars."""
    normalized_title = normalize_text(title)
    normalized_commit = str(commit_hash or "").strip()
    normalized_feature_id = "" if feature_id is None else str(feature_id)
    raw = f"{normalized_title}|{normalized_commit}|{normalized_feature_id}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return digest[:16]


def parse_index_selection(selection: str, total: int) -> List[int]:
    """Parse `1,3,5-7` style selection into sorted unique 0-based indexes."""
    if total < 0:
        raise ValueError("total must be >= 0")
    if not selection or not selection.strip():
        return []

    selected: set[int] = set()
    tokens = [item.strip() for item in selection.split(",") if item.strip()]
    if not tokens:
        return []

    for token in tokens:
        if "-" in token:
            parts = token.split("-", 1)
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise ValueError(f"Invalid range token: {token}")
            start = int(parts[0])
            end = int(parts[1])
            if start > end:
                raise ValueError(f"Range start > end: {token}")
            if start < 1 or end > total:
                raise ValueError(f"Range out of bounds: {token}")
            for value in range(start, end + 1):
                selected.add(value - 1)
            continue

        if not token.isdigit():
            raise ValueError(f"Invalid index token: {token}")
        index = int(token)
        if index < 1 or index > total:
            raise ValueError(f"Index out of bounds: {token}")
        selected.add(index - 1)

    return sorted(selected)


def _ensure_list(data: Dict[str, Any], key: str) -> None:
    value = data.get(key)
    if not isinstance(value, list):
        data[key] = []


def _normalize_limits(data: Dict[str, Any]) -> None:
    limits = data.get("limits")
    if not isinstance(limits, dict):
        limits = {}
        data["limits"] = limits

    max_sync_history = limits.get("max_sync_history")
    if not isinstance(max_sync_history, int) or max_sync_history <= 0:
        limits["max_sync_history"] = DEFAULT_MAX_SYNC_HISTORY

    max_rejected = limits.get("max_rejected_fingerprints")
    if not isinstance(max_rejected, int) or max_rejected <= 0:
        limits["max_rejected_fingerprints"] = DEFAULT_MAX_REJECTED_FINGERPRINTS


def _normalize_memory_shape(data: Dict[str, Any]) -> Dict[str, Any]:
    defaults = _default_memory()

    if not isinstance(data.get("schema_version"), str):
        data["schema_version"] = defaults["schema_version"]

    if not isinstance(data.get("created_at"), str) or not data.get("created_at"):
        data["created_at"] = defaults["created_at"]

    if not isinstance(data.get("updated_at"), str) or not data.get("updated_at"):
        data["updated_at"] = defaults["updated_at"]

    if not isinstance(data.get("next_capability_seq"), int) or data["next_capability_seq"] < 1:
        data["next_capability_seq"] = 1

    if "last_synced_commit" not in data:
        data["last_synced_commit"] = None
    elif data["last_synced_commit"] is not None and not isinstance(
        data["last_synced_commit"], str
    ):
        data["last_synced_commit"] = str(data["last_synced_commit"])

    _ensure_list(data, "capabilities")
    _ensure_list(data, "rejected_fingerprints")
    _ensure_list(data, "sync_history")
    _normalize_limits(data)
    return data


def _backup_corrupted_memory(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{PROJECT_MEMORY_JSON}.corrupt.{timestamp}")
    try:
        shutil.copy2(path, backup_path)
    except OSError:
        return None
    return backup_path


def load_memory(path: Optional[Path] = None) -> Tuple[Dict[str, Any], bool, Optional[Path]]:
    """Load memory JSON with corruption recovery."""
    memory_path = get_memory_path(path)
    if not memory_path.exists():
        return _default_memory(), False, None

    try:
        with open(memory_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise json.JSONDecodeError("Root JSON value must be an object", "", 0)
        return _normalize_memory_shape(data), False, None
    except (json.JSONDecodeError, OSError):
        backup_path = _backup_corrupted_memory(memory_path)
        recovered = _default_memory()
        save_memory(recovered, memory_path)
        return recovered, True, backup_path


def save_memory(data: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Save memory JSON atomically."""
    memory_path = get_memory_path(path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = _normalize_memory_shape(dict(data))
    normalized["schema_version"] = SCHEMA_VERSION
    if not normalized.get("created_at"):
        normalized["created_at"] = utc_now_iso()
    normalized["updated_at"] = utc_now_iso()

    temp_path = memory_path.parent / (
        f".{memory_path.name}.tmp.{os.getpid()}.{int(datetime.now(timezone.utc).timestamp())}"
    )
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=2, ensure_ascii=False)
    os.replace(temp_path, memory_path)


def _get_source_field(payload: Dict[str, Any], key: str, default: Any = None) -> Any:
    source = payload.get("source")
    if isinstance(source, dict) and key in source:
        return source.get(key)
    return payload.get(key, default)


def _normalize_tags(raw_tags: Any) -> List[str]:
    if not isinstance(raw_tags, list):
        return []
    tags: List[str] = []
    seen: set[str] = set()
    for item in raw_tags:
        text = str(item).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(text)
    return tags


def _normalize_confidence(raw_confidence: Any, default: float = 1.0) -> float:
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = default
    if confidence < 0.0:
        return 0.0
    if confidence > 1.0:
        return 1.0
    return confidence


def _prepare_capability(
    payload: Dict[str, Any], next_capability_seq: int, default_origin: str
) -> Dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("capability title is required")

    summary = str(payload.get("summary", "")).strip()
    tags = _normalize_tags(payload.get("tags", []))

    commit_hash = _get_source_field(
        payload, "commit_hash", payload.get("source_commit", payload.get("commit_hash", ""))
    )
    feature_id = _get_source_field(payload, "feature_id", payload.get("feature_id", 0))
    commit_range = _get_source_field(payload, "commit_range", payload.get("commit_range", ""))
    origin = _get_source_field(payload, "origin", default_origin)

    fingerprint = str(payload.get("fingerprint", "")).strip()
    if not fingerprint:
        fingerprint = compute_fingerprint(title, commit_hash, feature_id)

    confidence = _normalize_confidence(payload.get("confidence", 1.0), default=1.0)
    now = utc_now_iso()

    capability = {
        "cap_id": f"CAP-{next_capability_seq:03d}",
        "fingerprint": fingerprint,
        "title": title,
        "summary": summary,
        "tags": tags,
        "confidence": confidence,
        "source": {
            "origin": str(origin or default_origin),
            "feature_id": feature_id if feature_id is not None else 0,
            "commit_hash": str(commit_hash or ""),
            "commit_range": str(commit_range or ""),
        },
        "created_at": now,
        "updated_at": now,
    }
    return capability


def append_capability(data: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Append one capability with idempotent dedupe by fingerprint."""
    capabilities = data.get("capabilities", [])
    existing_fingerprints = {
        item.get("fingerprint") for item in capabilities if isinstance(item, dict)
    }

    draft = _prepare_capability(payload, data.get("next_capability_seq", 1), "prog_done")
    fingerprint = draft["fingerprint"]

    if fingerprint in existing_fingerprints:
        return {
            "status": "deduped",
            "fingerprint": fingerprint,
            "capability": None,
        }

    capabilities.append(draft)
    data["capabilities"] = capabilities
    data["next_capability_seq"] = int(data.get("next_capability_seq", 1)) + 1

    return {
        "status": "inserted",
        "fingerprint": fingerprint,
        "capability": draft,
    }


def _trim_list(values: List[Any], max_items: int) -> List[Any]:
    if max_items <= 0:
        return []
    if len(values) <= max_items:
        return values
    return values[-max_items:]


def batch_upsert_capabilities(
    data: Dict[str, Any], payloads: Sequence[Dict[str, Any]], sync_meta: Dict[str, Any]
) -> Dict[str, Any]:
    """Batch upsert capabilities and update sync history."""
    inserted = 0
    deduped = 0
    invalid = 0
    inserted_capabilities: List[Dict[str, Any]] = []

    for payload in payloads:
        if not isinstance(payload, dict):
            invalid += 1
            continue
        try:
            result = append_capability(data, payload)
        except ValueError:
            invalid += 1
            continue

        if result["status"] == "inserted":
            inserted += 1
            inserted_capabilities.append(result["capability"])
        else:
            deduped += 1

    sync_id = str(sync_meta.get("sync_id") or f"sync-{int(datetime.now(timezone.utc).timestamp())}")
    sync_entry = {
        "sync_id": sync_id,
        "timestamp": utc_now_iso(),
        "total_candidates": len(payloads),
        "accepted_count": len(payloads),
        "inserted_count": inserted,
        "deduped_count": deduped,
        "invalid_count": invalid,
        "rejected_count": int(sync_meta.get("rejected_count", 0) or 0),
        "commit_range": str(sync_meta.get("commit_range", "")),
        "last_synced_commit": sync_meta.get("last_synced_commit"),
    }

    history = data.get("sync_history", [])
    history.append(sync_entry)
    max_sync_history = data.get("limits", {}).get("max_sync_history", DEFAULT_MAX_SYNC_HISTORY)
    data["sync_history"] = _trim_list(history, int(max_sync_history))

    if sync_meta.get("last_synced_commit"):
        data["last_synced_commit"] = str(sync_meta["last_synced_commit"])

    return {
        "sync_id": sync_id,
        "inserted_count": inserted,
        "deduped_count": deduped,
        "invalid_count": invalid,
        "inserted_capabilities": inserted_capabilities,
        "sync_entry": sync_entry,
    }


def _extract_fingerprint_from_rejection(candidate: Any) -> Optional[str]:
    if isinstance(candidate, str):
        text = candidate.strip()
        return text or None

    if not isinstance(candidate, dict):
        return None

    fingerprint = str(candidate.get("fingerprint", "")).strip()
    if fingerprint:
        return fingerprint

    title = candidate.get("title") or candidate.get("summary")
    if not title:
        return None

    source = candidate.get("source", {})
    commit_hash = candidate.get("source_commit") or candidate.get("commit_hash")
    feature_id = candidate.get("feature_id")
    if isinstance(source, dict):
        commit_hash = source.get("commit_hash", commit_hash)
        feature_id = source.get("feature_id", feature_id)
    return compute_fingerprint(title, commit_hash, feature_id)


def register_rejections(
    data: Dict[str, Any], payloads: Sequence[Any], sync_id: Optional[str] = None
) -> Dict[str, Any]:
    """Register rejected candidate fingerprints with retention control."""
    fingerprints = data.get("rejected_fingerprints", [])
    existing = {str(item) for item in fingerprints}

    added: List[str] = []
    invalid = 0
    for candidate in payloads:
        fingerprint = _extract_fingerprint_from_rejection(candidate)
        if not fingerprint:
            invalid += 1
            continue
        if fingerprint in existing:
            continue
        fingerprints.append(fingerprint)
        existing.add(fingerprint)
        added.append(fingerprint)

    max_rejected = data.get("limits", {}).get(
        "max_rejected_fingerprints", DEFAULT_MAX_REJECTED_FINGERPRINTS
    )
    data["rejected_fingerprints"] = _trim_list(fingerprints, int(max_rejected))

    if sync_id:
        history = data.get("sync_history", [])
        for entry in reversed(history):
            if isinstance(entry, dict) and str(entry.get("sync_id")) == str(sync_id):
                entry["rejected_count"] = len(payloads)
                break

    return {
        "sync_id": sync_id,
        "added_count": len(added),
        "invalid_count": invalid,
        "added_fingerprints": added,
    }


def _parse_json_arg(raw_value: str, expected_type: type, arg_name: str) -> Any:
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{arg_name} is not valid JSON: {exc}") from exc
    if not isinstance(value, expected_type):
        expected_name = expected_type.__name__
        raise ValueError(f"{arg_name} must decode to {expected_name}")
    return value


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Project memory data manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("read", help="Read project memory JSON")

    append_parser = subparsers.add_parser("append", help="Append one capability")
    append_parser.add_argument("--payload-json", required=True, help="Capability JSON object")

    batch_parser = subparsers.add_parser("batch-upsert", help="Batch upsert capabilities")
    batch_parser.add_argument("--payload-json", required=True, help="JSON array of capabilities")
    batch_parser.add_argument(
        "--sync-meta-json",
        default="{}",
        help="JSON object containing sync metadata",
    )

    reject_parser = subparsers.add_parser("register-rejections", help="Register rejected candidates")
    reject_parser.add_argument("--payload-json", required=True, help="JSON array of rejected candidates")
    reject_parser.add_argument("--sync-id", default=None, help="Sync ID for history linkage")

    selection_parser = subparsers.add_parser(
        "parse-selection", help="Parse `1,3,5-7` style selection into indexes"
    )
    selection_parser.add_argument("--selection", required=True, help="Raw selection string")
    selection_parser.add_argument("--total", required=True, type=int, help="Total candidate count")

    args = parser.parse_args(argv)

    try:
        if args.command == "parse-selection":
            selected = parse_index_selection(args.selection, args.total)
            selected_numbers = [item + 1 for item in selected]
            rejected_numbers = [index for index in range(1, args.total + 1) if index not in selected_numbers]
            _print_json(
                {
                    "selected_indices": selected,
                    "selected_numbers": selected_numbers,
                    "rejected_numbers": rejected_numbers,
                }
            )
            return 0

        memory, recovered, backup_path = load_memory()
        if recovered:
            warning = (
                f"[project_memory] Corrupted file recovered."
                f" Backup: {backup_path}" if backup_path else "[project_memory] Corrupted file recovered."
            )
            print(warning, file=sys.stderr)

        if args.command == "read":
            _print_json(memory)
            return 0

        if args.command == "append":
            payload = _parse_json_arg(args.payload_json, dict, "--payload-json")
            result = append_capability(memory, payload)
            if result["status"] == "inserted":
                save_memory(memory)
            _print_json(result)
            return 0

        if args.command == "batch-upsert":
            payloads = _parse_json_arg(args.payload_json, list, "--payload-json")
            sync_meta = _parse_json_arg(args.sync_meta_json, dict, "--sync-meta-json")
            result = batch_upsert_capabilities(memory, payloads, sync_meta)
            save_memory(memory)
            _print_json(result)
            return 0

        if args.command == "register-rejections":
            payloads = _parse_json_arg(args.payload_json, list, "--payload-json")
            result = register_rejections(memory, payloads, sync_id=args.sync_id)
            save_memory(memory)
            _print_json(result)
            return 0

        parser.print_help()
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
