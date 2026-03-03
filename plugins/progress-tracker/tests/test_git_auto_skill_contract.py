#!/usr/bin/env python3
"""Contract tests for git-auto skill structure and compatibility fields."""

from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
GIT_AUTO_SKILL = PLUGIN_ROOT / "skills" / "git-auto" / "SKILL.md"
REFERENCES_DIR = PLUGIN_ROOT / "skills" / "git-auto" / "references"


def test_git_auto_skill_keeps_stable_command_interface_and_preflight():
    content = GIT_AUTO_SKILL.read_text(encoding="utf-8")

    assert "git auto" in content
    assert "git auto start <feature-name>" in content
    assert "git auto done" in content
    assert "git auto fix <bug-description>" in content

    assert "plugins/progress-tracker/prog git-auto-preflight --json" in content


def test_git_auto_skill_keeps_required_output_fields():
    content = GIT_AUTO_SKILL.read_text(encoding="utf-8")

    required_fields = [
        "Execution Intent:",
        "Enforcement Mode:",
        "Repo Policy:",
        "Workspace Mode:",
        "Branch Strategy:",
    ]
    for marker in required_fields:
        assert marker in content


def test_git_auto_references_are_split_into_expected_files():
    expected_files = {
        "enforcement-modes.md",
        "repo-policy-probe.md",
        "change-classification.md",
        "worktree-decision.md",
        "closeout-and-recovery.md",
    }

    actual_files = {path.name for path in REFERENCES_DIR.glob("*.md")}
    assert expected_files.issubset(actual_files)
