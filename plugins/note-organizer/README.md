# Note Organizer Plugin

智能笔记整理插件 - 将 AI 提取的笔记转换为结构化知识库内容。

## 功能

- 时间戳清理（智能清理各种格式）
- AI 自动分类（生成层级标签）
- 内容重组（碎片化 → 结构化）
- 双平台支持（NotebookLM + Obsidian）

## 命令

- `/note-process <file>` - 处理单个笔记
- `/note-batch <pattern> <output>` - 批量处理笔记

## 架构

- 命令层: Claude Code Commands
- 技能层: Skill Prompts
- 脚本层: Python 处理逻辑

## 安装

```bash
/plugin install note-organizer@siunin-plugins
```
