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


# --- T3: EN/ZH 同步一致性 ---

def test_extract_source_blocks_both_en_and_zh() -> None:
    """When PROG_COMMANDS.md has both README_EN and README_ZH blocks,
    both are extracted as non-empty strings."""
    source = """
<!-- SOURCE:README_EN:START -->
/en command-1
/en command-2
<!-- SOURCE:README_EN:END -->

<!-- SOURCE:README_ZH:START -->
/zh command-1
/zh command-2
<!-- SOURCE:README_ZH:END -->
"""
    en = generate_prog_docs.extract_source_block(source, "README_EN")
    zh = generate_prog_docs.extract_source_block(source, "README_ZH")
    assert "/en command-1" in en
    assert "/en command-2" in en
    assert "/zh command-1" in zh
    assert "/zh command-2" in zh


def test_source_block_en_zh_not_mixed() -> None:
    """EN block must not leak ZH content and vice versa."""
    source = """
<!-- SOURCE:README_EN:START -->
/en only
<!-- SOURCE:README_EN:END -->

<!-- SOURCE:README_ZH:START -->
/zh only
<!-- SOURCE:README_ZH:END -->
"""
    en = generate_prog_docs.extract_source_block(source, "README_EN")
    zh = generate_prog_docs.extract_source_block(source, "README_ZH")
    assert "/zh only" not in en
    assert "/en only" not in zh


# --- T4: merge 后漂移 check-write-check 端到端 ---

def test_check_write_check_roundtrip_in_temp_repo(tmp_path: Path) -> None:
    """Roundtrip in an isolated temp dir: check passes on clean state,
    drift makes check fail, write fixes it, check passes again."""
    import textwrap

    script_root = Path(__file__).resolve().parents[1] / "hooks" / "scripts"
    gen_script = script_root / "generate_prog_docs.py"

    # 构造临时仓库（不依赖 git repo 或 ORIG_HEAD）
    repo = tmp_path / "repo"
    repo.mkdir()
    docs_dir = repo / "docs"
    docs_dir.mkdir()

    (docs_dir / "PROG_COMMANDS.md").write_text(textwrap.dedent("""\
        <!-- SOURCE:README_EN:START -->
        ## Commands

        | Command | Description |
        |---------|-------------|
        | /prog   | Status     |
        <!-- SOURCE:README_EN:END -->

        <!-- SOURCE:README_ZH:START -->
        ## 命令

        | 命令 | 描述 |
        |------|------|
        | /prog | 状态 |
        <!-- SOURCE:README_ZH:END -->

        <!-- SOURCE:PROG_HELP:START -->
        prog - Progress Tracker CLI
        <!-- SOURCE:PROG_HELP:END -->
    """))

    (repo / "README.md").write_text(textwrap.dedent("""\
        # Test

        <!-- BEGIN:GENERATED:PROG_COMMANDS -->
        <!-- GENERATED CONTENT: DO NOT EDIT DIRECTLY -->
        ## Commands

        | Command | Description |
        |---------|-------------|
        | /prog   | Status     |
        <!-- END:GENERATED:PROG_COMMANDS -->
    """))

    (repo / "readme-zh.md").write_text(textwrap.dedent("""\
        # 测试

        <!-- BEGIN:GENERATED:PROG_COMMANDS -->
        <!-- GENERATED CONTENT: DO NOT EDIT DIRECTLY -->
        ## 命令

        | 命令 | 描述 |
        |------|------|
        | /prog | 状态 |
        <!-- END:GENERATED:PROG_COMMANDS -->
    """))

    (docs_dir / "PROG_HELP.md").write_text(
        "<!-- GENERATED FROM docs/PROG_COMMANDS.md. DO NOT EDIT DIRECTLY. -->\n\n"
        "prog - Progress Tracker CLI\n"
    )

    base_cmd = [sys.executable, str(gen_script), "--project-root", str(repo)]

    # baseline check
    r = subprocess.run(
        base_cmd + ["--check"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, f"baseline check should pass: {r.stderr}"

    # simulate drift — corrupt the generated block
    readme = repo / "README.md"
    corrupted = readme.read_text().replace(
        "| /prog   | Status     |",
        "| /prog   | STALE FROM MERGE |",
    )
    readme.write_text(corrupted)

    # check must fail
    r = subprocess.run(
        base_cmd + ["--check"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode != 0, f"check should fail after drift: {r.returncode}: {r.stderr}"

    # --write fixes
    r = subprocess.run(
        base_cmd + ["--write"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, f"write should succeed: {r.stderr}"

    # check should pass again
    r = subprocess.run(
        base_cmd + ["--check"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, f"check should pass after write: {r.returncode}: {r.stderr}"

    # verify file no longer has stale content
    fixed = readme.read_text()
    assert "STALE FROM MERGE" not in fixed
    assert "| /prog   | Status     |" in fixed
