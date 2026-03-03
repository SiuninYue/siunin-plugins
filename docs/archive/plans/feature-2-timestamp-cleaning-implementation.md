# Timestamp Cleaning Module Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Python CLI module that removes video transcription timestamps from text.

**Architecture:** Simple regex-based cleaning with `fileinput` module for flexible CLI input (files/stdin/multi-files). TDD approach with pytest.

**Tech Stack:** Python 3, re (regex), fileinput, pytest

---

## Task 1: Create clean_timestamps.py module skeleton

**Files:**
- Create: `plugins/note-organizer/scripts/clean_timestamps.py`

**Step 1: Create the file with shebang and module structure**

```python
#!/usr/bin/env python3
"""时间戳清理模块 - 移除视频转录格式的时间戳"""
import re
import fileinput
import sys

# 正则模式：匹配 [HH:MM:SS] 或 [MM:SS] 格式
TIMESTAMP_PATTERN = re.compile(r'\[\d{1,2}:\d{2}(?::\d{2})?\]\s*')


def clean_timestamps(text: str) -> str:
    """移除文本中的时间戳标记

    Args:
        text: 包含可能的时间戳的文本

    Returns:
        移除时间戳后的文本
    """
    return TIMESTAMP_PATTERN.sub('', text)


def main():
    """CLI 入口：处理输入并输出清理后的内容"""
    for line in fileinput.input():
        print(clean_timestamps(line), end='')


if __name__ == '__main__':
    main()
```

**Step 2: Make the file executable**

Run: `chmod +x plugins/note-organizer/scripts/clean_timestamps.py`
Expected: No error

**Step 3: Verify CLI help works**

Run: `cd plugins/note-organizer && python3 scripts/clean_timestamps.py --help`
Expected: No output (fileinput doesn't have --help by default, this is expected)

**Step 4: Commit**

```bash
git add plugins/note-organizer/scripts/clean_timestamps.py
git commit -m "feat(note-organizer): add clean_timestamps.py module skeleton

- Add shebang for executable support
- Implement clean_timestamps() function with regex
- Add main() CLI entry point using fileinput

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Create test file with basic timestamp removal test

**Files:**
- Create: `plugins/note-organizer/tests/test_clean_timestamps.py`

**Step 1: Write the failing test**

```python
"""测试时间戳清理模块"""
import pytest
from pathlib import Path
import sys
import subprocess

# Add plugin root to path for imports
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from scripts.clean_timestamps import clean_timestamps, TIMESTAMP_PATTERN


def test_basic_timestamp_removal_hh_mm_ss():
    """测试基本时间戳移除 [HH:MM:SS] 格式"""
    input_text = "[00:01:23] 这是测试内容"
    result = clean_timestamps(input_text)
    assert result == "这是测试内容"


def test_basic_timestamp_removal_mm_ss():
    """测试基本时间戳移除 [MM:SS] 格式"""
    input_text = "[01:23] 这是测试内容"
    result = clean_timestamps(input_text)
    assert result == "这是测试内容"


def test_timestamp_with_leading_space():
    """测试时间戳后有空格的情况"""
    input_text = "[00:01:23] 测试内容"
    result = clean_timestamps(input_text)
    assert result == "测试内容"
```

**Step 2: Run test to verify it fails**

Run: `cd plugins/note-organizer && pytest tests/test_clean_timestamps.py -v`
Expected: FAIL (module should exist from Task 1, tests should PASS actually)

**Step 3: Verify tests pass**

Run: `cd plugins/note-organizer && pytest tests/test_clean_timestamps.py -v`
Expected: PASS (3 passed)

**Step 4: Commit**

```bash
git add plugins/note-organizer/tests/test_clean_timestamps.py
git commit -m "test(note-organizer): add basic timestamp removal tests

- Test [HH:MM:SS] format removal
- Test [MM:SS] format removal
- Test space handling after timestamp

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add edge case tests

**Files:**
- Modify: `plugins/note-organizer/tests/test_clean_timestamps.py`

**Step 1: Add edge case tests**

Add to test file:

```python
def test_no_false_positive_brackets():
    """测试不误删其他方括号内容"""
    input_text = "[参考] 这是重要内容"
    result = clean_timestamps(input_text)
    assert result == "[参考] 这是重要内容"


def test_consecutive_timestamps():
    """测试连续多个时间戳"""
    input_text = "[00:01][00:02] 内容"
    result = clean_timestamps(input_text)
    assert result == "内容"


def test_timestamp_in_middle():
    """测试时间戳在文本中间"""
    input_text = "前言 [00:05] 正文"
    result = clean_timestamps(input_text)
    assert result == "前言 正文"


def test_no_timestamp():
    """测试没有时间戳的文本"""
    input_text = "普通文本内容"
    result = clean_timestamps(input_text)
    assert result == "普通文本内容"


def test_empty_input():
    """测试空输入"""
    result = clean_timestamps("")
    assert result == ""


def test_multiple_timestamps_in_line():
    """测试一行中多个时间戳"""
    input_text = "[00:01] 第一段 [00:15] 第二段"
    result = clean_timestamps(input_text)
    assert result == "第一段 第二段"
```

**Step 2: Run tests to verify they pass**

Run: `cd plugins/note-organizer && pytest tests/test_clean_timestamps.py -v`
Expected: PASS (all tests pass)

**Step 3: Commit**

```bash
git add plugins/note-organizer/tests/test_clean_timestamps.py
git commit -m "test(note-organizer): add edge case tests for timestamp cleaning

- Test false positive prevention (non-timestamp brackets)
- Test consecutive timestamps
- Test timestamp in middle of text
- Test no timestamp scenario
- Test empty input
- Test multiple timestamps in one line

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Test CLI with stdin input

**Files:**
- Modify: `plugins/note-organizer/tests/test_clean_timestamps.py`

**Step 1: Add stdin CLI test**

Add to test file:

```python
def test_cli_stdin_input():
    """测试 CLI 标准输入"""
    input_text = "[00:01:23] 测试内容\n"
    result = subprocess.run(
        ["python3", "scripts/clean_timestamps.py"],
        input=input_text,
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode == 0
    assert result.stdout == "测试内容\n"


def test_cli_stdin_multiple_lines():
    """测试 CLI 标准输入多行"""
    input_text = "[00:01] 第一行\n[00:02] 第二行\n"
    result = subprocess.run(
        ["python3", "scripts/clean_timestamps.py"],
        input=input_text,
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode == 0
    assert result.stdout == "第一行\n第二行\n"
```

**Step 2: Run tests to verify they pass**

Run: `cd plugins/note-organizer && pytest tests/test_clean_timestamps.py::test_cli_stdin_input -v`
Expected: PASS

**Step 3: Commit**

```bash
git add plugins/note-organizer/tests/test_clean_timestamps.py
git commit -m "test(note-organizer): add CLI stdin input tests

- Test basic stdin input
- Test multi-line stdin input

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Test CLI with file input

**Files:**
- Modify: `plugins/note-organizer/tests/test_clean_timestamps.py`

**Step 1: Add file input CLI tests**

Add to test file:

```python
def test_cli_file_input(tmp_path):
    """测试 CLI 文件输入"""
    # 创建临时测试文件
    test_file = tmp_path / "test_input.txt"
    test_file.write_text("[00:01:23] 文件测试内容")

    result = subprocess.run(
        ["python3", "scripts/clean_timestamps.py", str(test_file)],
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode == 0
    assert result.stdout == "文件测试内容"


def test_cli_file_not_found():
    """测试文件不存在的错误处理"""
    result = subprocess.run(
        ["python3", "scripts/clean_timestamps.py", "nonexistent.txt"],
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode != 0
    assert "No such file" in result.stderr or "cannot open" in result.stderr.lower()


def test_cli_multiple_files(tmp_path):
    """测试 CLI 多文件输入"""
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("[00:01] 文件一")
    file2.write_text("[00:02] 文件二")

    result = subprocess.run(
        ["python3", "scripts/clean_timestamps.py", str(file1), str(file2)],
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode == 0
    assert result.stdout == "文件一文件二"
```

**Step 2: Run tests to verify they pass**

Run: `cd plugins/note-organizer && pytest tests/test_clean_timestamps.py::test_cli_file_input -v`
Expected: PASS (all file input tests)

**Step 3: Commit**

```bash
git add plugins/note-organizer/tests/test_clean_timestamps.py
git commit -m "test(note-organizer): add CLI file input tests

- Test single file input
- Test file not found error handling
- Test multiple files input

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Update scripts/__init__.py version

**Files:**
- Modify: `plugins/note-organizer/scripts/__init__.py`

**Step 1: Check current version and update if needed**

Run: `cat plugins/note-organizer/scripts/__init__.py`

If version exists, ensure it's "1.0.0". If not, add:

```python
"""Note Organizer 脚本模块"""
__version__ = "1.0.0"
```

**Step 2: Run version test to verify**

Run: `cd plugins/note-organizer && pytest tests/test_base_structure.py::test_scripts_module_version -v`
Expected: PASS

**Step 3: Commit if changes made**

```bash
git add plugins/note-organizer/scripts/__init__.py
git commit -m "chore(note-organizer): ensure scripts module version is 1.0.0

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Run all tests and verify feature acceptance steps

**Files:**
- None (verification only)

**Step 1: Run all plugin tests**

Run: `cd plugins/note-organizer && pytest tests/ -v`
Expected: All tests PASS

**Step 2: Verify feature acceptance steps manually**

Run each acceptance step:

```bash
# 1. 验证模块存在
ls plugins/note-organizer/scripts/clean_timestamps.py

# 2. 运行单元测试
cd plugins/note-organizer && pytest tests/test_clean_timestamps.py -v

# 3. 测试 CLI 入口
cd plugins/note-organizer && python3 scripts/clean_timestamps.py --help

# 4. 测试清理功能
echo '[00:01:23] test content' | python3 plugins/note-organizer/scripts/clean_timestamps.py /dev/stdin
```

Expected: All steps pass

**Step 3: No commit (verification only)**

---

## Task 8: Update workflow state and prepare for completion

**Files:**
- None (state update only)

**Step 1: Update workflow state to execution_complete**

Run: `python3 /Users/siunin/.claude/plugins/cache/siunin-plugins/progress-tracker/1.6.5/hooks/scripts/progress_manager.py set-workflow-state --phase execution_complete --next-action "Review implementation and run /prog done"`

**Step 2: View final status**

Run: `/prog` or `python3 /Users/siunin/.claude/plugins/cache/siunin-plugins/progress-tracker/1.6.5/hooks/scripts/progress_manager.py status`

**Step 3: No commit (state update only)**

---

## Completion Checklist

- [ ] All tests pass (`pytest tests/test_clean_timestamps.py -v`)
- [ ] Module exists at correct path (`scripts/clean_timestamps.py`)
- [ ] CLI supports file input
- [ ] CLI supports stdin input
- [ ] Regex doesn't false-positive on `[参考]` style brackets
- [ ] Feature acceptance steps verified manually
- [ ] Workflow state updated to `execution_complete`

## Summary

This plan implements the timestamp cleaning module using TDD:
1. Create module skeleton with regex + fileinput
2. Test basic timestamp removal (both formats)
3. Test edge cases (false positives, consecutive, inline)
4. Test CLI stdin input
5. Test CLI file input (single/multiple/error)
6. Verify version consistency
7. Run full test suite and manual acceptance
8. Update workflow state

Total tasks: 8 | Estimated time: 30-45 minutes
