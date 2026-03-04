---
version: "1.0.0"
scope: command
inputs:
  - Glob 文件模式
  - 目标格式（可选，默认 notebooklm）
outputs:
  - 多个格式化后的笔记文件
  - 处理报告
evidence: optional
references:
  - ../skills/organize-note/SKILL.md
description: 批量格式化笔记文件
argument-hint: 文件模式，如 "./notes/*.txt"
---

# note-batch 命令

使用 Glob 模式批量处理多个笔记文件。

## 参数解析

从 `$ARGUMENTS` 解析：
- Glob 模式（必填，如 `"./notes/*.txt"`）
- `--obsidian` 使用 Obsidian 格式（可选，默认 NotebookLM）

## 执行流程

### 第一步：解析参数

```bash
GLOB_PATTERN=<提取的 glob 模式>
FORMAT=<提取的格式，默认 notebooklm>
```

### 第二步：扫描文件

使用 Glob 工具查找匹配的文件：
```
Glob: pattern=<GLOB_PATTERN>
```

如果没有匹配文件，提示用户并退出。

### 第三步：逐个处理

对每个文件：
1. 使用 Read 工具读取内容
2. 使用 Skill 工具调用 `organize-note`
3. 使用 Write 工具写入输出

### 第四步：生成报告

输出处理摘要：
- 成功处理数量
- 失败数量及原因
- 输出文件列表

## 错误处理

- 某个文件处理失败：跳过，记录错误，继续处理其他文件
- 所有文件失败：提示用户检查文件格式

## 示例

```bash
# 批量处理所有 txt 文件（默认 NotebookLM）
/note-batch "./notes/*.txt"
# → 生成 ./notes/file1-notebooklm.md
#    ./notes/file2-notebooklm.md
#    ...

# 使用 Obsidian 格式
/note-batch "./notes/*.txt" --obsidian
```
