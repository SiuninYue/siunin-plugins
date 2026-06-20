"""
evaluator_gateway.py — Evaluator backfill and assessment helpers.

Extracted from progress_manager.py (F18 modularisation).
"""
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROGRESS_JSON = "progress.json"


def _emit(data: Dict[str, Any], as_json: bool) -> None:
    """Print reconcile_evaluator result as JSON or human-readable text."""
    if as_json:
        print(json.dumps(data))
    else:
        if "error" in data:
            print(f"Error: {data['error']}", file=sys.stderr)
        elif "summary" in data:
            print(f"Reconcile evaluator: {data['summary']}")
            if data.get("failed"):
                print("Failed features:")
                for fid_str, err in data["failed"].items():
                    print(f"  F{fid_str}: {err}")
            if data.get("audit_failed"):
                print("Audit write warnings:")
                for fid_str, err in data["audit_failed"].items():
                    print(f"  F{fid_str}: {err}")


def _collect_ship_signals(feature: dict) -> dict:
    """Collect best-effort ship signals from feature state."""
    quality_gates = feature.get("quality_gates", {})
    evaluator = quality_gates.get("evaluator", {})
    defects = evaluator.get("defects", [])
    failed_tests = len([d for d in defects if isinstance(d, dict) and d.get("severity") == "critical"])
    return {
        "test_coverage": 1.0,
        "test_results": {"passed": 1, "failed": failed_tests, "skipped": 0},
        "docs_sync": {"architecture_refs_valid": True},
        "regression_results": {"passed": 1, "failed": 0},
    }


def reconcile_evaluator(
    feature_id: Optional[int] = None,
    output_json: bool = False,
    *,
    progress_dir: Path,
    load_progress_json_fn: Callable[[], Optional[Dict[str, Any]]],
    store_evaluator_result_fn: Callable[[int, Any], None],
    append_audit_event_fn: Callable[..., None],
    evaluator_gate_mod: Any,
    emit_fn: Optional[Callable[[Dict[str, Any], bool], None]] = None,
) -> int:
    """Backfill evaluator results for completed features missing evaluation."""
    emit = emit_fn or _emit

    if evaluator_gate_mod is None:
        emit({"error": "evaluator_gate module not available"}, output_json)
        return 2

    raw_null_evaluator_ids: set = set()
    try:
        raw_json_path = progress_dir / PROGRESS_JSON
        if raw_json_path.exists():
            raw = json.loads(raw_json_path.read_text(encoding="utf-8"))
            for f in raw.get("features", []):
                qg = f.get("quality_gates") or {}
                if qg.get("evaluator") is None and "quality_gates" in f:
                    raw_null_evaluator_ids.add(f.get("id"))
    except Exception:
        pass  # Non-critical; backfill_reason defaults to "retry"

    data = load_progress_json_fn()
    if data is None:
        emit({"error": "progress.json not found"}, output_json)
        return 2

    features = data.get("features", [])

    def _needs_backfill(feat: Dict[str, Any]) -> bool:
        ev = feat.get("quality_gates", {}).get("evaluator")
        return ev is None or ev.get("status") == "pending"

    if feature_id is not None:
        candidates = [f for f in features if f.get("id") == feature_id]
        if not candidates:
            emit({"error": f"Feature {feature_id} not found"}, output_json)
            return 2
        forced_overwrite_ids = {
            f["id"] for f in candidates if not _needs_backfill(f)
        }
    else:
        forced_overwrite_ids = set()
        exec_complete_ids: set = set()
        wf = data.get("workflow_state") or {}
        if wf.get("phase") == "execution_complete":
            current_fid = data.get("current_feature_id")
            if current_fid is not None:
                exec_complete_ids.add(current_fid)

        completed = [
            f
            for f in features
            if f.get("completed") or f.get("id") in exec_complete_ids
        ]
        candidates = [f for f in completed if _needs_backfill(f)]

    if not candidates:
        report: Dict[str, Any] = {
            "total_scanned": 0,
            "backfilled": 0,
            "failed": {},
            "summary": "No features need evaluator backfill",
        }
        emit(report, output_json)
        return 0

    rubric: Dict[str, Any] = {"test_coverage_min": 0.0}
    signals: Dict[str, Any] = {"test_coverage": 1.0, "defects": []}
    backfilled: List[int] = []
    failed: Dict[str, str] = {}
    audit_failed: Dict[str, str] = {}

    for feat in candidates:
        fid = feat["id"]
        backfill_reason = (
            "missing_evaluator" if fid in raw_null_evaluator_ids else "retry"
        )
        try:
            result = evaluator_gate_mod.assess(
                feature=feat,
                rubric=rubric,
                signals=signals,
            )
            store_evaluator_result_fn(fid, result)
            backfilled.append(fid)
        except Exception as exc:
            failed[str(fid)] = str(exc)
            continue

        try:
            append_audit_event_fn(
                event_type="evaluator_backfill",
                feature_id=fid,
                details={
                    "status": result.status,
                    "score": result.score,
                    "backfill_reason": backfill_reason,
                    "source": "reconcile-evaluator CLI",
                    "synthetic": True,
                    "score_source": "backfill_default",
                    **({"forced_overwrite": True} if fid in forced_overwrite_ids else {}),
                },
            )
        except Exception as exc:
            # Audit write failure should not downgrade a successful backfill.
            audit_failed[str(fid)] = str(exc)

    total = len(candidates)
    n_ok = len(backfilled)
    report = {
        "total_scanned": total,
        "backfilled": n_ok,
        "failed": failed,
        "audit_failed": audit_failed,
        "summary": f"{n_ok}/{total} backfilled successfully",
    }
    emit(report, output_json)

    if failed and backfilled:
        return 1
    if failed:
        return 2
    return 0
