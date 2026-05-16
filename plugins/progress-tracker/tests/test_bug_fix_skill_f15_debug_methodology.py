#!/usr/bin/env python3
"""F15: Contract tests — prog-fix skill embeds 4-phase debugging methodology in Scenario 3."""

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
BUG_FIX_SKILL = PLUGIN_ROOT / "skills" / "bug-fix" / "SKILL.md"


def _content() -> str:
    return BUG_FIX_SKILL.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Scenario 3 — Structured Evidence Collection
# ---------------------------------------------------------------------------

def test_scenario3_has_evidence_collection_section():
    content = _content()
    assert "结构化证据收集" in content or "Evidence Collection" in content, \
        "Scenario 3 must include a structured evidence collection step"


def test_scenario3_evidence_includes_reproduction_path():
    content = _content()
    assert "复现路径" in content or "reproduction path" in content.lower(), \
        "Evidence collection must list reproduction path"


def test_scenario3_evidence_includes_error_logs():
    content = _content()
    assert "错误日志" in content or "error log" in content.lower(), \
        "Evidence collection must list error logs"


def test_scenario3_evidence_includes_io_comparison():
    content = _content()
    assert "输入输出对比" in content or "input/output" in content.lower() \
           or "input output" in content.lower(), \
        "Evidence collection must include input/output comparison"


# ---------------------------------------------------------------------------
# Scenario 3 — Trigger Pattern Analysis
# ---------------------------------------------------------------------------

def test_scenario3_has_trigger_pattern_analysis():
    content = _content()
    assert "触发模式分析" in content or "trigger pattern" in content.lower(), \
        "Scenario 3 must include trigger pattern analysis step"


def test_scenario3_trigger_includes_stable_conditions():
    content = _content()
    assert "稳定触发条件" in content or "stable trigger" in content.lower(), \
        "Trigger analysis must identify stable trigger conditions"


def test_scenario3_trigger_includes_boundary_conditions():
    content = _content()
    assert "边界条件" in content or "boundary condition" in content.lower(), \
        "Trigger analysis must identify boundary conditions"


# ---------------------------------------------------------------------------
# Scenario 3 — Hypothesis Uniqueness Verification
# ---------------------------------------------------------------------------

def test_scenario3_hypothesis_has_uniqueness_check():
    content = _content()
    assert "唯一性" in content or "uniqueness" in content.lower(), \
        "Hypothesis step must include uniqueness verification"


def test_scenario3_hypothesis_requires_eliminating_competing():
    content = _content()
    assert "竞争假设" in content or "competing hypothesis" in content.lower() \
           or "competing hypothes" in content.lower(), \
        "Uniqueness check must require eliminating competing hypotheses"


# ---------------------------------------------------------------------------
# Scenario 3 — Regression Check after TDD
# ---------------------------------------------------------------------------

def test_scenario3_has_regression_check_after_tdd():
    content = _content()
    assert "回归检查" in content or "regression check" in content.lower(), \
        "Scenario 3 must include explicit regression check after TDD"


def test_scenario3_regression_check_verifies_fix_presence():
    content = _content()
    # The regression check should confirm the bug is gone
    assert "已消失" in content or "bug is gone" in content.lower() \
           or "problem gone" in content.lower() or "fix verified" in content.lower() \
           or "问题.*消失" in content or "已修复" in content, \
        "Regression check must verify the bug is gone"


def test_scenario3_regression_check_verifies_no_side_effects():
    content = _content()
    # The regression check should confirm no regression in other features
    assert "未受影响" in content or "no regression" in content.lower() \
           or "unaffected" in content.lower(), \
        "Regression check must verify no side-effect regressions"


# ---------------------------------------------------------------------------
# Preservation — Scenario 1 and Scenario 2 unchanged
# ---------------------------------------------------------------------------

def test_scenario1_bug_list_display_preserved():
    content = _content()
    assert "Scenario 1" in content or "No Arguments" in content, \
        "Scenario 1 (no-args bug list) must still be present"
    assert "Bug Backlog" in content, \
        "Scenario 1 bug backlog display must remain intact"


def test_scenario2_three_phase_flow_preserved():
    content = _content()
    assert "Scenario 2" in content or "Bug Description" in content, \
        "Scenario 2 (bug description flow) must still be present"
    assert "Quick Verification" in content, \
        "Scenario 2 quick verification phase must remain intact"
    assert "Smart Scheduling" in content, \
        "Scenario 2 smart scheduling phase must remain intact"


def test_systematic_debugging_delegation_preserved():
    content = _content()
    assert "systematic-debugging" in content, \
        "systematic-debugging skill delegation must remain present"


def test_tdd_delegation_preserved():
    content = _content()
    assert "test-driven-development" in content, \
        "test-driven-development skill delegation must remain present"


def test_git_auto_delegation_preserved():
    content = _content()
    assert "progress-tracker:git-auto" in content, \
        "git-auto skill delegation must remain present"
