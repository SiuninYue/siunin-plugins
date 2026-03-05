#!/usr/bin/env python3
"""Contract tests for unified git-auto preflight usage in prog workflows."""

from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
FEATURE_IMPLEMENT_SKILL = PLUGIN_ROOT / "skills" / "feature-implement" / "SKILL.md"
PROG_START_SKILL = PLUGIN_ROOT / "skills" / "prog-launcher" / "SKILL.md"
FEATURE_COMPLEX_SKILL = PLUGIN_ROOT / "skills" / "feature-implement-complex" / "SKILL.md"


def test_feature_implement_uses_unified_git_auto_preflight_and_tri_state_decision():
    content = FEATURE_IMPLEMENT_SKILL.read_text(encoding="utf-8")

    assert "plugins/progress-tracker/prog git-auto-preflight --json" in content
    assert "ALLOW_IN_PLACE" in content
    assert "REQUIRE_WORKTREE" in content
    assert "DELEGATE_GIT_AUTO" in content
    assert 'Skill("using-git-worktrees"' in content
    assert 'Skill("progress-tracker:git-auto"' in content


def test_prog_start_uses_same_preflight_entrypoint():
    content = PROG_START_SKILL.read_text(encoding="utf-8")

    assert "plugins/progress-tracker/prog git-auto-preflight --json" in content
    assert "check-workspace" not in content


def test_feature_implement_complex_respects_unified_preflight_decision():
    content = FEATURE_COMPLEX_SKILL.read_text(encoding="utf-8")

    assert "plugins/progress-tracker/prog git-auto-preflight --json" in content
    assert "decision=REQUIRE_WORKTREE" in content
    assert "decision=DELEGATE_GIT_AUTO" in content
