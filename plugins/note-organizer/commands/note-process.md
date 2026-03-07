---
version: "1.1.0"
scope: command
inputs:
  - 文件路径 或 直接粘贴的文章内容
  - 目标格式（可选，默认 notebooklm）
outputs:
  - 格式化后的笔记文件
evidence: optional
references:
  - ../skills/organize-note/SKILL.md
description: 格式化笔记（支持文件路径或直接粘贴内容）
argument-hint: 文件路径 或 直接粘贴文章内容
---

# note-process 命令

格式化笔记内容，支持两种输入方式：
1. **文件路径** - 读取指定文件
2. **直接粘贴内容** - 处理粘贴的文章内容

自动处理并保存，无需额外确认。

## 参数解析

从 `$ARGUMENTS` 解析：
- 输入内容（文件路径或直接文本）
- `--obsidian` 使用 Obsidian 格式（可选，默认 NotebookLM）
- `--output <路径>` 指定输出路径（可选）

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

- 如果指定了 `--output`，使用指定路径
- 文件路径模式：`<原文件名>-notebooklm.md` 或 `<原文件名>-obsidian.md`
- 直接内容模式：使用当前时间戳生成文件名，如 `note-2026-03-07-143022-notebooklm.md`

### 第四步：调用 Skill 处理

使用 Skill 工具调用 `note-organizer:organize-note`，传入内容和格式。

**重要：不询问用户任何问题，直接使用默认设置处理**

### 第五步：写入并确认

使用 Write 工具写入，告知用户输出文件路径。

## 错误处理

- 文件路径不存在：提示用户检查路径
- Skill 处理失败：返回原始内容，记录错误
- 写入冲突：添加时间戳后缀

## 示例

```bash
# 文件路径模式
/note-process ./notes/meeting.txt
# → 生成 ./notes/meeting-notebooklm.md

# 直接粘贴内容（自动生成文件名）
/note-process 这是一段需要整理的笔记内容...
# → 生成 ./notes/note-2026-03-07-143022-notebooklm.md

# 指定输出格式
/note-process 粘贴的内容 --obsidian
# → 生成 ./notes/note-2026-03-07-143022-obsidian.md

# 指定输出路径
/note-process 粘贴的内容 --output ./my-note.md
# → 生成 ./my-note.md
```
