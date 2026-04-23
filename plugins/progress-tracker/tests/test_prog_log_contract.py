#!/usr/bin/env python3
"""Contract tests for prog-log and prog-note command/skill wiring."""

from __future__ import annotations

import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent


def test_prog_log_skill_has_valid_frontmatter():
    """prog-log skill should use standard YAML frontmatter format."""
    skill_path = PLUGIN_ROOT / "skills" / "prog-log" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "\n---\n" in content[4:]
    assert re.search(r"^name:\s*prog-log$", content, re.MULTILINE)
    assert re.search(r"^description:\s*This skill should be used", content, re.MULTILINE)


def test_prog_log_command_invokes_prog_log_skill():
    """prog-log command should invoke the prog-log skill explicitly."""
    command_path = PLUGIN_ROOT / "commands" / "prog-log.md"
    content = command_path.read_text(encoding="utf-8")

    assert "<CRITICAL>" in content
    assert 'skill: "progress-tracker:prog-log"' in content


def test_prog_log_documented_in_prog_commands_source():
    """PROG command source doc should include namespaced prog-log entry."""
    source_path = PLUGIN_ROOT / "docs" / "PROG_COMMANDS.md"
    content = source_path.read_text(encoding="utf-8")

    assert "### `/progress-tracker:prog-log`" in content


def test_prog_note_skill_has_valid_frontmatter():
    """prog-note skill should use standard YAML frontmatter format."""
    skill_path = PLUGIN_ROOT / "skills" / "prog-note" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "\n---\n" in content[4:]
    assert re.search(r"^name:\s*prog-note$", content, re.MULTILINE)
    assert re.search(r"^description:\s*This skill should be used", content, re.MULTILINE)


def test_prog_note_command_invokes_prog_note_skill():
    """prog-note command should invoke the prog-note skill explicitly."""
    command_path = PLUGIN_ROOT / "commands" / "prog-note.md"
    content = command_path.read_text(encoding="utf-8")

    assert "<CRITICAL>" in content
    assert 'skill: "progress-tracker:prog-note"' in content


def test_prog_note_documented_in_prog_commands_source():
    """PROG command source doc should include namespaced prog-note entry."""
    source_path = PLUGIN_ROOT / "docs" / "PROG_COMMANDS.md"
    content = source_path.read_text(encoding="utf-8")

    assert "### `/progress-tracker:prog-note`" in content
