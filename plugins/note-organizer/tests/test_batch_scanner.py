"""测试批量扫描模块"""
import pytest
from pathlib import Path
import sys
import subprocess
import json
import os
import tempfile

# Add plugin root to path for imports
plugin_root = Path(__file__).parent.parent.resolve()
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from scripts.batch_scanner import scan_files


def test_basic_glob_match():
    """测试基本 glob 匹配"""
    result = scan_files([str(plugin_root / "tests" / "*.py")])
    assert "files" in result
    assert isinstance(result["files"], list)
    # 应该至少有一个测试文件
    assert len(result["files"]) > 0


def test_files_have_path_and_size():
    """测试文件包含 path 和 size 字段"""
    result = scan_files([str(plugin_root / "tests" / "test_base_structure.py")])
    if result["files"]:
        file_info = result["files"][0]
        assert "path" in file_info
        assert "size" in file_info
        assert isinstance(file_info["size"], int)
        assert file_info["size"] > 0


def test_recursive_glob():
    """测试递归 glob 匹配 (**/*.py)"""
    result = scan_files([str(plugin_root / "tests" / "**" / "*.py")])
    assert isinstance(result["files"], list)
    # 验证返回的是 Python 文件
    for file_info in result["files"]:
        assert file_info["path"].endswith(".py")


def test_multiple_patterns():
    """测试多个 glob 模式"""
    result = scan_files([
        str(plugin_root / "tests" / "test_*.py"),
        str(plugin_root / "scripts" / "*.py")
    ])
    assert isinstance(result["files"], list)
    # 应该匹配两个模式的文件（至少 2 个：一个测试文件和一个脚本文件）
    assert len(result["files"]) >= 2


def test_no_matches():
    """测试无匹配结果"""
    result = scan_files([str(plugin_root / "nonexistent" / "*.xyz")])
    assert result["files"] == []


def test_directories_skipped():
    """测试目录被跳过"""
    result = scan_files([str(plugin_root / "tests" / "*")])
    # 验证只返回文件，不返回目录
    for file_info in result["files"]:
        assert os.path.isfile(file_info["path"])


def test_cli_json_output():
    """测试 CLI JSON 输出"""
    result = subprocess.run(
        ["python3", "scripts/batch_scanner.py", "tests/test_*.py"],
        capture_output=True,
        text=True,
        cwd=str(plugin_root)
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
        cwd=str(plugin_root)
    )
    assert result.returncode != 0
    assert "Usage:" in result.stderr


def test_cli_multiple_patterns():
    """测试 CLI 多模式输入"""
    result = subprocess.run(
        ["python3", "scripts/batch_scanner.py", "tests/test_*.py", "scripts/*.py"],
        capture_output=True,
        text=True,
        cwd=str(plugin_root)
    )
    assert result.returncode == 0

    output = json.loads(result.stdout)
    assert "files" in output


def test_duplicate_removal():
    """测试重复文件去重"""
    # 使用两个会匹配相同文件的模式
    result = scan_files([
        str(plugin_root / "tests" / "test_*.py"),
        str(plugin_root / "tests" / "test_batch*.py")
    ])
    assert isinstance(result["files"], list)

    # 验证没有重复文件
    paths = [f["path"] for f in result["files"]]
    assert len(paths) == len(set(paths)), "Files should not be duplicated"


def test_path_normalization():
    """测试路径归一化：./x 和 x 应该被识别为同一文件"""
    # 创建临时测试目录和文件
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        test_file = tmppath / "test.txt"
        test_file.write_text("test content")

        # 使用不同的路径形式匹配同一文件
        # 相对路径形式
        pattern1 = str(tmppath / ".")
        pattern2 = str(tmppath)

        result = scan_files([f"{pattern1}/*.txt", f"{pattern2}/*.txt"])

        # 应该只有一个文件（去重后）
        assert len(result["files"]) == 1, f"Expected 1 file, got {len(result['files'])}"
        # 路径应该是归一化的绝对路径
        assert result["files"][0]["path"] == str(test_file.resolve())


def test_output_sorted():
    """测试输出按路径排序"""
    result = scan_files([str(plugin_root / "tests" / "*.py")])
    paths = [f["path"] for f in result["files"]]

    # 验证路径是排序的
    assert paths == sorted(paths), "Files should be sorted by path"
