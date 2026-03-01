#!/usr/bin/env python3
"""时间戳清理模块 - 移除视频转录格式的时间戳"""
import re
import fileinput

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
