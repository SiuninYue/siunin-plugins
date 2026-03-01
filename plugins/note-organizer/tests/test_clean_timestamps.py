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
