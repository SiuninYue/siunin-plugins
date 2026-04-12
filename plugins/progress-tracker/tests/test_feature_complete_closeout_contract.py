#!/usr/bin/env python3
"""Contract tests for feature-complete merge-first closeout policy."""

from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
FEATURE_COMPLETE_SKILL = PLUGIN_ROOT / "skills" / "feature-complete" / "SKILL.md"


def test_feature_complete_defaults_prog_done_to_merge_first_intent():
    """`/prog done` should default to commit_push_pr_merge closeout intent."""
    content = FEATURE_COMPLETE_SKILL.read_text(encoding="utf-8")

    assert "intent: commit_push_pr_merge" in content
    assert "intent: commit_push_pr\")" not in content


def test_feature_complete_keeps_single_merge_authority_in_git_auto():
    """Normal flow should not auto-run second branch-finishing authority."""
    content = FEATURE_COMPLETE_SKILL.read_text(encoding="utf-8")

    assert "`git-auto` is the single authority for merge gating and execution." in content
    assert "Do NOT invoke `finishing-a-development-branch` automatically" in content
