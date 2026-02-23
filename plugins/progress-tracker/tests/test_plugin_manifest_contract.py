#!/usr/bin/env python3
"""Contract tests for progress-tracker plugin manifest consistency."""

from __future__ import annotations

import json
import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
COMMANDS_DIR = PLUGIN_ROOT / "commands"
MANIFEST_PATH = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"


def _command_description(command_path: Path) -> str:
    content = command_path.read_text(encoding="utf-8")
    match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    assert match, f"Missing frontmatter description in {command_path.name}"
    return match.group(1).strip()


def test_manifest_commands_match_commands_directory():
    """Manifest command entries should stay in sync with commands/*.md files."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = manifest.get("commands", [])

    manifest_files = {entry["file"] for entry in entries}
    actual_files = {f"commands/{path.name}" for path in COMMANDS_DIR.glob("*.md")}

    assert manifest_files == actual_files


def test_manifest_command_entries_match_file_name_and_description():
    """Each manifest command entry should mirror command filename/frontmatter."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for entry in manifest.get("commands", []):
        command_path = PLUGIN_ROOT / entry["file"]
        assert command_path.exists(), f"Missing command file: {entry['file']}"
        assert entry["name"] == command_path.stem
        assert entry["description"] == _command_description(command_path)

