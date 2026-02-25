# Note Organizer Plugin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建一个智能笔记整理插件，将 AI 提取的笔记（带时间戳）转换为结构化知识库内容，优先适配 Google NotebookLM，同时兼容 Obsidian。

**Architecture:**
- 独立插件 `note-organizer`，包含技能和命令
- 时间戳清理模块（整合 youtube-transcript 优势）
- NotebookLM 格式化模块（整合 notebooklm-skill 优势）
- 调用 obsidian-skills 处理 Obsidian 格式
- 支持 /note-process 和 /note-batch 两个命令

**Tech Stack:**
- Claude Code Plugin System
- Markdown (输出格式)
- YAML (frontmatter)
- 依赖: obsidian-skills/obsidian-markdown

---

## Task 1: 创建插件基础结构

**Files:**
- Create: `plugins/note-organizer/.claude-plugin/plugin.json`
- Create: `plugins/note-organizer/README.md`
- Create: `plugins/note-organizer/LICENSE`

**Step 1: 创建 plugin.json**

```json
{
  "name": "note-organizer",
  "version": "1.0.0",
  "description": "智能笔记整理插件 - 将 AI 提取的笔记转换为结构化知识库内容",
  "author": {
    "name": "siunin"
  },
  "license": "MIT",
  "keywords": [
    "note-taking",
    "notebooklm",
    "obsidian",
    "transcript",
    "video-notes",
    "knowledge-management"
  ],
  "dependencies": {
    "skills": [
      "obsidian-skills/obsidian-markdown"
    ]
  }
}
```

**Step 2: 创建 README.md**

```markdown
# Note Organizer Plugin

智能笔记整理插件 - 将 AI 提取的笔记转换为结构化知识库内容。

## 功能

- 去除时间戳（智能清理各种格式）
- 内容重组（碎片化 → 结构化）
- 自动分类（AI 生成层级标签）
- 双平台支持（NotebookLM 优化 + Obsidian 兼容）

## 命令

- `/note-process <file>` - 交互式处理单个笔记
- `/note-batch <pattern>` - 批量处理多个笔记

## 依赖

- obsidian-skills/obsidian-markdown

## 安装

```bash
/plugin install note-organizer@siunin-plugins
```
```

**Step 3: 创建 LICENSE**

使用 MIT 许可证文本。

**Step 4: 提交**

```bash
git add plugins/note-organizer/
git commit -m "feat(note-organizer): create plugin base structure"
```

---

## Task 2: 创建时间戳清理参考文档

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/SKILL.md`
- Create: `plugins/note-organizer/skills/organize-note/references/transcript-cleaning.md`

**Step 1: 创建主技能文件 SKILL.md**

```markdown
---
name: organize-note
version: 1.0.0
description: 智能整理 AI 提取的笔记，去除时间戳、重组结构、自动分类
tags: [note-taking, transcript, organization]
dependencies:
  - obsidian-skills/obsidian-markdown
---

# Note Organizer Skill

## 触发条件

当用户需要处理以下内容时激活：
- AI 提取的视频/音频转录笔记
- 带时间戳的会议记录
- 需要整理的碎片化笔记

## 处理步骤

### 1. 分析输入
- 检测笔记类型（视频/会议/其他）
- 识别时间戳格式
- 评估内容结构

### 2. 清理时间戳
根据 `references/transcript-cleaning.md` 中的规则

### 3. 内容重组
根据 `references/content-structuring.md` 中的模式

### 4. 自动分类
根据 `references/auto-categorization.md` 中的规则

### 5. 格式化输出
- NotebookLM: 应用 `templates/notebooklm-optimized.md`
- Obsidian: 调用 `obsidian-markdown` skill

## 输出格式

确保输出符合目标平台的最佳实践。
```

**Step 2: 创建时间戳清理参考文档**

```markdown
# 时间戳清理指南

## 支持的时间戳格式

### 1. 简单格式
```
00:01:23
01:23
```

### 2. 方括号格式
```
[00:01:23]
[01:23]
```

### 3. 圆括号格式
```
(00:01:23)
(01:23)
```

### 4. 中文格式
```
第1分23秒
第01分23秒
```

### 5. 描述性格式
```
Timestamp: 00:01:23
时间: 01:23
```

## 清理策略

### 保留语义
- 保留对话上下文
- 保留说话人标记
- 保留段落结构

### 处理多说话人
```
说话人A [00:01:23]: 这是内容...
说话人B [00:01:45]: 这是回应...

处理后:
说话人A: 这是内容...
说话人B: 这是回应...
```

## 正则模式

```python
import re

patterns = [
    r"\d{1,2}:\d{2}:\d{2}",           # 00:01:23
    r"\[\d{1,2}:\d{2}:\d{2}\]",       # [00:01:23]
    r"\(\d{1,2}:\d{2}:\d{2}\)",       # (00:01:23)
    r"\d{2}:\d{2}",                   # 01:23
    r"\[\d{2}:\d{2}\]",               # [01:23]
    r"\(\d{2}:\d{2}\)",               # (01:23)
    r"第\d+分\d+秒",                  # 中文格式
    r"Timestamp: .*?$",               # Timestamp: 格式
]

def clean_timestamps(text):
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    # 清理多余空行
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
    return text.strip()
```

## 最佳实践

1. 处理前备份原文
2. 先在小样本上测试
3. 检查清理后内容的完整性
4. 保留原始引用信息
```

**Step 3: 提交**

```bash
git add plugins/note-organizer/skills/
git commit -m "feat(note-organizer): add transcript cleaning reference"
```

---

## Task 3: 创建 NotebookLM 格式规范

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/references/notebooklm-format.md`

**Step 1: 创建 NotebookLM 格式文档**

```markdown
# NotebookLM 格式规范

## 元数据结构 (Frontmatter)

```yaml
---
version: 1.0.0
source_type: video_transcript
original_url: https://youtube.com/watch?v=xxx
processing_date: 2026-02-25T10:30:00+08:00
tags:
  - #technology/ai
  - #tutorial/beginner
category: 技术教程
confidence: high
---
```

## 内容结构

### 1. 标题
使用 H1 标题，清晰描述主题：
```markdown
# 视频标题：AI 学习指南
```

### 2. 内容概览 (📋)
简短摘要，介绍主要内容：
```markdown
## 📋 内容概览

本视频介绍了人工智能的基础知识和学习路径...
```

### 3. 核心要点 (🔑)
列出主要观点，使用嵌套列表：
```markdown
## 🔑 核心要点

### 1. 机器学习基础
- 监督学习 vs 无监督学习
- 常用算法介绍

### 2. 深度学习入门
- 神经网络原理
- 实战案例
```

### 4. Callouts
使用 Obsidian 风格的 callout：
```markdown
> [!TIP] 学习建议
> 建议先掌握 Python 基础，再学习机器学习算法。

> [!IMPORTANT] 关键概念
> 这是需要特别注意的内容。

> [!QUOTE] 原话引用
> 这是原文中的重要引用。
```

### 5. 详细内容 (📚)
结构化展开详细内容：
```markdown
## 📚 详细内容

### 第一章：机器学习概述

机器学习是人工智能的一个分支...

#### 关键概念
- **训练集**: 用于训练模型的数据
- **测试集**: 用于评估模型的数据
```

### 6. 相关资源 (🔗)
使用 Wikilinks 和 Markdown 链接：
```markdown
## 🔗 相关资源

- [[机器学习基础]]
- [[神经网络入门]]
- [推荐课程](https://example.com)
- [相关论文](https://arxiv.org)
```

### 7. 总结 (📝)
总结关键收获：
```markdown
## 📝 总结

本视频涵盖了 AI 学习的三个核心方向：
1. 机器学习基础算法
2. 深度学习框架实践
3. 项目实战经验分享
```

## NotebookLM 优化技巧

1. **清晰的结构**: 使用一致的标题层级
2. **丰富的元数据**: 帮助 AI 理解上下文
3. **视觉分层**: 使用 Emoji 图标区分章节
4. **内部链接**: 使用 Wikilinks 构建知识图谱
5. **简洁的语言**: 避免冗余，突出重点
```

**Step 2: 提交**

```bash
git add plugins/note-organizer/skills/organize-note/references/
git commit -m "feat(note-organizer): add NotebookLM format specification"
```

---

## Task 4: 创建内容重组和自动分类参考

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/references/content-structuring.md`
- Create: `plugins/note-organizer/skills/organize-note/references/auto-categorization.md`

**Step 1: 创建内容重组指南**

```markdown
# 内容重组指南

## 分段策略

### 长内容处理 (>30分钟)
- 按主题分段
- 每段不超过 1000 字
- 保留章节过渡

### 短内容处理 (<10分钟)
- 单一结构
- 重点突出
- 简洁明了

## 层级结构

```markdown
# H1: 主标题
## H2: 主要章节 (📋🔑📚🔗📝)
### H3: 子章节
#### H4: 细节内容
```

## 语义保留

1. **保留关键术语**: 不改写专业术语
2. **保留引用**: 标注来源
3. **保留上下文**: 维持逻辑关系

## 摘要层级

### 执行摘要
- 2-3 句话概括全文
- 放在内容概览中

### 章节摘要
- 每章节 1-2 句话
- 突出关键点

### 详细内容
- 展开具体说明
- 保留重要细节
```

**Step 2: 创建自动分类指南**

```markdown
# 自动分类指南

## 层级标签系统 (整合 obsidian-skills)

### 内容分类
```
#category/subcategory
```

示例：
- `#technology/ai`
- `#programming/python`
- `#design/ui-ux`

### 项目关联
```
#project/name
```

示例：
- `#project/website-redesign`
- `#project/mobile-app`

### 状态标记
```
#status/active
#status/completed
#status/archived
```

### 优先级
```
#priority/high
#priority/medium
#priority/low
```

### 内容类型
```
#video-content
#meeting-notes
#article-notes
#course-notes
```

## AI 分类策略

### 基于内容
- 识别关键词
- 分析主题
- 检测领域

### 基于来源
- 视频 → #video-content
- 会议 → #meeting-notes
- 文章 → #article-notes

### 基于目的
- 学习 → 加上具体领域标签
- 工作 → 加上项目标签
- 参考 → 加上状态标签

## 标签生成示例

输入：关于 Python 机器学习的视频教程

输出标签：
```yaml
tags:
  - #programming/python
  - #technology/machine-learning
  - #tutorial
  - #video-content
  - #status/active
```
```

**Step 3: 提交**

```bash
git add plugins/note-organizer/skills/organize-note/references/
git commit -m "feat(note-organizer): add content structuring and categorization guides"
```

---

## Task 5: 创建 NotebookLM 模板

**Files:**
- Create: `plugins/note-organizer/templates/notebooklm-optimized.md`

**Step 1: 创建模板文件**

```markdown
---
version: 1.0.0
source_type: {{source_type}}
original_url: {{original_url}}
processing_date: {{processing_date}}
tags:
  {{#each tags}}
  - {{this}}
  {{/each}}
category: {{category}}
confidence: {{confidence}}
---

# {{title}}

## 📋 内容概览

{{summary}}

## 🔑 核心要点

{{#each key_points}}
### {{@index}}. {{this.title}}
{{#each this.items}}
- {{this}}
{{/each}}
{{/each}}

## 📚 详细内容

{{#each sections}}
### {{this.title}}

{{this.content}}

{{#if this.tip}}
> [!TIP] 提示
> {{this.tip}}
{{/if}}

{{/each}}

## 🔗 相关资源

{{#each resources}}
{{#if this.wikilink}}
- [[{{this.text}}]]
{{else}}
- [{{this.text}}]({{this.url}})
{{/if}}
{{/each}}

## 📝 总结

{{conclusion}}
```

**Step 2: 提交**

```bash
git add plugins/note-organizer/templates/
git commit -m "feat(note-organizer): add NotebookLM optimized template"
```

---

## Task 6: 创建 /note-process 命令

**Files:**
- Create: `plugins/note-organizer/commands/process.md`

**Step 1: 创建命令文件**

```markdown
---
name: note-process
description: 交互式处理单个笔记文件
arguments:
  - name: file
    description: 笔记文件路径
    required: true
  - name: target
    description: 目标平台 (notebooklm/obsidian/both)
    default: both
---

# Note Process Command

## 功能

交互式处理单个笔记文件，将 AI 提取的笔记转换为结构化知识库内容。

## 处理流程

### 1. 读取文件
- 检测文件格式
- 识别内容类型
- 确定时间戳格式

### 2. 清理时间戳
- 应用 `transcript-cleaning.md` 中的规则
- 保留语义和上下文

### 3. 内容分析
- AI 识别主题
- 提取关键点
- 生成摘要

### 4. 结构重组
- 应用 `content-structuring.md` 中的模式
- 生成层次化文档

### 5. 自动分类
- 应用 `auto-categorization.md` 中的规则
- 生成层级标签

### 6. 格式化输出
- NotebookLM: 应用 `notebooklm-optimized.md` 模板
- Obsidian: 调用 `obsidian-markdown` skill

### 7. 预览确认
- 显示处理结果
- 用户确认后保存

## 使用示例

```bash
# 处理单个文件，输出双格式
/note-process ./notes/video-transcript.txt

# 只输出 NotebookLM 格式
/note-process ./notes/meeting.md --target=notebooklm

# 只输出 Obsidian 格式
/note-process ./notes/article.txt --target=obsidian
```

## 输出

处理后的文件默认保存在 `./processed/` 目录：
- `<basename>-notebooklm.md`
- `<basename>-obsidian.md`
```

**Step 2: 提交**

```bash
git add plugins/note-organizer/commands/
git commit -m "feat(note-organizer): add /note-process command"
```

---

## Task 7: 创建 /note-batch 命令

**Files:**
- Create: `plugins/note-organizer/commands/batch.md`

**Step 1: 创建命令文件**

```markdown
---
name: note-batch
description: 批量处理多个笔记文件
arguments:
  - name: pattern
    description: 文件匹配模式 (glob)
    required: true
  - name: target
    description: 目标平台 (notebooklm/obsidian/both)
    default: both
  - name: output
    description: 输出目录
    required: true
---

# Note Batch Command

## 功能

批量处理多个笔记文件，自动应用笔记整理流程。

## 处理流程

### 1. 扫描文件
- 匹配指定 glob 模式
- 验证文件可读性
- 统计处理数量

### 2. 批量处理
- 对每个文件应用处理流程
- 显示处理进度
- 记录处理结果

### 3. 生成报告
- 成功处理数量
- 失败文件列表
- 输出位置信息

## 使用示例

```bash
# 批量处理所有 txt 文件
/note-batch "./raw-notes/*.txt" --output=./processed/

# 处理所有 md 文件，只输出 NotebookLM 格式
/note-batch "./videos/*.md" --target=notebooklm --output=./notebooklm-ready/

# 递归处理目录下所有文件
/note-batch "./notes/**/*.txt" --output=./organized/
```

## 输出报告示例

```
Batch Processing Report
======================
Files matched: 15
Successfully processed: 14
Failed: 1

Output directory: ./processed/
- notebook-1-notebooklm.md ✓
- notebook-1-obsidian.md ✓
- meeting-2-notebooklm.md ✓
- meeting-2-obsidian.md ✓
...

Failed files:
- corrupted-file.md (read error)
```
```

**Step 2: 提交**

```bash
git add plugins/note-organizer/commands/
git commit -m "feat(note-organizer): add /note-batch command"
```

---

## Task 8: 更新市场配置

**Files:**
- Modify: `.claude-plugin/marketplace.json`

**Step 1: 添加 note-organizer 插件到市场配置**

在 `plugins` 数组中添加：

```json
{
  "name": "note-organizer",
  "version": "1.0.0",
  "location": "plugins/note-organizer"
}
```

**Step 2: 提交**

```bash
git add .claude-plugin/marketplace.json
git commit -m "feat(marketplace): register note-organizer plugin"
```

---

## Task 9: 创建测试文件

**Files:**
- Create: `plugins/note-organizer/tests/fixtures/sample-transcript.txt`
- Create: `plugins/note-organizer/tests/expected/notebooklm-output.md`

**Step 1: 创建测试用例 - 样本转录**

创建包含时间戳的样本文件：

```
[00:00:00] 大家好，今天我们要讲的是人工智能基础
[00:00:15] 首先，什么是人工智能？
[00:00:30] 人工智能是指由机器展现的智能
[00:01:00] 它可以分为弱人工智能和强人工智能
[00:01:30] 弱人工智能专注于特定任务
[00:02:00] 强人工智能具有类似人类的通用智能
```

**Step 2: 创建预期输出**

创建预期的 NotebookLM 格式输出：

```markdown
---
version: 1.0.0
source_type: video_transcript
processing_date: 2026-02-25T10:30:00+08:00
tags:
  - #technology/ai
  - #tutorial/introduction
category: 技术教程
confidence: high
---

# 人工智能基础

## 📋 内容概览

本视频介绍了人工智能的定义和分类，包括弱人工智能和强人工智能的区别。

## 🔑 核心要点

### 1. 人工智能定义
- 由机器展现的智能
- 模拟人类认知能力

### 2. 人工智能分类
- 弱人工智能：专注特定任务
- 强人工智能：通用智能

## 📚 详细内容

### 什么是人工智能？

人工智能是指由机器展现的智能，它试图模拟人类的认知能力。

### 人工智能的分类

#### 弱人工智能
专注于特定任务的 AI，如语音识别、图像分类等。

#### 强人工智能
具有类似人类的通用智能，能够处理各种复杂任务。

## 📝 总结

人工智能是由机器展现的智能，分为专注于特定任务的弱人工智能和具有通用智能的强人工智能。
```

**Step 3: 提交**

```bash
git add plugins/note-organizer/tests/
git commit -m "test(note-organizer): add test fixtures and expected outputs"
```

---

## Task 10: 更新项目 README

**Files:**
- Modify: `README.md`

**Step 1: 添加 note-organizer 到插件列表**

在 README.md 的插件列表中添加：

```markdown
### 3. 笔记整理器 (note-organizer)
- **版本**: 1.0.0
- **描述**: 智能笔记整理插件 - 将 AI 提取的笔记转换为结构化知识库内容
- **类别**: 生产力 (productivity)
- **功能**: 2个命令、笔记整理、时间戳清理、双平台支持
- **依赖**: obsidian-skills/obsidian-markdown
```

**Step 2: 更新安装说明**

在安装部分添加：

```bash
# 安装笔记整理器插件（需要先安装 obsidian-skills 依赖）
/plugin install obsidian-skills
/plugin install note-organizer@siunin-plugins
```

**Step 3: 提交**

```bash
git add README.md
git commit -m "docs: add note-organizer to plugin list"
```

---

## 实现顺序建议

按照以下顺序实现，每完成一个任务就提交：

1. Task 1: 创建插件基础结构
2. Task 2: 创建时间戳清理参考文档
3. Task 3: 创建 NotebookLM 格式规范
4. Task 4: 创建内容重组和自动分类参考
5. Task 5: 创建 NotebookLM 模板
6. Task 6: 创建 /note-process 命令
7. Task 7: 创建 /note-batch 命令
8. Task 8: 更新市场配置
9. Task 9: 创建测试文件
10. Task 10: 更新项目 README

## 测试计划

### 手动测试
1. 使用样本转录文件测试 /note-process
2. 验证输出格式是否符合预期
3. 测试批量处理功能

### 验收标准
- [ ] 时间戳正确去除
- [ ] 内容结构清晰
- [ ] 标签自动生成
- [ ] NotebookLM 格式正确
- [ ] Obsidian 格式正确
- [ ] 命令正常工作

## 依赖检查

开始实现前确保：
- [ ] obsidian-skills 已安装
- [ ] Claude Code CLI 正常工作
- [ ] 有 git 写权限
