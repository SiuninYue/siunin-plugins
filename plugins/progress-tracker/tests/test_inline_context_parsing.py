"""
Inline context and Git Auto Result Block parsing contract tests.

These tests lock the behavior contracts for:
1. feature-implement Bucket/ProjectRoot inline context parsing
2. feature-complete === Git Auto Result === block parsing
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Helpers — lightweight parsers that mirror what SKILL.md instructs AI to do
# ---------------------------------------------------------------------------

def parse_inline_context(text: str) -> dict[str, Any]:
    """Parse inline context fields from a handoff block string.

    Returns a dict with parsed values and a 'warnings' list.
    Mirrors the parsing logic described in feature-implement/SKILL.md.
    """
    result: dict[str, Any] = {
        "feature_id": None,
        "feature_name": None,
        "phase": None,
        "plan_path": None,
        "plan_summary": None,
        "bucket": None,
        "project_root": None,
        "branch": None,
        "worktree_path": None,
        "questions": [],
        "warnings": [],
    }

    for line in text.splitlines():
        line = line.strip()

        if line.startswith("Feature:"):
            value = line[len("Feature:"):].strip()
            # Format: <id> "<name>" | Phase: <phase>
            m = re.match(r'(\S+)\s+"([^"]+)"\s*\|\s*Phase:\s*(\S+)', value)
            if m:
                result["feature_id"] = m.group(1)
                result["feature_name"] = m.group(2)
                result["phase"] = m.group(3)

        elif line.startswith("Phase:"):
            result["phase"] = line[len("Phase:"):].strip()

        elif line.startswith("Plan:"):
            result["plan_path"] = line[len("Plan:"):].strip()

        elif line.startswith("PlanSummary:"):
            result["plan_summary"] = line[len("PlanSummary:"):].strip()

        elif line.startswith("Bucket:"):
            bucket_val = line[len("Bucket:"):].strip()
            if bucket_val in ("simple", "standard", "complex"):
                result["bucket"] = bucket_val
            else:
                result["bucket"] = "standard"
                result["warnings"].append(
                    f"Bucket unknown, defaulting to standard (got: {bucket_val!r})"
                )

        elif line.startswith("ProjectRoot:"):
            result["project_root"] = line[len("ProjectRoot:"):].strip()

        elif line.startswith("Branch:"):
            value = line[len("Branch:"):].strip()
            # Branch may be followed by "| Worktree: <path>"
            if "| Worktree:" in value:
                parts = value.split("| Worktree:", 1)
                result["branch"] = parts[0].strip()
                result["worktree_path"] = parts[1].strip()
            else:
                result["branch"] = value

        elif line.startswith("Questions:"):
            raw = line[len("Questions:"):].strip()
            result["questions"] = [q.strip() for q in raw.split("|") if q.strip()]

    # Apply Bucket fallback: if still None after parsing, default to standard
    if result["bucket"] is None and result["phase"] == "planning:approved":
        result["bucket"] = "standard"
        result["warnings"].append("Bucket unknown, defaulting to standard")

    return result


def parse_git_auto_result(output: str) -> dict[str, Any]:
    """Parse the === Git Auto Result === block from git-auto output.

    Returns dict with commit_hash, pr, status, block_reason.
    Mirrors the parsing logic described in feature-complete/SKILL.md.
    """
    result: dict[str, Any] = {
        "commit_hash": None,
        "pr": None,
        "status": None,
        "block_reason": None,
    }

    in_block = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped == "=== Git Auto Result ===":
            in_block = True
            continue
        if stripped == "=== End Result ===":
            in_block = False
            continue
        if not in_block:
            continue

        if stripped.startswith("CommitHash:"):
            result["commit_hash"] = stripped[len("CommitHash:"):].strip()
        elif stripped.startswith("PR:"):
            result["pr"] = stripped[len("PR:"):].strip()
        elif stripped.startswith("Status:"):
            result["status"] = stripped[len("Status:"):].strip()
        elif stripped.startswith("BlockReason:"):
            result["block_reason"] = stripped[len("BlockReason:"):].strip()

    return result


# ---------------------------------------------------------------------------
# Tests — feature-implement Bucket/ProjectRoot inline context parsing
# ---------------------------------------------------------------------------

class TestInlineContextParsing:

    def test_planning_approved_bucket_routes_simple(self):
        """Bucket=simple → bucket field is 'simple'."""
        text = (
            'Feature: F1 "Auth" | Phase: planning:approved\n'
            "Bucket: simple\n"
            "ProjectRoot: /home/user/project\n"
            "Branch: feature/auth\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["bucket"] == "simple"
        assert ctx["warnings"] == []

    def test_planning_approved_bucket_routes_standard(self):
        """Bucket=standard → bucket field is 'standard'."""
        text = (
            'Feature: F2 "Search" | Phase: planning:approved\n'
            "Bucket: standard\n"
            "ProjectRoot: /home/user/project\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["bucket"] == "standard"
        assert ctx["warnings"] == []

    def test_planning_approved_bucket_routes_complex(self):
        """Bucket=complex → bucket field is 'complex'."""
        text = (
            'Feature: F3 "ML Pipeline" | Phase: planning:approved\n'
            "Bucket: complex\n"
            "ProjectRoot: /home/user/project\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["bucket"] == "complex"
        assert ctx["warnings"] == []

    def test_planning_approved_bucket_missing_defaults_standard(self):
        """Missing Bucket line for planning:approved → default standard + emit warning."""
        text = (
            'Feature: F4 "Dashboard" | Phase: planning:approved\n'
            "ProjectRoot: /home/user/project\n"
            "Branch: feature/dash\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["bucket"] == "standard"
        assert any("Bucket unknown, defaulting to standard" in w for w in ctx["warnings"])

    def test_planning_approved_bucket_invalid_defaults_standard(self):
        """Invalid Bucket value → default standard + emit warning."""
        text = (
            'Feature: F5 "Reports" | Phase: planning:approved\n'
            "Bucket: extreme\n"
            "ProjectRoot: /home/user/project\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["bucket"] == "standard"
        assert any("Bucket unknown, defaulting to standard" in w for w in ctx["warnings"])

    def test_projectroot_extracted_from_inline_context(self):
        """ProjectRoot line is parsed correctly."""
        text = (
            'Feature: F6 "Export" | Phase: execution\n'
            "ProjectRoot: /x/y/z\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["project_root"] == "/x/y/z"

    def test_questions_parsed_from_clarifying_block(self):
        """Questions field is split by pipe into list."""
        text = (
            'Feature: F7 "Payments" | Phase: planning:clarifying\n'
            "Questions: Use Stripe? | Need webhooks? | Async or sync?\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["questions"] == ["Use Stripe?", "Need webhooks?", "Async or sync?"]

    def test_plan_summary_parsed(self):
        """PlanSummary is extracted as a single string."""
        text = (
            'Feature: F8 "Notifications" | Phase: planning:draft\n'
            "PlanSummary: Add email service; add webhook support; store events\n"
        )
        ctx = parse_inline_context(text)
        assert ctx["plan_summary"] == "Add email service; add webhook support; store events"


# ---------------------------------------------------------------------------
# Tests — feature-complete === Git Auto Result === block parsing
# ---------------------------------------------------------------------------

class TestGitAutoResultParsing:

    def test_git_auto_result_block_extracts_commit_hash(self):
        """Parses CommitHash from result block."""
        output = (
            "=== Git Auto Result ===\n"
            "CommitHash: abc123def456abc123def456abc123def456abc1\n"
            "PR: https://github.com/org/repo/pull/42\n"
            "Status: ok\n"
            "=== End Result ==="
        )
        result = parse_git_auto_result(output)
        assert result["commit_hash"] == "abc123def456abc123def456abc123def456abc1"
        assert result["status"] == "ok"
        assert result["pr"] == "https://github.com/org/repo/pull/42"
        assert result["block_reason"] is None

    def test_git_auto_result_block_blocked_returns_reason(self):
        """Status=blocked extracts BlockReason."""
        output = (
            "=== Git Auto Result ===\n"
            "CommitHash: none\n"
            "PR: none\n"
            "Status: blocked\n"
            "BlockReason: merge conflict in src/main.py\n"
            "=== End Result ==="
        )
        result = parse_git_auto_result(output)
        assert result["status"] == "blocked"
        assert result["commit_hash"] == "none"
        assert result["block_reason"] == "merge conflict in src/main.py"

    def test_git_auto_result_block_ignored_outside_markers(self):
        """Content outside markers is not parsed."""
        output = (
            "CommitHash: should_be_ignored\n"
            "=== Git Auto Result ===\n"
            "CommitHash: real_sha_here\n"
            "Status: ok\n"
            "=== End Result ===\n"
            "CommitHash: also_ignored\n"
        )
        result = parse_git_auto_result(output)
        assert result["commit_hash"] == "real_sha_here"

    def test_git_auto_result_status_ok_no_block_reason(self):
        """Status=ok result has no block_reason."""
        output = (
            "=== Git Auto Result ===\n"
            "CommitHash: deadbeef00000000000000000000000000000001\n"
            "PR: none\n"
            "Status: ok\n"
            "=== End Result ==="
        )
        result = parse_git_auto_result(output)
        assert result["status"] == "ok"
        assert result["block_reason"] is None
