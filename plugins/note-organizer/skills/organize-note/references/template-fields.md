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
