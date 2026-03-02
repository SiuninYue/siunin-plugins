---
name: organize-note
description: 整理笔记内容，清理时间戳，生成元数据，渲染模板。接收文件内容，返回格式化后的文本（NotebookLM 或 Obsidian 格式）。
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - 文件内容（文本字符串）
  - 目标格式（notebooklm | obsidian）
outputs:
  - 格式化后的笔记文本
evidence: optional
references:
  - "./references/note-types.md"
  - "./references/timestamp-formats.md"
  - "./references/template-fields.md"
  - "./references/command-integration.md"
---

# organize-note Skill

整理笔记内容的核心处理逻辑。

## 接收：文件内容

输入为文本字符串，包含原始笔记内容。通常来自视频转录文件或会议记录。

## 返回：格式化后的文本

输出为处理后的笔记文本，格式为 NotebookLM 或 Obsidian 模板渲染后的内容。

## 处理流程

1. **时间戳清理** - 调用 `clean_timestamps.py` 移除视频转录格式的时间戳
2. **AI 元数据生成** - 分析内容并生成标题、标签、摘要、关键要点
3. **模板渲染** - 调用 `template_renderer.py` 渲染目标格式模板

## 使用示例

```bash
# 单文件处理
/note-process ./notes/meeting.txt --format notebooklm

# 批量处理
/note-batch "./notes/*.txt" --format obsidian
```

## 参考文档

详见 `references/` 目录：
- `note-types.md` - 笔记类型分类体系
- `timestamp-formats.md` - 时间戳格式规范
- `template-fields.md` - 模板字段说明
- `command-integration.md` - 命令集成文档
