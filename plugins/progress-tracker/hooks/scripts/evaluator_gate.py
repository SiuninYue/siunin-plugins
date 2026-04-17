#!/usr/bin/env python3
"""Independent quality evaluator gate (PR-3).

Generator/evaluator separation follows Anthropic harness discipline:
this module is expected to be invoked from a DIFFERENT subagent context
than the one that produced the feature code. The caller is responsible
for enforcing subagent isolation; this module only encodes the scoring
rubric and defect classification.

Status values:
  pass             — no blocking defects, coverage meets threshold
  retry            — blocking defect(s) found or coverage below threshold
  required_reviews — security/major defect requires human review lane
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

Status = Literal["pass", "retry", "required_reviews"]

_SECURITY_KEYWORDS = ("auth bypass", "sql injection", "xss", "rce", "secret leak")


@dataclass
class EvaluatorDefect:
    id: str
    severity: str  # blocking | major | minor | info
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "severity": self.severity, "description": self.description}


@dataclass
class EvaluatorResult:
    status: Status
    score: int
    defects: List[EvaluatorDefect] = field(default_factory=list)
    last_run_at: str = ""
    evaluator_model: Optional[str] = None

    def to_quality_gate_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "defects": [d.to_dict() for d in self.defects],
            "last_run_at": self.last_run_at,
            "evaluator_model": self.evaluator_model,
        }


def _classify(defect_dict: Dict[str, Any]) -> EvaluatorDefect:
    return EvaluatorDefect(
        id=defect_dict["id"],
        severity=defect_dict.get("severity", "minor"),
        description=defect_dict.get("description", ""),
    )


def _score_from_signals(signals: Dict[str, Any]) -> int:
    base = 100
    coverage = float(signals.get("test_coverage", 0.0))
    if coverage < 0.6:
        base -= 40
    elif coverage < 0.8:
        base -= 20
    for d in signals.get("defects", []):
        sev = d.get("severity", "minor")
        base -= {"blocking": 30, "major": 15, "minor": 5, "info": 0}.get(sev, 5)
    return max(0, min(100, base))


def _is_security_defect(d: EvaluatorDefect) -> bool:
    desc = d.description.lower()
    return any(kw in desc for kw in _SECURITY_KEYWORDS) or d.severity == "major"


def assess(
    *,
    feature: Dict[str, Any],
    rubric: Dict[str, Any],
    signals: Dict[str, Any],
    evaluator_model: Optional[str] = None,
) -> EvaluatorResult:
    """Run the evaluator rubric against generator signals.

    Args:
        feature: current feature dict from progress.json
        rubric: {"test_coverage_min": float, "require_changelog": bool, ...}
        signals: {"test_coverage": float, "defects": list[dict], ...}
        evaluator_model: model ID used for evaluation (for audit traceability)
    """
    defects = [_classify(d) for d in signals.get("defects", [])]
    coverage = float(signals.get("test_coverage", 0.0))
    if coverage < float(rubric.get("test_coverage_min", 0.8)):
        defects.append(
            EvaluatorDefect(
                id=f"COV-{feature['id']}",
                severity="blocking",
                description=(
                    f"test coverage {coverage:.0%} below minimum "
                    f"{rubric['test_coverage_min']:.0%}"
                ),
            )
        )

    status: Status
    if any(d.severity == "blocking" for d in defects):
        status = "retry"
    elif any(_is_security_defect(d) for d in defects):
        status = "required_reviews"
    else:
        status = "pass"

    return EvaluatorResult(
        status=status,
        score=_score_from_signals(signals),
        defects=defects,
        last_run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        evaluator_model=evaluator_model,
    )
