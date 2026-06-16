#!/usr/bin/env python3
import argparse
import json
import sys
import traceback
from pathlib import Path

class RenderError(Exception):
    pass

def main():
    try:
        _main_impl()
        sys.exit(0)
    except RenderError as re:
        print(f"Render Error: {re}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("Renderer crashed internally!", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

def _main_impl():
    parser = argparse.ArgumentParser(description="Render CHANGELOG.md from index.jsonl")
    parser.add_argument("--project-root", type=str, help="Path to project root")
    args = parser.parse_args()

    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        project_root = Path(__file__).resolve().parents[2]

    index_file = project_root / "docs" / "changes" / "index.jsonl"
    changelog_file = project_root / "CHANGELOG.md"

    if not index_file.exists():
        raise RenderError(f"index.jsonl not found at {index_file}")
    if not changelog_file.exists():
        raise RenderError(f"CHANGELOG.md not found at {changelog_file}")

    rows = []
    with open(index_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                rows.append(row)
            except json.JSONDecodeError as e:
                raise RenderError(f"index.jsonl line {idx}: Invalid JSON: {e}")

    rows.sort(key=lambda x: (x.get("date", ""), x.get("change_id", "")))

    lines = ["\n### AI Traceable Changes\n"]
    for row in rows:
        date = row.get("date", "unknown")
        change_id = row.get("change_id", "unknown")
        record_path = row.get("record_path", "")
        summary = row.get("summary", "")
        fixes = row.get("fixes", [])
        fixes_str = ", ".join(fixes) if fixes else "none"

        lines.append(f"- **[{date}] [{change_id}]({record_path})**: {summary} (fixes: {fixes_str})")
    
    lines.append("")
    rendered_block = "\n".join(lines)

    changelog_content = changelog_file.read_text(encoding="utf-8")
    
    start_marker = "<!-- START_F19_MANAGED_BLOCK -->"
    end_marker = "<!-- END_F19_MANAGED_BLOCK -->"

    if start_marker not in changelog_content or end_marker not in changelog_content:
        raise RenderError(f"Markers '{start_marker}' or '{end_marker}' not found in CHANGELOG.md")

    start_idx = changelog_content.find(start_marker) + len(start_marker)
    end_idx = changelog_content.find(end_marker)

    if start_idx > end_idx:
        raise RenderError("Start marker found after end marker in CHANGELOG.md")

    new_content = changelog_content[:start_idx] + rendered_block + changelog_content[end_idx:]

    changelog_file.write_text(new_content, encoding="utf-8")
    print("CHANGELOG.md successfully regenerated from index.jsonl.")

if __name__ == "__main__":
    main()
