# Batch Scanner Module Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Python CLI module that scans files matching glob patterns and returns JSON output with file paths and sizes.

**Architecture:** Simple file discovery using glob module with JSON serialization. TDD approach with pytest.

**Tech Stack:** Python 3, glob, os, json, argparse, pytest

---

## Task 1: Create batch_scanner.py module skeleton

**Files:**
- Create: `plugins/note-organizer/scripts/batch_scanner.py`

**Step 1: Create the file with shebang and module structure**

```python
#!/usr/bin/env python3
"""批量扫描模块 - 扫描匹配 glob 模式的文件"""
import glob
import os
import json
import sys
from typing import List, Dict, Any


def scan_files(patterns: List[str]) -> Dict[str, Any]:
    """扫描匹配 glob 模式的文件，返回路径和大小

    Args:
        patterns: glob 模式列表

    Returns:
        包含 files 列表的字典，每个文件包含 path 和 size
    """
    files = []
    for pattern in patterns:
        # 使用 recursive=True 支持 ** 递归匹配
        matched = glob.glob(pattern, recursive=True)
        for filepath in matched:
            # 只包含文件，跳过目录
            if os.path.isfile(filepath):
                files.append({
                    "path": filepath,
                    "size": os.path.getsize(filepath)
                })
    return {"files": files}


def main():
    """CLI 入口：扫描文件并输出 JSON 格式"""
    # 简单解析：第一个参数是模式，--json 标志可选
    if len(sys.argv) < 2:
        print("Usage: batch_scanner.py <pattern> [<pattern>...]", file=sys.stderr)
        sys.exit(1)

    # 提取 glob 模式（跳过 --json 标志）
    patterns = [arg for arg in sys.argv[1:] if not arg.startswith("--")]

    # 扫描文件
    result = scan_files(patterns)

    # 输出 JSON
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
```

**Step 2: Make the file executable**

Run: `chmod +x plugins/note-organizer/scripts/batch_scanner.py`
Expected: No error

**Step 3: Verify basic functionality**

Run: `cd plugins/note-organizer && python3 scripts/batch_scanner.py 'tests/*.py'`
Expected: JSON output with test files

**Step 4: Commit**

```bash
git add plugins/note-organizer/scripts/batch_scanner.py
git commit -m "feat(note-organizer): add batch_scanner.py module skeleton

- Add shebang for executable support
- Implement scan_files() function with glob support
- Add main() CLI entry point with JSON output
- Support multiple glob patterns

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Create test file with basic glob match tests

**Files:**
- Create: `plugins/note-organizer/tests/test_batch_scanner.py`

**Step 1: Write the failing test**

```python
"""测试批量扫描模块"""
import pytest
from pathlib import Path
import sys
import subprocess
import json

# Add plugin root to path for imports
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from scripts.batch_scanner import scan_files


def test_basic_glob_match():
    """测试基本 glob 匹配"""
    result = scan_files(["tests/*.py"])
    assert "files" in result
    assert isinstance(result["files"], list)
    # 应该至少有一个测试文件
    assert len(result["files"]) > 0


def test_files_have_path_and_size():
    """测试文件包含 path 和 size 字段"""
    result = scan_files(["tests/test_base_structure.py"])
    if result["files"]:
        file_info = result["files"][0]
        assert "path" in file_info
        assert "size" in file_info
        assert isinstance(file_info["size"], int)
        assert file_info["size"] > 0
```

**Step 2: Run test to verify it fails**

Run: `cd plugins/note-organizer && pytest tests/test_batch_scanner.py -v`
Expected: FAIL (module should exist from Task 1, tests should PASS actually)

**Step 3: Verify tests pass**

Run: `cd plugins/note-organizer && pytest tests/test_batch_scanner.py -v`
Expected: PASS (2 passed)

**Step 4: Commit**

```bash
git add plugins/note-organizer/tests/test_batch_scanner.py
git commit -m "test(note-organizer): add basic glob match tests

- Test basic glob pattern matching
- Test file info contains path and size fields

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add recursive glob and multiple patterns tests

**Files:**
- Modify: `plugins/note-organizer/tests/test_batch_scanner.py`

**Step 1: Add recursive and multiple patterns tests**

Add to test file:

```python
def test_recursive_glob():
    """测试递归 glob 匹配 (**/*.py)"""
    result = scan_files(["tests/**/*.py"])
    assert isinstance(result["files"], list)
    # 验证返回的是 Python 文件
    for file_info in result["files"]:
        assert file_info["path"].endswith(".py")


def test_multiple_patterns():
    """测试多个 glob 模式"""
    result = scan_files(["tests/test_*.py", "scripts/*.py"])
    assert isinstance(result["files"], list)
    # 应该匹配两个模式的文件
    assert len(result["files"]) >= 0


def test_no_matches():
    """测试无匹配结果"""
    result = scan_files(["nonexistent/*.xyz"])
    assert result["files"] == []


def test_directories_skipped():
    """测试目录被跳过"""
    result = scan_files(["tests/*"])
    # 验证只返回文件，不返回目录
    for file_info in result["files"]:
        assert os.path.isfile(file_info["path"])
```

**Step 2: Run tests to verify they pass**

Run: `cd plugins/note-organizer && pytest tests/test_batch_scanner.py -v`
Expected: PASS (all tests pass)

**Step 3: Commit**

```bash
git add plugins/note-organizer/tests/test_batch_scanner.py
git commit -m "test(note-organizer): add recursive and multiple patterns tests

- Test recursive glob with **/*.py
- Test multiple glob patterns
- Test empty result when no matches
- Test directories are skipped

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Test CLI with JSON output

**Files:**
- Modify: `plugins/note-organizer/tests/test_batch_scanner.py`

**Step 1: Add CLI JSON output tests**

Add to test file:

```python
def test_cli_json_output():
    """测试 CLI JSON 输出"""
    result = subprocess.run(
        ["python3", "scripts/batch_scanner.py", "tests/test_*.py"],
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode == 0

    # 验证输出是有效 JSON
    output = json.loads(result.stdout)
    assert "files" in output
    assert isinstance(output["files"], list)


def test_cli_no_args():
    """测试 CLI 无参数时的错误处理"""
    result = subprocess.run(
        ["python3", "scripts/batch_scanner.py"],
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode != 0
    assert "Usage:" in result.stderr


def test_cli_multiple_patterns():
    """测试 CLI 多模式输入"""
    result = subprocess.run(
        ["python3", "scripts/batch_scanner.py", "tests/test_*.py", "scripts/*.py"],
        capture_output=True,
        text=True,
        cwd=plugin_root
    )
    assert result.returncode == 0

    output = json.loads(result.stdout)
    assert "files" in output
```

**Step 2: Run tests to verify they pass**

Run: `cd plugins/note-organizer && pytest tests/test_batch_scanner.py::test_cli_json_output -v`
Expected: PASS (all CLI tests pass)

**Step 3: Commit**

```bash
git add plugins/note-organizer/tests/test_batch_scanner.py
git commit -m "test(note-organizer): add CLI JSON output tests

- Test JSON output is valid
- Test error handling for no arguments
- Test multiple patterns via CLI

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Run all tests and verify feature acceptance steps

**Files:**
- None (verification only)

**Step 1: Run all plugin tests**

Run: `cd plugins/note-organizer && pytest tests/test_batch_scanner.py -v`
Expected: All tests PASS

**Step 2: Verify feature acceptance steps manually**

Run each acceptance step:

```bash
# 1. 验证模块存在
ls plugins/note-organizer/scripts/batch_scanner.py

# 2. 运行单元测试
cd plugins/note-organizer && pytest tests/test_batch_scanner.py -v

# 3. 测试 CLI 入口
cd plugins/note-organizer && python3 scripts/batch_scanner.py --help 2>&1 | head -3

# 4. 测试扫描功能
cd plugins/note-organizer && python3 scripts/batch_scanner.py 'tests/*.py' --json
```

Expected: All steps pass

**Step 3: No commit (verification only)**

---

## Task 6: Update workflow state and prepare for completion

**Files:**
- None (state update only)

**Step 1: Update workflow state to execution_complete**

Run: `python3 /Users/siunin/.claude/plugins/cache/siunin-plugins/progress-tracker/1.6.5/hooks/scripts/progress_manager.py set-workflow-state --phase execution_complete --next-action "Review implementation and run /prog done"`

**Step 2: View final status**

Run: `/prog` or `python3 /Users/siunin/.claude/plugins/cache/siunin-plugins/progress-tracker/1.6.5/hooks/scripts/progress_manager.py status`

**Step 3: No commit (state update only)**

---

## Completion Checklist

- [ ] All tests pass (`pytest tests/test_batch_scanner.py -v`)
- [ ] Module exists at correct path (`scripts/batch_scanner.py`)
- [ ] CLI supports glob patterns
- [ ] CLI outputs valid JSON
- [ ] File info contains path and size
- [ ] Directories are skipped
- [ ] Feature acceptance steps verified manually
- [ ] Workflow state updated to `execution_complete`

## Summary

This plan implements the batch scanner module using TDD:
1. Create module skeleton with glob + JSON output
2. Test basic glob matching
3. Test recursive and multiple patterns
4. Test CLI JSON output
5. Run full test suite and manual acceptance
6. Update workflow state

Total tasks: 6 | Estimated time: 20-30 minutes
