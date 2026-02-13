#!/usr/bin/env python3
"""Quick validator for progress-tracker skill/document consistency."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


MAIN_SKILLS = [
    "skills/feature-implement/SKILL.md",
    "skills/feature-complete/SKILL.md",
    "skills/progress-recovery/SKILL.md",
]

REQUIRED_DESCRIPTION_TOKENS = {
    "skills/feature-breakdown/SKILL.md": ["/prog init"],
    "skills/architectural-planning/SKILL.md": ["/prog plan"],
    "skills/progress-management/SKILL.md": ["/prog reset", "/prog undo"],
    "skills/progress-recovery/SKILL.md": ["/prog"],
    "skills/bug-fix/SKILL.md": ["/prog-fix"],
}

REQUIRED_REFERENCE_FILES = [
    "skills/feature-implement/references/session-playbook.md",
    "skills/feature-complete/references/verification-playbook.md",
    "skills/feature-complete/references/session-examples.md",
    "skills/progress-recovery/references/scenario-playbook.md",
    "skills/progress-recovery/references/communication-templates.md",
]


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def word_count(text: str) -> int:
    return len(text.split())


def extract_frontmatter(path: Path) -> str:
    text = read_text(path)
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    if end == -1:
        return ""
    return text[4:end]


def check_description_tokens(root: Path, errors: list[str]) -> None:
    for rel_path, tokens in REQUIRED_DESCRIPTION_TOKENS.items():
        path = root / rel_path
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue

        frontmatter = extract_frontmatter(path)
        description_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
        description = description_match.group(1) if description_match else ""
        for token in tokens:
            if token not in description:
                errors.append(f"Missing description token '{token}' in {path}")


def check_bug_fix_contract(root: Path, errors: list[str]) -> None:
    bug_fix_dir = root / "skills" / "bug-fix"
    if not bug_fix_dir.exists():
        errors.append(f"Missing bug-fix directory: {bug_fix_dir}")
        return

    content = "\n".join(
        p.read_text(encoding="utf-8")
        for p in bug_fix_dir.rglob("*.md")
        if p.is_file()
    )

    if re.search(r"--commit-hash|\bcommit-hash\b", content):
        errors.append("Found deprecated '--commit-hash' usage in skills/bug-fix")

    if "superpowers:code-reviewer" in content:
        errors.append("Found deprecated 'superpowers:code-reviewer' in skills/bug-fix")

    if re.search(r"\bpython3\s+progress_manager\.py\b", content):
        errors.append("Found bare 'python3 progress_manager.py' path in skills/bug-fix")

    if "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py" not in content:
        errors.append("Missing '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py' usage in skills/bug-fix")


def check_main_skill_word_counts(root: Path, errors: list[str]) -> None:
    for rel_path in MAIN_SKILLS:
        path = root / rel_path
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue
        count = word_count(read_text(path))
        if count > 2000:
            errors.append(f"Word count exceeds 2000 in {path}: {count}")


def check_required_references(root: Path, errors: list[str]) -> None:
    for rel_path in REQUIRED_REFERENCE_FILES:
        path = root / rel_path
        if not path.exists():
            errors.append(f"Missing reference file: {path}")


def check_generated_docs_sync(root: Path, errors: list[str]) -> None:
    script = root / "hooks" / "scripts" / "generate_prog_docs.py"
    if not script.exists():
        errors.append(f"Missing generate script: {script}")
        return

    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "generate_prog_docs.py --check failed"
        errors.append(f"Generated docs drift detected: {details}")


def run_checks(root: Path, *, run_docs_check: bool = True) -> list[str]:
    errors: list[str] = []

    check_bug_fix_contract(root, errors)
    check_description_tokens(root, errors)
    check_main_skill_word_counts(root, errors)
    check_required_references(root, errors)
    if run_docs_check:
        check_generated_docs_sync(root, errors)

    return errors


def main() -> int:
    root = plugin_root()
    errors = run_checks(root)
    if errors:
        print("Quick validation failed:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("Quick validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
