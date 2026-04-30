#!/usr/bin/env python3
"""Contract tests for SPM planning command set."""

from __future__ import annotations

import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = PLUGIN_ROOT / "commands"
SKILLS_DIR = PLUGIN_ROOT / "skills"

PLANNING_COMMANDS = (
    "office-hours",
    "plan-ceo-review",
    "plan-design-review",
    "plan-devex-review",
)


def _frontmatter(content: str) -> str:
    assert content.startswith("---\n")
    end = content.find("\n---\n", 4)
    assert end != -1
    return content[4:end]


def test_planning_command_files_exist_with_required_frontmatter() -> None:
    for name in PLANNING_COMMANDS:
        command_path = COMMANDS_DIR / f"{name}.md"
        assert command_path.exists(), f"missing command file: {command_path}"
        frontmatter = _frontmatter(command_path.read_text(encoding="utf-8"))

        assert re.search(r"^scope:\s*command$", frontmatter, re.MULTILINE)
        assert re.search(r'^version:\s*"\d+\.\d+\.\d+"$', frontmatter, re.MULTILINE)
        assert re.search(r"^description:\s*.+", frontmatter, re.MULTILINE)


def test_office_hours_enforces_planner_only_boundary() -> None:
    content = (COMMANDS_DIR / "office-hours.md").read_text(encoding="utf-8")
    assert "技术实现路径" in content


def test_optional_lane_commands_document_auto_suggestion() -> None:
    for name in ("plan-design-review", "plan-devex-review"):
        content = (COMMANDS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert "自动建议" in content


def _parse_references(frontmatter: str) -> list[str]:
    """Extract list items under 'references:' key from YAML-like frontmatter."""
    refs: list[str] = []
    in_refs = False
    for line in frontmatter.splitlines():
        if re.match(r"^references\s*:", line):
            in_refs = True
            continue
        if in_refs:
            m = re.match(r"^\s+-\s+(.+)", line)
            if m:
                refs.append(m.group(1).strip())
            elif re.match(r"^\S", line):
                break
    return refs


def test_planning_commands_reference_skill_files_that_exist() -> None:
    """Each planning command's references: field must point to an existing SKILL.md."""
    for name in PLANNING_COMMANDS:
        command_path = COMMANDS_DIR / f"{name}.md"
        raw_fm = _frontmatter(command_path.read_text(encoding="utf-8"))
        refs = _parse_references(raw_fm)
        assert refs, f"{name}.md has empty references: field — must point to skill SKILL.md"
        for ref in refs:
            resolved = (command_path.parent / ref).resolve()
            assert resolved.exists(), (
                f"{name}.md references '{ref}' but resolved path does not exist: {resolved}"
            )


def test_planning_skill_files_contain_subagent_review_instruction() -> None:
    """Each planning skill SKILL.md must contain sub-agent review keywords."""
    skill_dirs = {
        "office-hours": SKILLS_DIR / "office-hours" / "SKILL.md",
        "plan-ceo-review": SKILLS_DIR / "plan-ceo-review" / "SKILL.md",
        "plan-design-review": SKILLS_DIR / "plan-design-review" / "SKILL.md",
        "plan-devex-review": SKILLS_DIR / "plan-devex-review" / "SKILL.md",
    }
    required_keywords = ["Agent", "completeness/consistency/clarity/scope/feasibility"]
    for skill_name, skill_path in skill_dirs.items():
        assert skill_path.exists(), f"missing skill file: {skill_path}"
        content = skill_path.read_text(encoding="utf-8")
        for kw in required_keywords:
            assert kw in content, (
                f"skill '{skill_name}' missing required sub-agent review keyword: '{kw}'"
            )


def test_planning_skill_subagent_review_handles_severity_levels() -> None:
    """Each planning skill SKILL.md must describe both blocking and advisory severity handling."""
    skill_dirs = [
        SKILLS_DIR / name / "SKILL.md"
        for name in ("office-hours", "plan-ceo-review", "plan-design-review", "plan-devex-review")
    ]
    for skill_path in skill_dirs:
        content = skill_path.read_text(encoding="utf-8")
        assert "blocking" in content, f"{skill_path.parent.name}: missing 'blocking' severity handling"
        assert "advisory" in content, f"{skill_path.parent.name}: missing 'advisory' severity handling"


def test_planning_skill_fix_iteration_uses_sync_planning_update_status() -> None:
    """Each planning skill SKILL.md must instruct fix iteration to use sync_planning_update(category=status)."""
    skill_dirs = [
        SKILLS_DIR / name / "SKILL.md"
        for name in ("office-hours", "plan-ceo-review", "plan-design-review", "plan-devex-review")
    ]
    for skill_path in skill_dirs:
        content = skill_path.read_text(encoding="utf-8")
        assert 'sync_planning_update' in content, (
            f"{skill_path.parent.name}: missing sync_planning_update call in fix iteration instructions"
        )
        assert 'category="status"' in content or "category=status" in content, (
            f"{skill_path.parent.name}: fix iteration must use category=status, not bare add-update"
        )
