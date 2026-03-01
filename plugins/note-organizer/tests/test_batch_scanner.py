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
