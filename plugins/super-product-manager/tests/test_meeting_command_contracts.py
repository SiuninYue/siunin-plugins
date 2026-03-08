#!/usr/bin/env python3
"""Contract tests for SPM beta meeting command set."""

from __future__ import annotations

import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = PLUGIN_ROOT / "commands"


def _frontmatter(content: str) -> str:
    assert content.startswith("---\n")
    end = content.find("\n---\n", 4)
    assert end != -1
    return content[4:end]


def test_meeting_command_files_exist_with_required_frontmatter() -> None:
    for name in ("meeting", "roundtable", "assign", "followup"):
        command_path = COMMANDS_DIR / f"{name}.md"
        assert command_path.exists(), f"missing command file: {command_path}"
        frontmatter = _frontmatter(command_path.read_text(encoding="utf-8"))

        assert re.search(r"^scope:\s*command$", frontmatter, re.MULTILINE)
        assert re.search(r'^version:\s*"\d+\.\d+\.\d+"$', frontmatter, re.MULTILINE)
        assert re.search(r"^description:\s*.+", frontmatter, re.MULTILINE)


def test_assign_command_routes_to_owner_assignment_and_assignment_update() -> None:
    content = (COMMANDS_DIR / "assign.md").read_text(encoding="utf-8")

    assert "set-feature-owner" in content
    assert "assignment" in content.lower()


def test_meeting_and_followup_commands_include_artifact_and_sync_contract() -> None:
    for name in ("meeting", "roundtable", "followup"):
        content = (COMMANDS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert "docs/meetings" in content
        assert "同步" in content
