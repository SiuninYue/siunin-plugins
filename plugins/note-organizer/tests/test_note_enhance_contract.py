"""Contract tests for note-enhance command and enhance-note skill."""
from pathlib import Path
import re


TEST_FILE = Path(__file__).resolve()
PLUGIN_ROOT = TEST_FILE.parent.parent.resolve()

COMMAND_PATH = PLUGIN_ROOT / "commands" / "note-enhance.md"
SKILL_PATH = PLUGIN_ROOT / "skills" / "enhance-note" / "SKILL.md"


def _read_text(path: Path) -> str:
    assert path.exists(), f"Expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def _extract_frontmatter(md_text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", md_text, flags=re.DOTALL)
    assert match, "Markdown file should contain YAML frontmatter"
    return match.group(1)


def test_note_enhance_command_exists():
    assert COMMAND_PATH.exists(), f"Command should exist: {COMMAND_PATH}"


def test_enhance_note_skill_exists():
    assert SKILL_PATH.exists(), f"Skill should exist: {SKILL_PATH}"


def test_note_enhance_command_frontmatter_contract():
    command_text = _read_text(COMMAND_PATH)
    frontmatter = _extract_frontmatter(command_text)

    assert "scope: command" in frontmatter
    assert "description: 增强不完整内容并输出结构化笔记（填充/优化/改写/扩展）" in frontmatter
    assert "- ../skills/enhance-note/SKILL.md" in frontmatter
    assert "argument-hint:" in frontmatter


def test_note_enhance_command_flags_and_defaults():
    command_text = _read_text(COMMAND_PATH)

    for flag in ("--mode", "--obsidian", "--output", "--out-dir"):
        assert flag in command_text, f"{flag} should be documented in command contract"

    assert "默认 `all`" in command_text
    assert "默认 NotebookLM" in command_text
    assert "./enhanced-notes" in command_text


def test_note_enhance_command_routes_to_namespaced_skill_only():
    command_text = _read_text(COMMAND_PATH)

    assert "note-organizer:enhance-note" in command_text
    assert "note-organizer:note-enhance" not in command_text


def test_enhance_note_skill_frontmatter_contract():
    skill_text = _read_text(SKILL_PATH)
    frontmatter = _extract_frontmatter(skill_text)

    assert "name: enhance-note" in frontmatter
    assert "scope: skill" in frontmatter
    assert "fill | optimize | rewrite | expand | all" in frontmatter
    assert "notebooklm | obsidian" in frontmatter


def test_enhance_note_skill_covers_required_modes():
    skill_text = _read_text(SKILL_PATH)

    for mode in ("`fill`", "`optimize`", "`rewrite`", "`expand`", "`all`"):
        assert mode in skill_text, f"{mode} should be covered in skill mode definitions"


def test_enhance_note_skill_declares_required_output_sections():
    skill_text = _read_text(SKILL_PATH)

    required_sections = (
        "增强正文（严格原文事实）",
        "信息缺口与追问清单",
        "推断草案附录",
        "变更摘要",
    )
    for section in required_sections:
        assert section in skill_text, f"Skill should include output section: {section}"


def test_enhance_note_skill_enforces_dual_track_fact_policy():
    skill_text = _read_text(SKILL_PATH)

    assert "正文" in skill_text and "严格基于原文事实" in skill_text
    assert "[推断]" in skill_text


def test_enhance_note_skill_has_no_command_self_reference():
    skill_text = _read_text(SKILL_PATH)
    assert "/note-enhance" not in skill_text, \
        "Skill should not self-reference the command to avoid command-skill loops"
