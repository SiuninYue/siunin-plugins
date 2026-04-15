# organize-note Skill 设计文档

**日期**: 2026-03-03
**功能**: Feature 4 - Skill and reference documents
**状态**: 设计已批准

## 概述

创建 `organize-note` skill，作为 Note Organizer 插件的核心处理逻辑层。该 skill 负责协调 Python 脚本（确定性任务）和 AI 生成（创造性任务），实现笔记内容的自动整理。

## 核心契约

```
接收：文件内容（文本字符串）
返回：格式化后的文本（NotebookLM 或 Obsidian 格式）
```

## 处理流程

```
输入文本
   ↓
1. 时间戳清理（Python: clean_timestamps.py）
   - 移除 [HH:MM:SS] 或 [MM:SS] 格式的时间戳
   ↓
2. AI 元数据生成（Claude: sonnet）
   - 标题（简洁描述）
   - 笔记类型（教程/对话/技术文档等）
   - 标签（层级分类，如 tech/ai）
   - 摘要（50-100字）
   - 关键要点（3-5条）
   ↓
3. 模板渲染（Python: template_renderer.py）
   - NotebookLM 格式
   - Obsidian 格式
   ↓
输出格式化文本
```

## 文件结构

```
plugins/note-organizer/skills/organize-note/
├── SKILL.md                    # 主 skill 文件
└── references/
    ├── note-types.md           # 笔记类型分类
    ├── timestamp-formats.md    # 时间戳格式规范
    ├── template-fields.md      # 模板字段说明
    └── command-integration.md  # 命令集成文档
```

## Skill 元数据

```yaml
name: organize-note
description: 整理笔记内容，清理时间戳，生成元数据，渲染模板
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - 文件内容（文本字符串）
  - 目标格式（notebooklm | obsidian）
outputs:
  - 格式化后的笔记文本
```

## 参考文档内容

### note-types.md
- 笔记类型分类体系
- 每种类型的特征描述
- 分类判断逻辑

### timestamp-formats.md
- 支持的时间戳格式（[HH:MM:SS]、[MM:SS]）
- 清理规则和边界情况
- 示例输入输出

### template-fields.md
- NotebookLM 模板变量定义
- Obsidian 模板变量定义
- 字段格式要求

### command-integration.md
- 如何被 /note-process 调用
- 如何被 /note-batch 调用
- CLAUDE_PLUGIN_ROOT 路径约定

## 验收标准

1. 验证主 skill: `ls plugins/note-organizer/skills/organize-note/SKILL.md`
2. 验证参考文档: `ls plugins/note-organizer/skills/organize-note/references/*.md`
3. 检查输入契约: `grep '接收：文件内容' plugins/note-organizer/skills/organize-note/SKILL.md`
4. 检查输出契约: `grep '返回：格式化后的文本' plugins/note-organizer/skills/organize-note/SKILL.md`

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 输入形式 | 文本内容 | 职责分离，skill 专注处理逻辑 |
| 模型选择 | sonnet | 平衡性能和质量，适合元数据生成 |
| 文件写入 | 命令层负责 | skill 返回格式化文本，I/O 由命令层处理 |
