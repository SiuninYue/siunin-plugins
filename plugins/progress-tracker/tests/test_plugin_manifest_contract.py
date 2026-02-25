#!/usr/bin/env python3
"""Contract tests for progress-tracker plugin manifest consistency."""

from __future__ import annotations

import json
import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
COMMANDS_DIR = PLUGIN_ROOT / "commands"
SKILLS_DIR = PLUGIN_ROOT / "skills"
MANIFEST_PATH = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"


def _command_description(command_path: Path) -> str:
    content = command_path.read_text(encoding="utf-8")
    match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    assert match, f"Missing frontmatter description in {command_path.name}"
    return match.group(1).strip()


def test_manifest_relies_on_auto_discovery_for_commands():
    """Manifest should not inline command metadata; Claude Code auto-discovers commands/."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "commands" not in manifest


def test_command_frontmatter_matches_file_name_and_description():
    """Each command file should include required frontmatter description."""
    command_files = sorted(COMMANDS_DIR.glob("*.md"))
    assert command_files, "Expected commands/*.md files"

    for command_path in command_files:
        assert _command_description(command_path)


def test_skills_are_available_for_auto_discovery():
    """Skills should live in root skills/ for current Claude Code auto-discovery."""
    skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    assert skill_files, "Expected skills/*/SKILL.md files"
