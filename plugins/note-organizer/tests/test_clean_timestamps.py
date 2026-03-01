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
