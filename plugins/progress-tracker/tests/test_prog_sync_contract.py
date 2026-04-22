#!/usr/bin/env python3
"""Contract tests for prog-sync command/skill wiring."""

from __future__ import annotations

import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent


def test_prog_sync_skill_has_valid_frontmatter():
    """prog-sync skill should use standard YAML frontmatter format."""
    skill_path = PLUGIN_ROOT / "skills" / "prog-sync" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "\n---\n" in content[4:]
    assert re.search(r"^name:\s*prog-sync$", content, re.MULTILINE)
    assert re.search(r"^description:\s*This skill should be used", content, re.MULTILINE)


def test_prog_sync_command_invokes_prog_sync_skill():
    """prog-sync command should invoke the prog-sync skill explicitly."""
    command_path = PLUGIN_ROOT / "commands" / "prog-sync.md"
    content = command_path.read_text(encoding="utf-8")

    assert "<CRITICAL>" in content
    assert 'skill: "progress-tracker:prog-sync"' in content


def test_prog_sync_documented_in_prog_commands_source():
    """PROG command source doc should include namespaced prog-sync entry."""
    source_path = PLUGIN_ROOT / "docs" / "PROG_COMMANDS.md"
    content = source_path.read_text(encoding="utf-8")

    assert "### `/progress-tracker:prog-sync`" in content


def test_prog_update_skill_has_valid_frontmatter():
    """prog-update skill should use standard YAML frontmatter format."""
    skill_path = PLUGIN_ROOT / "skills" / "progress-update" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "\n---\n" in content[4:]
    assert re.search(r"^name:\s*progress-update$", content, re.MULTILINE)
    assert re.search(r"^description:\s*This skill should be used", content, re.MULTILINE)


def test_prog_update_command_invokes_progress_update_skill():
    """prog-update command should invoke the progress-update skill explicitly."""
    command_path = PLUGIN_ROOT / "commands" / "prog-update.md"
    content = command_path.read_text(encoding="utf-8")

    assert "<CRITICAL>" in content
    assert 'skill: "progress-tracker:progress-update"' in content


def test_prog_update_documented_in_prog_commands_source():
    """PROG command source doc should include namespaced prog-update entry."""
    source_path = PLUGIN_ROOT / "docs" / "PROG_COMMANDS.md"
    content = source_path.read_text(encoding="utf-8")

    assert "### `/progress-tracker:prog-update`" in content
