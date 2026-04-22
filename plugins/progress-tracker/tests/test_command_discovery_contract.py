#!/usr/bin/env python3
"""Command discovery contract tests."""

from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
COMMANDS_DIR = PLUGIN_ROOT / "commands"


def test_prog_workspace_command_is_removed_from_public_commands():
    assert not (COMMANDS_DIR / "prog-workspace.md").exists()


def test_core_progress_commands_remain_discoverable():
    expected_commands = {
        "prog.md",
        "prog-init.md",
        "prog-next.md",
        "prog-update.md",
        "prog-done.md",
        "prog-sync.md",
        "prog-ui.md",
        "help.md",
    }

    actual_commands = {path.name for path in COMMANDS_DIR.glob("*.md")}
    assert expected_commands.issubset(actual_commands)


def test_prog_start_command_is_not_reintroduced():
    """ADR-008: `/prog-next` is the sole feature-start entrypoint."""
    assert not (COMMANDS_DIR / "prog-start.md").exists()
