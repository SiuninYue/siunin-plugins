---
version: "1.0.0"
scope: command
inputs:
  - 文件路径
  - 目标格式（可选，默认 notebooklm）
outputs:
  - 格式化后的笔记文件
evidence: optional
references:
  - ../skills/organize-note/SKILL.md
description: 格式化单个笔记文件
argument-hint: 文件路径，如 ./notes/meeting.txt
---

# note-process 命令

格式化单个笔记文件，支持 NotebookLM 和 Obsidian 两种输出格式。

## 参数解析

从 `$ARGUMENTS` 解析：
- 文件路径（必填）
- `--obsidian` 使用 Obsidian 格式（可选，默认 NotebookLM）

## 执行流程

### 第一步：解析参数

```bash
FILE_PATH=<提取的文件路径>
FORMAT=<提取的格式，默认 notebooklm>
```

### 第二步：读取文件内容

使用 Read 工具读取文件内容：
- 如果文件不存在，提示用户并退出

### 第三步：调用 Skill

使用 Skill 工具调用 `organize-note`：
```json
{
  "skill": "organize-note",
  "args": "<文件内容> --format <FORMAT>"
}
```

### 第四步：写入输出文件

输出文件路径规则：
- NotebookLM: `<原文件名>-notebooklm.md`
- Obsidian: `<原文件名>-obsidian.md`

使用 Write 工具写入格式化后的内容。

### 第五步：确认

告知用户输出文件路径。

## 错误处理

- 文件不存在：提示用户检查路径
- Skill 处理失败：返回原始内容，记录错误
- 写入冲突：添加时间戳后缀

## 示例

```bash
# 默认 NotebookLM 格式
/note-process ./notes/meeting.txt
# → 生成 ./notes/meeting-notebooklm.md

# Obsidian 格式
/note-process ./notes/meeting.txt --obsidian
# → 生成 ./notes/meeting-obsidian.md
```
