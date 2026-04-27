#!/usr/bin/env python3
"""Contract tests for project-memory skill integration in /prog flows."""

from __future__ import annotations

import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
VALID_DECLARED_MODELS = {"haiku", "sonnet", "opus"}


def _extract_frontmatter(content: str) -> str:
    if not content.startswith("---\n"):
        return ""
    end = content.find("\n---\n", 4)
    if end == -1:
        return ""
    return content[4:end]


def _required_skill_scopes_from_commands() -> set[str]:
    scopes: set[str] = set()
    pattern = re.compile(r'skill:\s*"progress-tracker:([A-Za-z0-9_-]+)"')
    for command_path in sorted((PLUGIN_ROOT / "commands").glob("*.md")):
        content = command_path.read_text(encoding="utf-8")
        scopes.update(pattern.findall(content))
    return scopes


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


def test_command_required_skills_declare_valid_models():
    """Every command-required skill scope should explicitly declare a supported model."""
    required_scopes = sorted(_required_skill_scopes_from_commands())
    assert required_scopes, "Expected at least one required skill scope from commands/*.md"

    missing_skill_files: list[str] = []
    missing_model: list[str] = []
    invalid_model: list[str] = []

    for scope in required_scopes:
        skill_path = PLUGIN_ROOT / "skills" / scope / "SKILL.md"
        if not skill_path.exists():
            missing_skill_files.append(scope)
            continue

        content = skill_path.read_text(encoding="utf-8")
        frontmatter = _extract_frontmatter(content)
        model_match = re.search(r"^model:\s*(.+)$", frontmatter, re.MULTILINE)
        if not model_match:
            missing_model.append(scope)
            continue

        model_value = model_match.group(1).strip().strip("\"'")
        if model_value not in VALID_DECLARED_MODELS:
            invalid_model.append(f"{scope}={model_value}")

    assert not missing_skill_files, f"Missing SKILL.md for required scopes: {missing_skill_files}"
    assert not missing_model, f"Missing frontmatter model declaration in scopes: {missing_model}"
    assert not invalid_model, (
        f"Unsupported model declarations in required scopes: {invalid_model}; "
        f"expected one of {sorted(VALID_DECLARED_MODELS)}"
    )
