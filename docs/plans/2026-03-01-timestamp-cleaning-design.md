# Timestamp Cleaning Module Design

**Feature**: #2 - Timestamp cleaning module with CLI
**Date**: 2026-03-01
**Complexity**: Standard (21/40)

## Overview

创建一个 Python 模块 `clean_timestamps.py`，用于移除视频转录笔记中的时间戳标记。

## Requirements

### Functional
- 识别并移除 `[HH:MM:SS]` 和 `[MM:SS]` 格式的时间戳
- 支持文件路径和标准输入两种方式
- 不误删其他方括号内容（如 `[参考]`）

### Non-Functional
- 简单可预测的输出
- 符合 Unix 工具哲学
- 易于测试和维护

## Design Decisions

### 1. 正则表达式策略

使用简单的数字格式匹配，而非严格时间验证：

```python
TIMESTAMP_PATTERN = re.compile(r'\[\d{1,2}:\d{2}(?::\d{2})?\]\s*')
```

**理由**：
- 兼容性更好（接受 `[75:30]` 这种超时表示）
- 足够精确（不会误删 `[参考]` 等内容）
- 更简单易维护

### 2. CLI 实现方式

使用 `fileinput` 模块实现统一接口：

```python
import fileinput

def main():
    for line in fileinput.input():
        print(clean_timestamps(line), end='')
```

**优势**：
- 自动支持文件路径 + stdin + 多文件
- 符合 Unix 工具惯例
- 代码简洁

### 3. 错误处理

- 文件不存在：`fileinput` 自动报错并退出（exit code 1）
- 空输入：正常处理，返回空字符串
- 无时间戳：原文返回（静默）

## Module Structure

```
scripts/clean_timestamps.py
├── Shebang: #!/usr/bin/env python3
├── Module docstring
├── TIMESTAMP_PATTERN (compiled regex)
├── clean_timestamps(text: str) -> str
├── main()
└── __main__ guard
```

## Data Flow

```
Input (file/stdin/multi-files)
    ↓
fileinput.input() → line by line
    ↓
clean_timestamps(line) → cleaned line
    ↓
print to stdout
```

## Test Coverage

```python
tests/test_clean_timestamps.py
├── test_basic_removal()          # [00:01:23] text → text
├── test_mm_ss_format()           # [01:23] text → text
├── test_hh_mm_ss_format()        # [00:01:23] text → text
├── test_no_false_positive()      # [参考] text → [参考] text
├── test_consecutive_timestamps() # [00:01][00:02] text → text
├── test_timestamp_in_middle()    # prefix [00:05] suffix → prefix suffix
├── test_stdin_input()            # echo [...] | python3 script.py
├── test_file_input()             # python3 script.py file.txt
├── test_multiple_files()         # python3 script.py f1.txt f2.txt
└── test_file_not_found()         # 错误处理验证
```

## Edge Cases Handled

| 场景 | 输入 | 输出 |
|------|------|------|
| 连续时间戳 | `[00:01][00:02] 内容` | `内容` |
| 行中时间戳 | `前言 [00:05] 正文` | `前言 正文` |
| 无时间戳 | `普通文本` | `普通文本` |
| 空输入 | `` | `` |
| 混合格式 | `[00:01:23] 和 [01:45]` | `和` |

## Integration Points

- **上游**：`/note-process` command 调用
- **下游**：输出传递给 AI 分析和模板渲染
- **测试**：与 `test_base_structure.py` 风格一致

## Success Criteria

✅ 所有测试通过
✅ CLI 支持 `--help`、文件路径、stdin
✅ 不误删非时间戳的方括号内容
✅ 符合项目编码规范
