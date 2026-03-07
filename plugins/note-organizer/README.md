# Note Organizer Plugin

智能笔记整理插件 - 将 AI 提取的笔记转换为结构化知识库内容。

## 功能

- 时间戳清理（智能清理各种格式）
- AI 自动分类（生成层级标签）
- 内容重组（碎片化 → 结构化）
- 双平台支持（NotebookLM + Obsidian）
- **直接粘贴内容支持** - 无需先保存文件

## 命令

### `/note-process` - 处理笔记

**文件路径模式：**
```bash
/note-process ./notes/meeting.txt
# 生成 ./notes/meeting-notebooklm.md
```

**直接粘贴内容模式：**
```bash
/note-process 这里粘贴你的文章内容...
# 自动生成带时间戳的文件
```

**指定格式：**
```bash
/note-process ./notes/meeting.txt --obsidian
/note-process 粘贴的内容 --obsidian
```

**指定输出路径：**
```bash
/note-process 粘贴的内容 --output ./my-note.md
```

### `/note-batch` - 批量处理

```bash
/note-batch "./notes/*.txt"
```

## 特性

- **自动处理** - 不询问任何问题，直接使用默认设置
- **智能识别** - 自动判断输入是文件路径还是直接内容
- **自动保存** - 处理完成后自动保存到文件

## 架构

- 命令层: Claude Code Commands
- 技能层: Skill Prompts
- 脚本层: Python 处理逻辑

## 安装

```bash
/plugin install note-organizer@siunin-plugins
```
