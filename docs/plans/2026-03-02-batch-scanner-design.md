# Batch Scanner Module Design

**Feature**: #3 - Batch scanner module with CLI
**Date**: 2026-03-02
**Complexity**: Standard (18/40)

## Overview

创建一个 Python 模块 `batch_scanner.py`，用于扫描匹配 glob 模式的文件并返回 JSON 格式的文件列表（包含路径和大小）。

## Requirements

### Functional
- 接受 glob 模式作为输入（支持递归 `**`）
- 返回匹配文件的路径和大小
- 支持 `--json` 输出格式
- 支持多个 glob 模式（位置参数）

### Non-Functional
- 简单可预测的输出
- 性能优化（不读取文件内容）
- 符合 Unix 工具哲学

## Design Decisions

### 1. 核心功能：文件发现

只负责文件发现，不处理文件内容。内容处理由其他模块（如 clean_timestamps.py）完成。

### 2. JSON 输出格式

```json
{
  "files": [
    {"path": "relative/path/to/file.py", "size": 1234},
    {"path": "another/file.md", "size": 5678}
  ]
}
```

使用相对路径（相对于当前工作目录），便于跨环境使用。

### 3. CLI 参数设计

```bash
python3 batch_scanner.py <pattern> [<pattern>...] [--json]
```

- `pattern`: glob 模式（支持 `**/*.py` 递归）
- `--json`: 输出 JSON 格式（默认）
- 无需 `--recursive`（glob 本身支持）

### 4. 错误处理

| 场景 | 行为 |
|------|------|
| 无匹配文件 | 返回 `{"files": []}`，exit code 0 |
| 无效 glob | 打印错误，exit code 1 |
| 文件不可读 | 跳过该文件，记录警告 |

## Module Structure

```python
scripts/batch_scanner.py
├── Shebang: #!/usr/bin/env python3
├── Module docstring
├── scan_files(patterns: List[str]) -> Dict
├── main()
└── __main__ guard
```

## Data Flow

```
CLI 参数 → glob.glob() → 文件扫描 → {path, size} → JSON 输出
```

## Test Coverage

```python
tests/test_batch_scanner.py
├── test_basic_glob_match()       # 基本匹配
├── test_recursive_glob()         # **/*.py 递归
├── test_multiple_patterns()      # 多个模式
├── test_no_matches()             # 无匹配返回空
├── test_json_output()            # JSON 格式验证
├── test_file_size_accuracy()     # 大小准确性
├── test_cli_help()               # --help 或默认行为
└── test_invalid_pattern()        # 错误处理
```

## Edge Cases

| 场景 | 输入 | 输出 |
|------|------|------|
| 无匹配 | `nonexistent/*` | `{"files": []}` |
| 递归匹配 | `**/*.py` | 所有 .py 文件 |
| 多模式 | `*.py *.txt` | 合并结果 |
| 目录 | `tests/` | 跳过（只返回文件） |

## Integration Points

- **上游**: `/note-batch` command 调用
- **下游**: 输出传递给内容处理模块
- **测试**: 与 clean_timestamps 测试风格一致

## Success Criteria

✅ 所有测试通过
✅ CLI 支持 glob 模式和 --json
✅ 相对路径输出
✅ 准确的文件大小
✅ 符合项目编码规范
