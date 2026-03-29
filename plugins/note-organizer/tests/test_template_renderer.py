"""Tests for template_renderer module"""
import pytest
from pathlib import Path
import sys

# Add plugin root to path for imports
plugin_root = Path(__file__).parent.parent.resolve()
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from scripts.template_renderer import NoteData, format_tags_list
try:
    from scripts.template_renderer import format_tags_yaml
    _has_format_tags_yaml = True
except ImportError:
    _has_format_tags_yaml = False
try:
    from scripts.template_renderer import format_inline_tags
    _has_format_inline_tags = True
except ImportError:
    _has_format_inline_tags = False
try:
    from scripts.template_renderer import render_template
    _has_render = True
except ImportError:
    _has_render = False

try:
    from scripts.template_renderer import main
    _has_main = True
except ImportError:
    _has_main = False


class TestFormatTagsList:
    """Test format_tags_list function"""

    def test_empty_list(self):
        result = format_tags_list([])
        assert result == ""

    def test_single_tag(self):
        result = format_tags_list(["tech/ai"])
        assert result == "tech/ai"

    def test_multiple_tags(self):
        result = format_tags_list(["tech/ai", "tutorial"])
        assert result == "tech/ai, tutorial"


@pytest.mark.skipif(not _has_format_tags_yaml, reason="format_tags_yaml not implemented yet")
class TestFormatTagsYaml:
    """Test format_tags_yaml function"""

    def test_empty_list(self):
        result = format_tags_yaml([])
        assert result == ""

    def test_single_tag(self):
        result = format_tags_yaml(["tech/ai"])
        assert result == "\n  - tech/ai"

    def test_multiple_tags(self):
        result = format_tags_yaml(["tech/ai", "tutorial"])
        assert result == "\n  - tech/ai\n  - tutorial"


@pytest.mark.skipif(not _has_format_inline_tags, reason="format_inline_tags not implemented yet")
class TestFormatInlineTags:
    """Test format_inline_tags function"""

    def test_empty_list(self):
        result = format_inline_tags([])
        assert result == ""

    def test_single_tag(self):
        result = format_inline_tags(["tech/ai"])
        assert result == "#tech/ai"

    def test_multiple_tags(self):
        result = format_inline_tags(["tech/ai", "tutorial"])
        assert result == "#tech/ai #tutorial"


class TestNoteDataValidation:
    """Test NoteData.validate method"""

    def test_valid_data(self):
        data = NoteData(
            title="Test Title",
            note_type="tutorial",
            tags=["tech/ai"],
            summary="A summary",
            key_points="- Point 1",
            content="Content"
        )
        data.validate()  # Should not raise

    def test_empty_title_raises_value_error(self):
        data = NoteData(
            title="",
            note_type="tutorial",
            tags=[],
            summary="Summary",
            key_points="- Point",
            content="Content"
        )
        with pytest.raises(ValueError, match="title"):
            data.validate()

    def test_empty_note_type_raises_value_error(self):
        data = NoteData(
            title="Title",
            note_type="",
            tags=[],
            summary="Summary",
            key_points="- Point",
            content="Content"
        )
        with pytest.raises(ValueError, match="note_type"):
            data.validate()

    def test_tags_wrong_type_raises_type_error(self):
        """TypeError is raised when tags is not a list"""
        with pytest.raises(TypeError, match="tags.*list"):
            NoteData(
                title="Title",
                note_type="tutorial",
                tags="not-a-list",  # type: ignore
                summary="Summary",
                key_points="- Point",
                content="Content"
            ).validate()


@pytest.mark.skipif(not _has_render, reason="render_template not implemented yet")
class TestRenderTemplate:
    """Test render_template function"""

    def test_render_basic(self, tmp_path):
        # Create a test template
        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n类型: {note_type}\n标签: {tags}\n")

        data = NoteData(
            title="Test Title",
            note_type="tutorial",
            tags=["tech/ai", "tutorial"],
            summary="Summary",
            key_points="- Point 1\n- Point 2",
            content="Content"
        )

        result = render_template(str(template_file), data)

        assert "# Test Title" in result
        assert "类型: tutorial" in result
        assert "标签: tech/ai, tutorial" in result

    def test_render_obsidian_template(self, tmp_path):
        """Test rendering Obsidian-style template with YAML frontmatter"""
        # Create test Obsidian template
        template_file = tmp_path / "test-obsidian.md"
        template_file.write_text("""---
type: {note_type}
tags:{tags_yaml}
created: {created}
cssclass: {note_type}
---

# {title}

{summary}
""")

        # Test data
        data = NoteData(
            title="Test Note",
            note_type="tutorial",
            tags=["python", "testing"],
            summary="Test summary",
            key_points="- Point 1",
            content="Test content"
        )

        # Render and verify
        result = render_template(str(template_file), data)
        assert "type: tutorial" in result
        assert "- python" in result
        assert "- testing" in result
        assert "cssclass: tutorial" in result
        assert "# Test Note" in result
        assert "Test summary" in result

    def test_template_not_found_raises_file_not_found_error(self):
        data = NoteData(
            title="Title",
            note_type="tutorial",
            tags=[],
            summary="S",
            key_points="- P",
            content="C"
        )
        with pytest.raises(FileNotFoundError):
            render_template("nonexistent-template.md", data)

    def test_template_undefined_placeholder_raises_key_error(self, tmp_path):
        # Template with undefined placeholder
        template_file = tmp_path / "bad-template.md"
        template_file.write_text("# {title}\n{undefined_field}\n")

        data = NoteData(
            title="Title",
            note_type="tutorial",
            tags=[],
            summary="S",
            key_points="- P",
            content="C"
        )

        with pytest.raises(KeyError):
            render_template(str(template_file), data)


@pytest.mark.skipif(not _has_main, reason="CLI not implemented yet")
class TestCLI:
    """Test CLI interface"""

    def test_stdin_input(self, tmp_path, capsys):
        import subprocess
        import json

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n{content}\n")

        input_data = {
            "title": "CLI Test",
            "note_type": "tutorial",
            "tags": ["test"],
            "summary": "S",
            "key_points": "- P",
            "content": "Content from stdin"
        }

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            cwd=str(plugin_root)
        )

        assert result.returncode == 0
        assert "# CLI Test" in result.stdout
        assert "Content from stdin" in result.stdout

    def test_file_input_with_flag(self, tmp_path, capsys):
        import subprocess

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n{content}\n")

        input_file = tmp_path / "input.json"
        input_file.write_text('{"title": "File Test", "note_type": "tutorial", "tags": [], "summary": "S", "key_points": "- P", "content": "Content"}')

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file), "--input", str(input_file)],
            capture_output=True,
            text=True,
            cwd=str(plugin_root)
        )

        assert result.returncode == 0
        assert "# File Test" in result.stdout

    def test_invalid_json_exits_with_code_3(self, tmp_path):
        import subprocess

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n{content}\n")

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file)],
            input="invalid json{",
            capture_output=True,
            text=True,
            cwd=str(plugin_root)
        )

        assert result.returncode == 3

    def test_missing_template_exits_with_code_1(self, tmp_path):
        import subprocess

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", "nonexistent.md"],
            input='{"title": "T", "note_type": "t", "tags": [], "summary": "S", "key_points": "- P", "content": "C"}',
            capture_output=True,
            text=True,
            cwd=str(plugin_root)
        )

        assert result.returncode == 1

    def test_empty_field_exits_with_code_2(self, tmp_path):
        import subprocess

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n")

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file)],
            input='{"title": "", "note_type": "t", "tags": [], "summary": "S", "key_points": "- P", "content": "C"}',
            capture_output=True,
            text=True,
            cwd=str(plugin_root)
        )

        assert result.returncode == 2
