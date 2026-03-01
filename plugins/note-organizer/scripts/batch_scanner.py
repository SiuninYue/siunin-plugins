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
                try:
                    size = os.path.getsize(filepath)
                except (OSError, PermissionError):
                    # 跳过无法访问的文件
                    continue
                files.append({
                    "path": filepath,
                    "size": size
                })
    return {"files": files}


def main():
    """CLI 入口：扫描文件并输出 JSON 格式"""
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
