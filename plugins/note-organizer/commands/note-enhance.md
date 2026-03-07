---
version: "1.0.0"
scope: command
inputs:
  - 文件路径 或 直接粘贴内容
  - 增强模式（可选，默认 all）
  - 目标格式（可选，默认 notebooklm）
outputs:
  - 增强后的笔记文件
evidence: optional
references:
  - ../skills/enhance-note/SKILL.md
description: 增强不完整内容并输出结构化笔记（填充/优化/改写/扩展）
argument-hint: 文件路径或内容 [--mode ...] [--obsidian] [--output 路径] [--out-dir 目录]
---

# note-enhance 命令

增强已有笔记内容，重点处理信息缺口、表达优化和结构扩展。

## 参数解析

从 `$ARGUMENTS` 解析：
- 输入内容（文件路径或直接文本）
- `--mode <fill|optimize|rewrite|expand|all>` 增强模式（可选，默认 `all`）
- `--obsidian` 使用 Obsidian 格式（可选，默认 NotebookLM）
- `--output <路径>` 指定输出文件路径（可选）
- `--out-dir <目录>` 指定输出目录（可选，默认 `./enhanced-notes`）

## 执行流程

### 第一步：判断输入类型

检测输入是文件路径还是直接内容：
- 如果 `$ARGUMENTS` 以 `/` 或 `./` 或 `../` 开头 → 文件路径
- 否则 → 直接内容

### 第二步：获取内容

**文件路径模式：**
```bash
使用 Read 工具读取文件内容
如果文件不存在，提示用户并退出
```

**直接内容模式：**
```bash
将 $ARGUMENTS 作为原始内容使用
```

### 第三步：确定输出路径

路径优先级：
1. 如果指定了 `--output`，直接使用指定路径
2. 否则根据 `--out-dir`（默认 `./enhanced-notes`）生成文件名

默认命名：
- 文件路径模式：`<原文件名>-enhanced-notebooklm.md` 或 `<原文件名>-enhanced-obsidian.md`
- 直接内容模式：`note-enhanced-<YYYY-MM-DD-HHMMSS>-notebooklm.md` 或 `note-enhanced-<YYYY-MM-DD-HHMMSS>-obsidian.md`

### 第四步：调用 Skill 处理

使用 Skill 工具调用 `note-organizer:enhance-note`，传入：
- 原始内容
- mode
- format

### 第五步：写入并确认

使用 Write 工具写入输出文件，并返回：
- 输出文件路径
- 使用的增强模式
- 目标格式

## 错误处理

- 文件路径不存在：提示用户检查路径
- mode 非法：回退到 `all` 并提示已回退
- Skill 处理失败：返回原始内容并记录错误
- 写入冲突：添加时间戳后缀

## 示例

```bash
# 文件路径模式（默认 all + notebooklm）
/note-enhance ./notes/meeting.txt
# → 生成 ./enhanced-notes/meeting-enhanced-notebooklm.md

# 直接粘贴内容
/note-enhance 这是一段待增强的笔记草稿...
# → 生成 ./enhanced-notes/note-enhanced-2026-03-07-143022-notebooklm.md

# 指定 mode
/note-enhance ./notes/meeting.txt --mode rewrite

# 指定 Obsidian
/note-enhance ./notes/meeting.txt --obsidian

# 指定输出目录
/note-enhance ./notes/meeting.txt --out-dir ./notes/enhanced

# 指定输出文件（最高优先级）
/note-enhance ./notes/meeting.txt --output ./custom/meeting-v2.md
```
