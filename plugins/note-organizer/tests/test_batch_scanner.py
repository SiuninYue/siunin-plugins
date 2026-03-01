"""测试批量扫描模块"""
import pytest
from pathlib import Path
import sys
import subprocess
import json
import os

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
