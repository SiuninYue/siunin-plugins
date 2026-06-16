import sys
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import render_changelog_from_index

@pytest.fixture
def temp_project(tmp_path):
    project_root = tmp_path / "progress-tracker"
    project_root.mkdir()
    
    docs_dir = project_root / "docs" / "changes"
    docs_dir.mkdir(parents=True)
    
    # Write sample index.jsonl with unsorted dates/ids
    index_file = docs_dir / "index.jsonl"
    index_file.write_text(
        '{"change_id": "20260603-boundary-fix-r0-c4f2", "date": "2026-06-03", "component": "a", "summary": "Fix b", "record_path": "docs/changes/20260603-boundary-fix-r0.md"}\n'
        '{"change_id": "20260521-pm-modularize-a7d2", "date": "2026-05-21", "component": "c", "summary": "Split PM", "record_path": "docs/changes/20260521-pm-modularize-a7d2.md"}\n',
        encoding="utf-8"
    )
    
    # Write CHANGELOG.md with markers
    changelog_file = project_root / "CHANGELOG.md"
    changelog_file.write_text(
        "# Changelog\n\n## [Unreleased]\n\nManual stuff here\n\n<!-- START_F19_MANAGED_BLOCK -->\n<!-- END_F19_MANAGED_BLOCK -->\n\n## [1.6.28] — 2026-06-14\n\nLegacy history remains stable.\n",
        encoding="utf-8"
    )
    
    return project_root

def test_renderer_generates_stable_sorted_changelog(temp_project):
    changelog_file = temp_project / "CHANGELOG.md"
    
    with patch("sys.exit") as mock_exit:
        with patch("sys.argv", ["render_changelog_from_index.py", "--project-root", str(temp_project)]):
            render_changelog_from_index.main()
            mock_exit.assert_called_once_with(0)
            
    updated_changelog = changelog_file.read_text(encoding="utf-8")
    
    # Verify legacy section is untouched
    assert "Legacy history remains stable." in updated_changelog
    assert "Manual stuff here" in updated_changelog
    
    # Verify sorted output: 05-21 comes before 06-03
    assert "<!-- START_F19_MANAGED_BLOCK -->\n### AI Traceable Changes\n" in updated_changelog
    first_idx = updated_changelog.find("20260521-pm-modularize-a7d2")
    second_idx = updated_changelog.find("20260603-boundary-fix-r0-c4f2")
    assert first_idx != -1
    assert second_idx != -1
    assert first_idx < second_idx

def test_renderer_missing_markers_fails(temp_project):
    changelog_file = temp_project / "CHANGELOG.md"
    # Overwrite without markers
    changelog_file.write_text("# Changelog\n", encoding="utf-8")
    
    with patch("sys.exit") as mock_exit:
        with patch("sys.argv", ["render_changelog_from_index.py", "--project-root", str(temp_project)]):
            render_changelog_from_index.main()
            mock_exit.assert_called_once_with(1)
