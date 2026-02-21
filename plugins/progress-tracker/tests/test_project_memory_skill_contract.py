#!/usr/bin/env python3
"""Contract tests for project-memory skill integration in /prog flows."""

from __future__ import annotations

from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent


def test_feature_complete_mentions_project_memory_append():
    """feature-complete skill should append capability memory after completion."""
    skill_path = PLUGIN_ROOT / "skills" / "feature-complete" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert "project_memory.py append" in content
    assert "do not roll back feature completion" in content


def test_feature_implement_mentions_project_memory_overlap_warning():
    """feature-implement skill should read project memory for advisory overlap warning."""
    skill_path = PLUGIN_ROOT / "skills" / "feature-implement" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert "project_memory.py read" in content
    assert "Never block `/prog next`" in content
