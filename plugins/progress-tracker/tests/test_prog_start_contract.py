#!/usr/bin/env python3
"""Contract tests for prog-start command/skill wiring."""

import json
import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent


def test_prog_start_skill_has_valid_frontmatter():
    """prog-start skill should use standard YAML frontmatter format."""
    skill_path = PLUGIN_ROOT / "skills" / "prog-start" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "\n---\n" in content[4:]
    assert re.search(r"^name:\s*prog-start$", content, re.MULTILINE)
    assert re.search(r"^description:\s*This skill should be used", content, re.MULTILINE)


def test_prog_start_command_invokes_prog_start_skill():
    """prog-start command should invoke the prog-start skill explicitly."""
    command_path = PLUGIN_ROOT / "commands" / "prog-start.md"
    content = command_path.read_text(encoding="utf-8")

    assert "<CRITICAL>" in content
    assert 'skill: "progress-tracker:prog-start"' in content


def test_plugin_json_relies_on_auto_discovery_for_commands():
    """plugin manifest should use default command auto-discovery (no inline commands registry)."""
    plugin_json_path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    manifest = json.loads(plugin_json_path.read_text(encoding="utf-8"))

    assert "commands" not in manifest
