#!/usr/bin/env python3
"""Planning workflow helpers for SPM -> PROG preflight integration."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import prog_bridge


DESIGN_CATEGORIES = {"ui", "ux", "frontend", "design", "visual", "interaction"}
DEVEX_CATEGORIES = {"devex", "developer_experience", "tooling", "ci", "build", "test", "workflow"}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "planning"


def _contracts_dir(project_root: Path) -> Path:
    return project_root / "docs" / "product-contracts"


def _reviews_dir(project_root: Path) -> Path:
    return project_root / "docs" / "product-reviews"


def _write_markdown(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def suggest_optional_lanes(change_categories: Optional[List[str]] = None) -> Dict[str, bool]:
    """Suggest optional review lanes from normalized change categories."""
    normalized = {item.strip().lower() for item in (change_categories or []) if item.strip()}
    return {
        "design": bool(normalized & DESIGN_CATEGORIES),
        "devex": bool(normalized & DEVEX_CATEGORIES),
    }


def run_office_hours(
    *,
    topic: str,
    goals: Optional[List[str]] = None,
    scope: Optional[List[str]] = None,
    acceptance: Optional[List[str]] = None,
    risks: Optional[List[str]] = None,
    feature_id: Optional[int] = None,
    refs: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create office-hours product contract artifact and sync into PROG."""
    root = (project_root or Path.cwd()).resolve()
    now = datetime.now(timezone.utc)
    date_token = now.strftime("%Y-%m-%d")
    artifact = _contracts_dir(root) / f"{date_token}-{_slugify(topic)}-office-hours.md"

    lines = [
        f"# Office Hours: {topic}",
        "",
        f"- Date: {date_token}",
        "- Mode: planner-only (no technical implementation path)",
        "",
        "## Goals",
    ]
    lines.extend([f"- {item}" for item in (goals or [])] or ["- (pending)"])
    lines.append("")
    lines.append("## Scope")
    lines.extend([f"- {item}" for item in (scope or [])] or ["- (pending)"])
    lines.append("")
    lines.append("## Acceptance Criteria")
    lines.extend([f"- {item}" for item in (acceptance or [])] or ["- (pending)"])
    lines.append("")
    lines.append("## Risks")
    lines.extend([f"- {item}" for item in (risks or [])] or ["- (none)"])
    _write_markdown(artifact, lines)

    rel_artifact = _relative_to_root(artifact, root)
    sync_result = prog_bridge.sync_planning_update(
        stage="office_hours",
        category="decision",
        summary=f"office-hours complete: {topic}",
        details="Planner contract captured (goals/scope/acceptance/risks).",
        feature_id=feature_id,
        doc_path=rel_artifact,
        refs=refs,
        cwd=root,
    )
    return {
        "ok": True,
        "artifact_file": str(artifact),
        "sync": sync_result,
        "sync_errors": [] if sync_result.get("ok") else [sync_result],
    }


def run_ceo_review(
    *,
    topic: str,
    verdict: str,
    opportunities: Optional[List[str]] = None,
    risks: Optional[List[str]] = None,
    feature_id: Optional[int] = None,
    refs: Optional[List[str]] = None,
    change_categories: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create plan-ceo-review artifact and sync into PROG."""
    verdict = verdict.strip()[:500]
    root = (project_root or Path.cwd()).resolve()
    now = datetime.now(timezone.utc)
    date_token = now.strftime("%Y-%m-%d")
    artifact = _reviews_dir(root) / f"{date_token}-{_slugify(topic)}-plan-ceo-review.md"
    lane_suggestion = suggest_optional_lanes(change_categories)

    lines = [
        f"# Plan CEO Review: {topic}",
        "",
        f"- Date: {date_token}",
        f"- Verdict: {verdict}",
        "",
        "## Opportunities",
    ]
    lines.extend([f"- {item}" for item in (opportunities or [])] or ["- (none)"])
    lines.append("")
    lines.append("## Risks")
    lines.extend([f"- {item}" for item in (risks or [])] or ["- (none)"])
    lines.append("")
    lines.append("## Optional Lane Suggestions")
    lines.append(f"- design: {'recommended' if lane_suggestion['design'] else 'optional'}")
    lines.append(f"- devex: {'recommended' if lane_suggestion['devex'] else 'optional'}")
    _write_markdown(artifact, lines)

    rel_artifact = _relative_to_root(artifact, root)
    sync_result = prog_bridge.sync_planning_update(
        stage="ceo_review",
        category="decision",
        summary=f"plan-ceo-review complete: {topic} ({verdict})",
        details="CEO-level opportunity/risk review captured.",
        feature_id=feature_id,
        doc_path=rel_artifact,
        refs=refs,
        cwd=root,
    )
    return {
        "ok": True,
        "artifact_file": str(artifact),
        "lane_suggestion": lane_suggestion,
        "sync": sync_result,
        "sync_errors": [] if sync_result.get("ok") else [sync_result],
    }


def run_design_review(
    *,
    topic: str,
    score: int,
    strengths: Optional[List[str]] = None,
    issues: Optional[List[str]] = None,
    recommendation: Optional[str] = None,
    feature_id: Optional[int] = None,
    refs: Optional[List[str]] = None,
    change_categories: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create plan-design-review artifact and sync into PROG."""
    if not (0 <= score <= 10):
        return {"ok": False, "error": "invalid_score", "message": f"score must be 0-10, got {score}"}
    root = (project_root or Path.cwd()).resolve()
    now = datetime.now(timezone.utc)
    date_token = now.strftime("%Y-%m-%d")
    artifact = _reviews_dir(root) / f"{date_token}-{_slugify(topic)}-plan-design-review.md"
    lane_suggestion = suggest_optional_lanes(change_categories)

    lines = [
        f"# Plan Design Review: {topic}",
        "",
        f"- Date: {date_token}",
        f"- Score: {score}/10",
        "",
        "## Strengths",
    ]
    lines.extend([f"- {item}" for item in (strengths or [])] or ["- (none)"])
    lines.append("")
    lines.append("## Issues")
    lines.extend([f"- {item}" for item in (issues or [])] or ["- (none)"])
    lines.append("")
    lines.append("## Recommendation")
    lines.append(f"- {recommendation.strip()}" if isinstance(recommendation, str) and recommendation.strip() else "- (pending)")
    lines.append("")
    lines.append("## Lane Trigger Hint")
    lines.append(
        f"- design lane suggested by categories: {'yes' if lane_suggestion['design'] else 'no'}"
    )
    _write_markdown(artifact, lines)

    rel_artifact = _relative_to_root(artifact, root)
    sync_result = prog_bridge.sync_planning_update(
        stage="design_review",
        category="decision",
        summary=f"plan-design-review complete: {topic} (score={score}/10)",
        details="Design quality review recorded.",
        feature_id=feature_id,
        doc_path=rel_artifact,
        refs=refs,
        cwd=root,
    )
    return {
        "ok": True,
        "artifact_file": str(artifact),
        "lane_suggestion": lane_suggestion,
        "sync": sync_result,
        "sync_errors": [] if sync_result.get("ok") else [sync_result],
    }


def run_devex_review(
    *,
    topic: str,
    score: int,
    frictions: Optional[List[str]] = None,
    improvements: Optional[List[str]] = None,
    recommendation: Optional[str] = None,
    feature_id: Optional[int] = None,
    refs: Optional[List[str]] = None,
    change_categories: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create plan-devex-review artifact and sync into PROG."""
    if not (0 <= score <= 10):
        return {"ok": False, "error": "invalid_score", "message": f"score must be 0-10, got {score}"}
    root = (project_root or Path.cwd()).resolve()
    now = datetime.now(timezone.utc)
    date_token = now.strftime("%Y-%m-%d")
    artifact = _reviews_dir(root) / f"{date_token}-{_slugify(topic)}-plan-devex-review.md"
    lane_suggestion = suggest_optional_lanes(change_categories)

    lines = [
        f"# Plan DevEx Review: {topic}",
        "",
        f"- Date: {date_token}",
        f"- Score: {score}/10",
        "",
        "## Frictions",
    ]
    lines.extend([f"- {item}" for item in (frictions or [])] or ["- (none)"])
    lines.append("")
    lines.append("## Improvements")
    lines.extend([f"- {item}" for item in (improvements or [])] or ["- (none)"])
    lines.append("")
    lines.append("## Recommendation")
    lines.append(f"- {recommendation.strip()}" if isinstance(recommendation, str) and recommendation.strip() else "- (pending)")
    lines.append("")
    lines.append("## Lane Trigger Hint")
    lines.append(
        f"- devex lane suggested by categories: {'yes' if lane_suggestion['devex'] else 'no'}"
    )
    _write_markdown(artifact, lines)

    rel_artifact = _relative_to_root(artifact, root)
    sync_result = prog_bridge.sync_planning_update(
        stage="devex_review",
        category="decision",
        summary=f"plan-devex-review complete: {topic} (score={score}/10)",
        details="Developer experience review recorded.",
        feature_id=feature_id,
        doc_path=rel_artifact,
        refs=refs,
        cwd=root,
    )
    return {
        "ok": True,
        "artifact_file": str(artifact),
        "lane_suggestion": lane_suggestion,
        "sync": sync_result,
        "sync_errors": [] if sync_result.get("ok") else [sync_result],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SPM planning workflow bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    office_parser = subparsers.add_parser("office-hours", help="Create office-hours contract")
    office_parser.add_argument("--topic", required=True)
    office_parser.add_argument("--goals", help="Comma-separated goals")
    office_parser.add_argument("--scope", help="Comma-separated scope bullets")
    office_parser.add_argument("--acceptance", help="Comma-separated acceptance criteria")
    office_parser.add_argument("--risks", help="Comma-separated risk bullets")
    office_parser.add_argument("--feature-id", type=int)
    office_parser.add_argument("--refs", help="Comma-separated refs")

    ceo_parser = subparsers.add_parser("plan-ceo-review", help="Create CEO review artifact")
    ceo_parser.add_argument("--topic", required=True)
    ceo_parser.add_argument("--verdict", required=True)
    ceo_parser.add_argument("--opportunities", help="Comma-separated opportunities")
    ceo_parser.add_argument("--risks", help="Comma-separated risks")
    ceo_parser.add_argument("--feature-id", type=int)
    ceo_parser.add_argument("--refs", help="Comma-separated refs")
    ceo_parser.add_argument("--change-categories", help="Comma-separated change categories")

    design_parser = subparsers.add_parser("plan-design-review", help="Create design review artifact")
    design_parser.add_argument("--topic", required=True)
    design_parser.add_argument("--score", type=int, required=True)
    design_parser.add_argument("--strengths", help="Comma-separated strengths")
    design_parser.add_argument("--issues", help="Comma-separated issues")
    design_parser.add_argument("--recommendation")
    design_parser.add_argument("--feature-id", type=int)
    design_parser.add_argument("--refs", help="Comma-separated refs")
    design_parser.add_argument("--change-categories", help="Comma-separated change categories")

    devex_parser = subparsers.add_parser("plan-devex-review", help="Create devex review artifact")
    devex_parser.add_argument("--topic", required=True)
    devex_parser.add_argument("--score", type=int, required=True)
    devex_parser.add_argument("--frictions", help="Comma-separated frictions")
    devex_parser.add_argument("--improvements", help="Comma-separated improvements")
    devex_parser.add_argument("--recommendation")
    devex_parser.add_argument("--feature-id", type=int)
    devex_parser.add_argument("--refs", help="Comma-separated refs")
    devex_parser.add_argument("--change-categories", help="Comma-separated change categories")

    args = parser.parse_args()

    if args.command == "office-hours":
        result = run_office_hours(
            topic=args.topic,
            goals=_parse_csv(args.goals),
            scope=_parse_csv(args.scope),
            acceptance=_parse_csv(args.acceptance),
            risks=_parse_csv(args.risks),
            feature_id=args.feature_id,
            refs=_parse_csv(args.refs),
        )
    elif args.command == "plan-ceo-review":
        result = run_ceo_review(
            topic=args.topic,
            verdict=args.verdict,
            opportunities=_parse_csv(args.opportunities),
            risks=_parse_csv(args.risks),
            feature_id=args.feature_id,
            refs=_parse_csv(args.refs),
            change_categories=_parse_csv(args.change_categories),
        )
    elif args.command == "plan-design-review":
        result = run_design_review(
            topic=args.topic,
            score=args.score,
            strengths=_parse_csv(args.strengths),
            issues=_parse_csv(args.issues),
            recommendation=args.recommendation,
            feature_id=args.feature_id,
            refs=_parse_csv(args.refs),
            change_categories=_parse_csv(args.change_categories),
        )
    else:
        result = run_devex_review(
            topic=args.topic,
            score=args.score,
            frictions=_parse_csv(args.frictions),
            improvements=_parse_csv(args.improvements),
            recommendation=args.recommendation,
            feature_id=args.feature_id,
            refs=_parse_csv(args.refs),
            change_categories=_parse_csv(args.change_categories),
        )

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
