"""Tests for generated command docs tooling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import generate_prog_docs


def test_extract_source_block_success() -> None:
    source = """
<!-- SOURCE:README_EN:START -->
line-a
line-b
<!-- SOURCE:README_EN:END -->
"""
    block = generate_prog_docs.extract_source_block(source, "README_EN")
    assert block == "line-a\nline-b\n"


def test_extract_source_block_missing_markers() -> None:
    with pytest.raises(ValueError):
        generate_prog_docs.extract_source_block("no markers here", "README_EN")


def test_replace_generated_block_success() -> None:
    content = """
Header
<!-- BEGIN:GENERATED:PROG_COMMANDS -->
old
<!-- END:GENERATED:PROG_COMMANDS -->
Footer
"""
    replaced = generate_prog_docs.replace_generated_block(content, "new-content\n", "README.md")
    assert "new-content" in replaced
    assert "old" not in replaced


def test_generate_prog_docs_check_passes_current_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "hooks" / "scripts" / "generate_prog_docs.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
