# 命令集成文档

## 概述

`organize-note` skill 由命令层调用，不直接处理文件 I/O。

## /note-process 命令集成

### 调用流程

**文件路径模式：**
```
用户输入: /note-process ./notes/meeting.txt
    ↓
命令层: 读取文件内容
    ↓
Skill: organize-note 处理内容（自动使用默认设置）
    ↓
命令层: 写入 ./notes/meeting-notebooklm.md
```

**直接粘贴内容模式：**
```
用户输入: /note-process [粘贴的文章内容]
    ↓
命令层: 直接使用粘贴内容
    ↓
Skill: organize-note 处理内容（自动使用默认设置）
    ↓
命令层: 写入 ./notes/note-2026-03-07-143022-notebooklm.md
```

### 重要规则

**不询问用户任何问题**：
- 自动使用 NotebookLM 格式（除非指定 --obsidian）
- 自动生成元数据（标题、标签、摘要）
- 自动清理时间戳
- 直接输出结果

### 命令结构

```markdown
---
name: note-process
scope: command
description: 格式化笔记（支持文件路径或直接粘贴内容）
---

# note-process 命令

使用 organize-note skill 格式化笔记内容。

## 参数

- 输入：文件路径 或 直接粘贴的文章内容
- `--obsidian`: 使用 Obsidian 格式（可选，默认 NotebookLM）
- `--output <路径>`: 指定输出路径（可选）

## 处理步骤

1. 判断输入类型（文件路径 vs 直接内容）
2. 获取内容（读取文件 或 使用粘贴内容）
3. 确定输出路径
4. 调用 organize-note skill
5. 将 skill 返回的格式化文本写入输出文件
```

## /note-batch 命令集成

### 调用流程

```
用户输入: /note-batch "./notes/*.txt" --format obsidian
    ↓
命令层: 使用 batch_scanner.py 扫描文件
    ↓
循环: 对每个文件调用 organize-note skill
    ↓
命令层: 为每个文件写入对应的输出文件
```

### 命令结构

```markdown
---
name: note-batch
scope: command
description: 批量格式化笔记文件
---

# note-batch 命令

使用 organize-note skill 批量格式化笔记文件。

## 参数

- `pattern`: Glob 文件模式
- `--format`: 目标格式 (notebooklm | obsidian)

## 处理步骤

1. 使用 batch_scanner.py 扫描匹配的文件
2. 对每个文件：
   a. 读取文件内容
   b. 调用 organize-note skill
   c. 写入格式化输出
3. 生成处理报告
```

## 路径约定

### CLAUDE_PLUGIN_ROOT

所有脚本调用使用 `${CLAUDE_PLUGIN_ROOT}` 环境变量：

```bash
cd "${CLAUDE_PLUGIN_ROOT}"
python3 scripts/clean_timestamps.py
```

### 输出文件命名

- NotebookLM: `<original-name>-notebooklm.md`
- Obsidian: `<original-name>-obsidian.md`

## 错误处理

- 文件读取失败：跳过该文件，记录错误
- Skill 处理失败：返回原始内容，记录错误
- 写入冲突：添加时间戳后缀
