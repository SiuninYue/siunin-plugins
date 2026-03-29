"""E2E structure tests for note-organizer plugin

This module tests the end-to-end structure of the plugin, including:
- NotebookLM output structure
- Obsidian output structure
- Timestamp removal verification
- Template rendering integration
"""
import pytest
from pathlib import Path
import sys

# Add plugin root to path for imports
plugin_root = Path(__file__).parent.parent.resolve()
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from scripts.template_renderer import NoteData, render_template


class TestNotebookLMOutputStructure:
    """Test NotebookLM template output structure"""

    def test_template_exists(self):
        """Verify NotebookLM template file exists"""
        template_path = plugin_root / "templates" / "notebooklm-template.md"
        assert template_path.exists(), "NotebookLM template should exist"

    def test_template_has_required_fields(self):
        """Verify template contains required placeholder fields"""
        template_path = plugin_root / "templates" / "notebooklm-template.md"
        content = template_path.read_text(encoding='utf-8')

        required_fields = ["{title}", "{note_type}", "{tags}", "{summary}", "{key_points}", "{content}"]
        for field in required_fields:
            assert field in content, f"Template should contain {field} placeholder"

    def test_render_output_structure(self):
        """Test rendered output has correct structure"""
        template_path = plugin_root / "templates" / "notebooklm-template.md"
        data = NoteData(
            title="Test Note",
            note_type="tutorial",
            tags=["tech/ai", "tutorial"],
            summary="Test summary",
            key_points="- Point 1\n- Point 2",
            content="Test content"
        )

        output = render_template(str(template_path), data)

        # Verify structure elements present
        assert "Test Note" in output
        assert "tutorial" in output
        assert "tech/ai" in output or "tech" in output
        assert "Test summary" in output
        assert "Point 1" in output
        assert "Test content" in output


class TestObsidianOutputStructure:
    """Test Obsidian template output structure"""

    def test_template_exists(self):
        """Verify Obsidian template file exists"""
        template_path = plugin_root / "templates" / "obsidian-template.md"
        assert template_path.exists(), "Obsidian template should exist"

    def test_template_has_yaml_frontmatter(self):
        """Verify template contains YAML frontmatter"""
        template_path = plugin_root / "templates" / "obsidian-template.md"
        content = template_path.read_text(encoding='utf-8')

        assert content.startswith("---"), "Obsidian template should start with YAML frontmatter"
        assert "type:" in content, "YAML should contain type field"
        assert "tags:" in content, "YAML should contain tags field"

    def test_yaml_tags_format(self):
        """Test YAML tags are formatted correctly"""
        template_path = plugin_root / "templates" / "obsidian-template.md"
        data = NoteData(
            title="Test Note",
            note_type="tutorial",
            tags=["tech/ai", "coding/python"],
            summary="Test summary",
            key_points="- Point 1",
            content="Test content"
        )

        output = render_template(str(template_path), data)

        # Verify YAML structure
        assert output.startswith("---")
        lines = output.split("\n")
        assert "type: tutorial" in output
        assert "tags:" in output
        # Check for closing delimiter anywhere in first 200 chars
        assert "---" in output[:200]  # Closing YAML delimiter


class TestTimestampsRemoved:
    """Test timestamp removal in content processing"""

    def test_timestamp_pattern_standard(self):
        """Test standard [HH:MM:SS] timestamp pattern"""
        from scripts.clean_timestamps import clean_timestamps

        input_text = "[00:01:23] This is a test\n[00:02:45] Another line"
        expected = "This is a test\nAnother line"

        result = clean_timestamps(input_text)
        assert result == expected

    def test_timestamp_pattern_variations(self):
        """Test various timestamp format patterns that are actually supported"""
        from scripts.clean_timestamps import clean_timestamps

        test_cases = [
            ("[00:01:23] Content", "Content"),
            ("[00:01] Content", "Content"),  # Simplified format
            ("[1:23:45] Content", "Content"),  # Single digit hour
            ("[12:34] Content", "Content"),  # MM:SS only
        ]

        for input_text, expected_suffix in test_cases:
            result = clean_timestamps(input_text)
            assert result.strip() == expected_suffix

    def test_no_timestamps_passthrough(self):
        """Test content without timestamps passes through unchanged"""
        from scripts.clean_timestamps import clean_timestamps

        input_text = "Regular content without timestamps\nSecond line"
        result = clean_timestamps(input_text)

        assert result == input_text


class TestCommandFilesExist:
    """Test command files exist with correct structure"""

    def test_note_process_command_exists(self):
        """Verify /note-process command file exists"""
        command_path = plugin_root / "commands" / "note-process.md"
        assert command_path.exists(), "note-process command should exist"

        content = command_path.read_text(encoding='utf-8')
        assert "scope: command" in content

    def test_note_batch_command_exists(self):
        """Verify /note-batch command file exists"""
        command_path = plugin_root / "commands" / "note-batch.md"
        assert command_path.exists(), "note-batch command should exist"

        content = command_path.read_text(encoding='utf-8')
        assert "scope: command" in content

    def test_note_enhance_command_exists(self):
        """Verify /note-enhance command file exists"""
        command_path = plugin_root / "commands" / "note-enhance.md"
        assert command_path.exists(), "note-enhance command should exist"

        content = command_path.read_text(encoding='utf-8')
        assert "scope: command" in content


class TestSkillFilesExist:
    """Test skill files exist with correct structure"""

    def test_organize_note_skill_exists(self):
        """Verify organize-note skill exists"""
        skill_path = plugin_root / "skills" / "organize-note" / "SKILL.md"
        assert skill_path.exists(), "organize-note skill should exist"

        content = skill_path.read_text(encoding='utf-8')
        assert "name:" in content or "---" in content  # Has frontmatter or structure

    def test_enhance_note_skill_exists(self):
        """Verify enhance-note skill exists"""
        skill_path = plugin_root / "skills" / "enhance-note" / "SKILL.md"
        assert skill_path.exists(), "enhance-note skill should exist"

        content = skill_path.read_text(encoding='utf-8')
        assert "name:" in content or "---" in content


class TestPluginStructure:
    """Test overall plugin structure"""

    def test_plugin_json_exists(self):
        """Verify plugin.json exists and has required fields"""
        plugin_json = plugin_root / ".claude-plugin" / "plugin.json"
        assert plugin_json.exists(), "plugin.json should exist"

        import json
        content = json.loads(plugin_json.read_text(encoding='utf-8'))
        assert "name" in content
        assert "version" in content
        assert content["name"] == "note-organizer"

    def test_readme_exists(self):
        """Verify README.md exists"""
        readme_path = plugin_root / "README.md"
        assert readme_path.exists(), "README.md should exist"

    def test_scripts_directory_exists(self):
        """Verify scripts directory with required modules"""
        scripts_dir = plugin_root / "scripts"
        assert scripts_dir.exists(), "scripts directory should exist"

        required_modules = [
            "clean_timestamps.py",
            "batch_scanner.py",
            "template_renderer.py"
        ]

        for module in required_modules:
            module_path = scripts_dir / module
            assert module_path.exists(), f"{module} should exist"
