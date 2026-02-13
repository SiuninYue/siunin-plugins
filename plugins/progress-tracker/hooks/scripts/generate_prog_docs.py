#!/usr/bin/env python3
"""Generate command documentation from docs/PROG_COMMANDS.md.

Supports two modes:
- --write: update generated targets
- --check: validate targets are up to date (non-zero on drift)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SOURCE_BLOCK_START = "<!-- SOURCE:{name}:START -->"
SOURCE_BLOCK_END = "<!-- SOURCE:{name}:END -->"

TARGET_BLOCK_START = "<!-- BEGIN:GENERATED:PROG_COMMANDS -->"
TARGET_BLOCK_END = "<!-- END:GENERATED:PROG_COMMANDS -->"
TARGET_BLOCK_NOTE = "<!-- GENERATED CONTENT: DO NOT EDIT DIRECTLY -->"


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def extract_source_block(source_text: str, name: str) -> str:
    start = SOURCE_BLOCK_START.format(name=name)
    end = SOURCE_BLOCK_END.format(name=name)
    if start not in source_text or end not in source_text:
        raise ValueError(f"Missing source block markers for {name}")

    start_idx = source_text.index(start) + len(start)
    end_idx = source_text.index(end)
    block = source_text[start_idx:end_idx].strip("\n")
    return block + "\n"


def render_generated_block(block_text: str) -> str:
    return (
        f"{TARGET_BLOCK_START}\n"
        f"{TARGET_BLOCK_NOTE}\n"
        f"{block_text.rstrip()}\n"
        f"{TARGET_BLOCK_END}"
    )


def replace_generated_block(content: str, block_text: str, target_name: str) -> str:
    if TARGET_BLOCK_START not in content or TARGET_BLOCK_END not in content:
        raise ValueError(f"Missing generated markers in {target_name}")

    start_idx = content.index(TARGET_BLOCK_START)
    end_idx = content.index(TARGET_BLOCK_END) + len(TARGET_BLOCK_END)
    return content[:start_idx] + render_generated_block(block_text) + content[end_idx:]


def render_prog_help(block_text: str) -> str:
    return (
        "<!-- GENERATED FROM docs/PROG_COMMANDS.md. DO NOT EDIT DIRECTLY. -->\n\n"
        f"{block_text.rstrip()}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PROG command docs")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Write generated content")
    mode.add_argument("--check", action="store_true", help="Check generated content")
    args = parser.parse_args()

    root = plugin_root()
    source_path = root / "docs" / "PROG_COMMANDS.md"
    readme_en_path = root / "README.md"
    readme_zh_path = root / "readme-zh.md"
    help_path = root / "docs" / "PROG_HELP.md"

    source_text = source_path.read_text(encoding="utf-8")
    source_en = extract_source_block(source_text, "README_EN")
    source_zh = extract_source_block(source_text, "README_ZH")
    source_help = extract_source_block(source_text, "PROG_HELP")

    readme_en_current = readme_en_path.read_text(encoding="utf-8")
    readme_zh_current = readme_zh_path.read_text(encoding="utf-8")
    help_current = help_path.read_text(encoding="utf-8") if help_path.exists() else ""

    readme_en_expected = replace_generated_block(readme_en_current, source_en, readme_en_path.name)
    readme_zh_expected = replace_generated_block(readme_zh_current, source_zh, readme_zh_path.name)
    help_expected = render_prog_help(source_help)

    changes: list[tuple[Path, str, str]] = []
    if readme_en_current != readme_en_expected:
        changes.append((readme_en_path, readme_en_current, readme_en_expected))
    if readme_zh_current != readme_zh_expected:
        changes.append((readme_zh_path, readme_zh_current, readme_zh_expected))
    if help_current != help_expected:
        changes.append((help_path, help_current, help_expected))

    if args.check:
        if changes:
            print("Generated docs are out of date:")
            for path, _, _ in changes:
                print(f"- {path}")
            return 1
        print("Generated docs are up to date.")
        return 0

    for path, _, expected in changes:
        path.write_text(expected, encoding="utf-8")
        print(f"Updated {path}")

    if not changes:
        print("No changes needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
