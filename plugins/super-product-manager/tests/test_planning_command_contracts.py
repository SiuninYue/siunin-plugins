#!/usr/bin/env python3
"""Contract tests for SPM planning command set."""

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


def test_planning_command_files_exist_with_required_frontmatter() -> None:
    for name in (
        "office-hours",
        "plan-ceo-review",
        "plan-design-review",
        "plan-devex-review",
    ):
        command_path = COMMANDS_DIR / f"{name}.md"
        assert command_path.exists(), f"missing command file: {command_path}"
        frontmatter = _frontmatter(command_path.read_text(encoding="utf-8"))

        assert re.search(r"^scope:\s*command$", frontmatter, re.MULTILINE)
        assert re.search(r'^version:\s*"\d+\.\d+\.\d+"$', frontmatter, re.MULTILINE)
        assert re.search(r"^description:\s*.+", frontmatter, re.MULTILINE)


def test_office_hours_enforces_planner_only_boundary() -> None:
    content = (COMMANDS_DIR / "office-hours.md").read_text(encoding="utf-8")
    assert "技术实现路径" in content


def test_optional_lane_commands_document_auto_suggestion() -> None:
    for name in ("plan-design-review", "plan-devex-review"):
        content = (COMMANDS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert "自动建议" in content
