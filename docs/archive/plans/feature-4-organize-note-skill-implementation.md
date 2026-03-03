# organize-note Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create organize-note skill that coordinates Python scripts and AI generation to process and format note content.

**Architecture:** Hybrid architecture with Python handling deterministic tasks (timestamp cleaning, template rendering) and AI (sonnet) handling creative tasks (metadata generation). Skill receives text content and returns formatted text.

**Tech Stack:** Python 3.x, Claude Sonnet model, YAML frontmatter, Markdown

---

## Task 1: Create skill directory structure

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/SKILL.md`
- Create: `plugins/note-organizer/skills/organize-note/references/.gitkeep`

**Step 1: Create directory structure**

```bash
mkdir -p plugins/note-organizer/skills/organize-note/references
touch plugins/note-organizer/skills/organize-note/references/.gitkeep
```

**Step 2: Verify directories created**

Run: `ls -la plugins/note-organizer/skills/organize-note/`
Expected: Show `references/` directory

**Step 3: Commit**

```bash
git add plugins/note-organizer/skills/organize-note/
git commit -m "feat(organize-note): create skill directory structure"
```

---

## Task 2: Write SKILL.md with YAML frontmatter

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/SKILL.md`

**Step 1: Write SKILL.md with complete frontmatter and content**

```markdown
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
```

**Step 2: Verify file created**

Run: `cat plugins/note-organizer/skills/organize-note/SKILL.md | head -20`
Expected: Show YAML frontmatter and skill description

**Step 3: Commit**

```bash
git add plugins/note-organizer/skills/organize-note/SKILL.md
git commit -m "feat(organize-note): add SKILL.md with frontmatter and contract"
```

---

## Task 3: Write note-types.md reference

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/references/note-types.md`

**Step 1: Write note type classification document**

```markdown
# 笔记类型分类

## 分类体系

### tutorial（教程）

**特征：**
- 包含步骤或教程性质的内容
- 有"如何"、"步骤"、"操作"等关键词
- 结构化的指导性内容

**示例：**
- "如何使用 Claude Code"
- "Python 异步编程教程"

### conversation（对话记录）

**特征：**
- 包含对话轮次或问答形式
- 有"问"、"答"、"说"等对话标识
- 多人交流的记录

**示例：**
- 会议记录
- 面试记录
- 问答对话

### technical（技术文档）

**特征：**
- 包含技术概念、API 说明
- 有代码示例或技术术语
- 结构化的技术内容

**示例：**
- API 文档
- 架构设计文档
- 代码分析

### meeting（会议记录）

**特征：**
- 包含会议议程、决策、行动项
- 有时间戳或议程结构
- 多人讨论的总结

**示例：**
- 每周站会记录
- 项目评审会议

### other（其他）

**特征：**
- 不符合上述任何类型
- 通用笔记内容

## 分类判断逻辑

AI 分析内容时，按以下优先级判断：

1. 检查是否有对话格式 → conversation
2. 检查是否有教程/步骤关键词 → tutorial
3. 检查是否有技术术语/代码 → technical
4. 检查是否有会议特征 → meeting
5. 默认 → other
```

**Step 2: Verify file created**

Run: `grep "tutorial" plugins/note-organizer/skills/organize-note/references/note-types.md`
Expected: Show tutorial type definition

**Step 3: Commit**

```bash
git add plugins/note-organizer/skills/organize-note/references/note-types.md
git commit -m "docs(organize-note): add note type classification reference"
```

---

## Task 4: Write timestamp-formats.md reference

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/references/timestamp-formats.md`

**Step 1: Write timestamp format specification**

```markdown
# 时间戳格式规范

## 支持的格式

### 格式 1: [HH:MM:SS]

完整时间戳格式，包含小时、分钟、秒。

**正则：** `\[\\d{1,2}:\\d{2}:\\d{2}\]\s*`

**示例：**
```
[00:01:23] 这是第一句话
[01:05:47] 这是第二句话
```

**清理后：**
```
这是第一句话
这是第二句话
```

### 格式 2: [MM:SS]

简短时间戳格式，仅包含分钟和秒。

**正则：** `\[\\d{1,2}:\\d{2}\]\s*`

**示例：**
```
[01:23] 这是第一句话
[05:47] 这是第二句话
```

**清理后：**
```
这是第一句话
这是第二句话
```

## 清理规则

1. **完全匹配** - 只移除标准格式的时间戳
2. **保留空格** - 时间戳后的空格一并移除，保持文本整洁
3. **行首/行中** - 支持出现在行首或文本中间

## 边界情况

### 不处理的情况

- 圆括号格式：`(00:01:23)` - 不处理
- 其他时间格式：`00:01:23` (无方括号) - 不处理
- 非标准分隔符：`[00-01-23]` - 不处理

### 连续时间戳

```
[00:01:23][00:01:24] 内容
```

清理后：
```
内容
```

## 实现参考

清理逻辑在 `scripts/clean_timestamps.py` 中实现：
```python
TIMESTAMP_PATTERN = re.compile(r'\[\d{1,2}:\d{2}(?::\d{2})?\]\s*')
```
```

**Step 2: Verify file created**

Run: `grep "TIMESTAMP_PATTERN" plugins/note-organizer/skills/organize-note/references/timestamp-formats.md`
Expected: Show regex pattern reference

**Step 3: Commit**

```bash
git add plugins/note-organizer/skills/organize-note/references/timestamp-formats.md
git commit -m "docs(organize-note): add timestamp format specification"
```

---

## Task 5: Write template-fields.md reference

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/references/template-fields.md`

**Step 1: Write template field documentation**

```markdown
# 模板字段说明

## NotebookLM 模板字段

### 必填字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `{title}` | string | 笔记标题 | "Claude Code 使用指南" |
| `{note_type}` | string | 笔记类型 | tutorial, conversation, technical, meeting, other |
| `{tags}` | string | 标签列表（逗号分隔） | "tech/ai, tutorial, getting-started" |
| `{summary}` | string | 内容摘要（50-100字） | "本指南介绍 Claude Code 的基本使用方法..." |
| `{key_points}` | string | 关键要点（每行一条） | "- 第一点\n- 第二点\n- 第三点" |
| `{content}` | string | 处理后的正文内容 | 清理时间戳后的原始内容 |

### 输出格式

```
# {title}

类型: {note_type}
标签: {tags}

## 摘要

{summary}

## 关键要点

{key_points}

## 内容

{content}
```

## Obsidian 模板字段

### 必填字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `{title}` | string | 笔记标题 | "Claude Code 使用指南" |
| `{note_type}` | string | 笔记类型 | tutorial, conversation, technical, meeting, other |
| `{tags}` | string | YAML 标签数组 | "[tech/ai, tutorial, getting-started]" |
| `{summary}` | string | 内容摘要 | "本指南介绍..." |
| `{key_points}` | string | 关键要点 | "- 第一点\n- 第二点" |
| `{content}` | string | 处理后的正文内容 | 清理后的内容 |

### 元数据格式

```yaml
---
cssclass: note-{note_type}
tags: {tags}
created: {created_date}
---

# {title}

## 摘要

{summary}

## 关键要点

{key_points}

## 内容

{content}
```

## 字段格式要求

### 标签格式

- **层级标签**：使用 `/` 分隔，如 `tech/ai`
- **多个标签**：NotebookLM 用逗号分隔，Obsidian 用 YAML 数组

### 关键要点

- **格式**：每行一个要点，使用 `-` 开头
- **数量**：建议 3-5 个要点
- **内容**：简洁的总结性语句

### 摘要

- **长度**：50-100 字
- **内容**：概括笔记的核心内容和价值

## 实现参考

模板渲染逻辑在 `scripts/template_renderer.py` 中实现（Feature 5）。
```

**Step 2: Verify file created**

Run: `grep "note_type" plugins/note-organizer/skills/organize-note/references/template-fields.md`
Expected: Show field type definitions

**Step 3: Commit**

```bash
git add plugins/note-organizer/skills/organize-note/references/template-fields.md
git commit -m "docs(organize-note): add template field documentation"
```

---

## Task 6: Write command-integration.md reference

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/references/command-integration.md`

**Step 1: Write command integration documentation**

```markdown
# 命令集成文档

## 概述

`organize-note` skill 由命令层调用，不直接处理文件 I/O。

## /note-process 命令集成

### 调用流程

```
用户输入: /note-process ./notes/meeting.txt --format notebooklm
    ↓
命令层: 读取文件内容
    ↓
Skill: organize-note 处理内容
    ↓
命令层: 写入 ./notes/meeting-notebooklm.md
```

### 命令结构

```markdown
---
name: note-process
scope: command
description: 格式化单个笔记文件
---

# note-process 命令

使用 organize-note skill 格式化单个笔记文件。

## 参数

- `file`: 笔记文件路径
- `--format`: 目标格式 (notebooklm | obsidian)

## 处理步骤

1. 读取文件内容
2. 调用 organize-note skill
3. 将 skill 返回的格式化文本写入输出文件
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
```

**Step 2: Verify file created**

Run: `grep "CLAUDE_PLUGIN_ROOT" plugins/note-organizer/skills/organize-note/references/command-integration.md`
Expected: Show path convention documentation

**Step 3: Commit**

```bash
git add plugins/note-organizer/skills/organize-note/references/command-integration.md
git commit -m "docs(organize-note): add command integration reference"
```

---

## Task 7: Verify acceptance criteria

**Files:**
- Verify: All created files

**Step 1: Run acceptance test commands**

```bash
# Test 1: 验证主 skill
ls plugins/note-organizer/skills/organize-note/SKILL.md

# Test 2: 验证参考文档
ls plugins/note-organizer/skills/organize-note/references/*.md

# Test 3: 检查输入契约
grep "接收：文件内容" plugins/note-organizer/skills/organize-note/SKILL.md

# Test 4: 检查输出契约
grep "返回：格式化后的文本" plugins/note-organizer/skills/organize-note/SKILL.md
```

Expected: All commands return successful output

**Step 2: Verify YAML frontmatter**

```bash
grep -A 15 "^---" plugins/note-organizer/skills/organize-note/SKILL.md | head -20
```

Expected: Show valid YAML frontmatter with name, description, model, version

**Step 3: Final commit**

```bash
git add docs/plans/2026-03-03-organize-note-skill-implementation.md
git commit -m "docs: add organize-note skill implementation plan"
```

---

## Summary

This plan creates the `organize-note` skill with:

1. **SKILL.md** - Main skill file with YAML frontmatter and processing contract
2. **note-types.md** - Note type classification system (tutorial, conversation, technical, meeting, other)
3. **timestamp-formats.md** - Timestamp format specification ([HH:MM:SS], [MM:SS])
4. **template-fields.md** - Template field definitions for NotebookLM and Obsidian formats
5. **command-integration.md** - Documentation on how commands integrate with the skill

All files follow the established skill pattern from progress-tracker and package-manager plugins.
