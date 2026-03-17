#!/usr/bin/env python3
"""Meeting workflow helpers for SPM beta integration with PROG."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import prog_bridge


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "meeting"


def _meetings_dir(project_root: Path) -> Path:
    return project_root / "docs" / "meetings"


def _action_items_path(project_root: Path) -> Path:
    return _meetings_dir(project_root) / "action-items.json"


def _load_action_items(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _save_action_items(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _next_action_id(existing: List[Dict[str, Any]], date_token: str) -> str:
    prefix = f"A-{date_token}-"
    max_index = 0
    for item in existing:
        raw_id = str(item.get("id", ""))
        if raw_id.startswith(prefix):
            try:
                max_index = max(max_index, int(raw_id.split("-")[-1]))
            except ValueError:
                continue
    return f"{prefix}{max_index + 1:02d}"


def create_meeting_record(
    *,
    topic: str,
    summary: str,
    decisions: Optional[List[str]] = None,
    action_items: Optional[List[str]] = None,
    refs: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist meeting artifacts and best-effort sync into PROG."""
    root = (project_root or Path.cwd()).resolve()
    meetings_dir = _meetings_dir(root)
    meetings_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_token = now.strftime("%Y-%m-%d")
    action_date_token = now.strftime("%Y%m%d")
    meeting_file = meetings_dir / f"{date_token}-{_slugify(topic)}.md"

    existing_actions = _load_action_items(_action_items_path(root))
    normalized_action_items: List[Dict[str, Any]] = []
    for item in action_items or []:
        item_text = item.strip()
        if not item_text:
            continue
        action_id = _next_action_id(existing_actions + normalized_action_items, action_date_token)
        normalized_action_items.append(
            {
                "id": action_id,
                "topic": topic,
                "summary": item_text,
                "status": "open",
                "created_at": now.isoformat().replace("+00:00", "Z"),
                "updated_at": now.isoformat().replace("+00:00", "Z"),
            }
        )

    markdown_lines = [
        f"# Meeting: {topic}",
        "",
        f"- Date: {date_token}",
        f"- Summary: {summary}",
        "",
        "## Decisions",
    ]
    if decisions:
        markdown_lines.extend([f"- {item}" for item in decisions])
    else:
        markdown_lines.append("- (none)")

    markdown_lines.append("")
    markdown_lines.append("## Action Items")
    if normalized_action_items:
        for item in normalized_action_items:
            markdown_lines.append(f"- [{item['id']}] {item['summary']}")
    else:
        markdown_lines.append("- (none)")

    if refs:
        markdown_lines.append("")
        markdown_lines.append("## Refs")
        markdown_lines.extend([f"- {ref}" for ref in refs if ref.strip()])

    meeting_file.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")

    all_actions = [*existing_actions, *normalized_action_items]
    action_items_path = _action_items_path(root)
    _save_action_items(action_items_path, all_actions)

    sync_result = prog_bridge.sync_meeting(
        summary=summary,
        details="\n".join(decisions or []),
        refs=refs,
        cwd=root,
    )
    sync_errors: List[Dict[str, Any]] = []
    if not sync_result.get("ok"):
        sync_errors.append(sync_result)

    return {
        "ok": True,
        "meeting_file": str(meeting_file),
        "action_items_file": str(action_items_path),
        "action_item_ids": [item["id"] for item in normalized_action_items],
        "sync": sync_result,
        "sync_errors": sync_errors,
    }


def assign_feature_owner(
    *,
    feature_id: int,
    role: str,
    owner: str,
    note: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Assign owner and sync assignment update into PROG."""
    root = (project_root or Path.cwd()).resolve()
    summary = note.strip() if isinstance(note, str) and note.strip() else f"Assign {role} owner: {owner}"
    result = prog_bridge.sync_assignment(
        feature_id=feature_id,
        role=role,
        owner=owner,
        summary=summary,
        details=note,
        cwd=root,
    )
    return {
        "ok": bool(result.get("ok")),
        "sync": result,
        "sync_errors": [] if result.get("ok") else [result],
    }


def followup_action_item(
    *,
    action_id: str,
    status: str,
    note: str,
    feature_id: Optional[int] = None,
    next_action: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Update action-items file and perform best-effort follow-up sync."""
    root = (project_root or Path.cwd()).resolve()
    action_items_path = _action_items_path(root)
    items = _load_action_items(action_items_path)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    target = None
    for item in items:
        if str(item.get("id")) == action_id:
            target = item
            break

    if target is None:
        target = {
            "id": action_id,
            "topic": "followup",
            "summary": note,
            "status": "open",
            "created_at": now,
            "updated_at": now,
        }
        items.append(target)

    target["status"] = status
    target["summary"] = note
    target["updated_at"] = now
    _save_action_items(action_items_path, items)

    category = "handoff" if status.lower() in {"handoff", "blocked"} else "status"
    sync_result = prog_bridge.sync_followup(
        summary=f"{action_id}: {status}",
        details=note,
        category=category,
        feature_id=feature_id,
        next_action=next_action,
        cwd=root,
    )

    return {
        "ok": True,
        "action_items_file": str(action_items_path),
        "sync": sync_result,
        "sync_errors": [] if sync_result.get("ok") else [sync_result],
    }


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="SPM meeting workflow bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    meeting_parser = subparsers.add_parser("meeting", help="Create meeting record and sync")
    meeting_parser.add_argument("--topic", required=True)
    meeting_parser.add_argument("--summary", required=True)
    meeting_parser.add_argument("--decisions", help="Comma-separated decisions")
    meeting_parser.add_argument("--actions", help="Comma-separated action items")
    meeting_parser.add_argument("--refs", help="Comma-separated refs")

    assign_parser = subparsers.add_parser("assign", help="Assign feature owner")
    assign_parser.add_argument("--feature-id", type=int, required=True)
    assign_parser.add_argument("--role", required=True)
    assign_parser.add_argument("--owner", required=True)
    assign_parser.add_argument("--note")

    followup_parser = subparsers.add_parser("followup", help="Update action item follow-up")
    followup_parser.add_argument("--action-id", required=True)
    followup_parser.add_argument("--status", required=True)
    followup_parser.add_argument("--note", required=True)
    followup_parser.add_argument("--feature-id", type=int)
    followup_parser.add_argument("--next-action")

    args = parser.parse_args()

    if args.command == "meeting":
        result = create_meeting_record(
            topic=args.topic,
            summary=args.summary,
            decisions=_parse_csv(args.decisions),
            action_items=_parse_csv(args.actions),
            refs=_parse_csv(args.refs),
        )
    elif args.command == "assign":
        result = assign_feature_owner(
            feature_id=args.feature_id,
            role=args.role,
            owner=args.owner,
            note=args.note,
        )
    else:
        result = followup_action_item(
            action_id=args.action_id,
            status=args.status,
            note=args.note,
            feature_id=args.feature_id,
            next_action=args.next_action,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
