#!/usr/bin/env python3
"""Append-only sprint artifact ledger for resumable sessions."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SprintLedgerError(Exception):
    """Raised when sprint ledger contract validation fails."""


VALID_PHASES = ("plan", "implementation", "evaluation", "handoff")


@dataclass
class SprintRecord:
    timestamp: str
    feature_id: int
    phase: str
    artifact_path: str
    metadata: Dict[str, Any]

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_ledger_path() -> Path:
    try:
        import progress_manager

        return progress_manager.get_progress_dir() / "sprint_ledger.jsonl"
    except Exception:
        return Path.cwd() / "docs" / "progress-tracker" / "state" / "sprint_ledger.jsonl"


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace file contents using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _append_json_line_serialized(
    *,
    path: Path,
    line: str,
    use_progress_lock: bool,
) -> None:
    """Append one line with optional progress lock and atomic replace semantics."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def _append_without_lock() -> None:
        existing = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        _atomic_write_text(path, existing + line + "\n")

    if not use_progress_lock:
        _append_without_lock()
        return

    try:
        import progress_manager

        with progress_manager.progress_transaction():
            _append_without_lock()
    except Exception as exc:
        raise SprintLedgerError(f"failed serialized ledger append: {exc}") from exc


def _validate_phase(phase: str) -> None:
    if phase not in VALID_PHASES:
        raise SprintLedgerError(f"phase {phase!r} not in {VALID_PHASES}")


def _find_feature(data: Dict[str, Any], feature_id: int) -> Optional[Dict[str, Any]]:
    """Locate feature by id from progress payload."""
    features = data.get("features")
    if not isinstance(features, list):
        return None
    for item in features:
        if isinstance(item, dict) and item.get("id") == feature_id:
            return item
    return None


def record(
    *,
    feature_id: int,
    phase: str,
    artifact_path: str,
    metadata: Optional[Dict[str, Any]] = None,
    ledger_path: Optional[Path] = None,
) -> SprintRecord:
    """Append one immutable sprint artifact record to jsonl ledger."""
    _validate_phase(phase)
    if not isinstance(feature_id, int):
        raise SprintLedgerError("feature_id must be int")
    if not str(artifact_path).strip():
        raise SprintLedgerError("artifact_path must be non-empty")

    path = ledger_path or _default_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = SprintRecord(
        timestamp=_utc_now_z(),
        feature_id=feature_id,
        phase=phase,
        artifact_path=str(artifact_path),
        metadata=dict(metadata or {}),
    )
    _append_json_line_serialized(
        path=path,
        line=rec.to_json_line(),
        use_progress_lock=ledger_path is None,
    )
    return rec


def list_sprint_records(
    *,
    feature_id: Optional[int] = None,
    phase: Optional[str] = None,
    ledger_path: Optional[Path] = None,
) -> List[SprintRecord]:
    """Read ledger records with optional feature/phase filtering."""
    if phase is not None:
        _validate_phase(phase)
    path = ledger_path or _default_ledger_path()
    if not path.exists():
        return []

    out: List[SprintRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SprintLedgerError(f"invalid jsonl at line {line_no}: {exc}") from exc
            if feature_id is not None and payload.get("feature_id") != feature_id:
                continue
            if phase is not None and payload.get("phase") != phase:
                continue
            try:
                out.append(SprintRecord(**payload))
            except TypeError as exc:
                raise SprintLedgerError(f"invalid sprint record shape at line {line_no}: {exc}") from exc
    return out


def read_latest(
    *,
    feature_id: int,
    phase: str,
    ledger_path: Optional[Path] = None,
) -> Optional[SprintRecord]:
    """Return most recent record for feature+phase pair."""
    records = list_sprint_records(feature_id=feature_id, phase=phase, ledger_path=ledger_path)
    if not records:
        return None
    return records[-1]


def require_sprint_contract(feature: Dict[str, Any]) -> None:
    """Ensure sprint contract is present before execution gatekeeping."""
    sprint_contract = feature.get("sprint_contract")
    if not isinstance(sprint_contract, dict):
        raise SprintLedgerError("sprint_contract missing")

    scope = sprint_contract.get("scope")
    done_criteria = sprint_contract.get("done_criteria")
    test_plan = sprint_contract.get("test_plan")

    missing: List[str] = []
    if not str(scope or "").strip():
        missing.append("scope")
    if not isinstance(done_criteria, list) or not any(str(item).strip() for item in done_criteria):
        missing.append("done_criteria")
    if not isinstance(test_plan, list) or not any(str(item).strip() for item in test_plan):
        missing.append("test_plan")

    if missing:
        raise SprintLedgerError(
            "sprint_contract incomplete: missing " + ", ".join(missing)
        )


def mark_handoff(
    *,
    feature_id: int,
    from_phase: str,
    to_phase: str,
    artifact_path: str,
    ledger_path: Optional[Path] = None,
) -> SprintRecord:
    """Persist feature handoff data and append a handoff artifact record."""
    _validate_phase(from_phase)
    _validate_phase(to_phase)
    if not str(artifact_path).strip():
        raise SprintLedgerError("artifact_path must be non-empty")

    import progress_manager  # Local import to avoid cycle with progress_manager module import.

    with progress_manager.progress_transaction():
        data = progress_manager.load_progress_json()
        if not isinstance(data, dict):
            raise SprintLedgerError("progress tracking not initialized")

        feature = _find_feature(data, feature_id)
        if feature is None:
            raise SprintLedgerError(f"feature {feature_id} not found")

        feature["handoff"] = {
            "from_phase": from_phase,
            "to_phase": to_phase,
            "artifact_path": artifact_path,
            "created_at": _utc_now_z(),
        }
        progress_manager.save_progress_json(data)
        return record(
            feature_id=feature_id,
            phase="handoff",
            artifact_path=artifact_path,
            metadata={"from": from_phase, "to": to_phase},
            ledger_path=ledger_path,
        )
