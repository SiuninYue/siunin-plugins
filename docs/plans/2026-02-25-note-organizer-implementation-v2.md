# Note Organizer Plugin Implementation Plan v2

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建一个可执行的智能笔记整理插件，真正能处理文件、批量操作，包含时间戳清理、AI 分类、格式化输出功能。

**Architecture:**
- **混合模式架构**: Python 脚本处理确定性任务（时间戳清理、文件 I/O），Skill Prompt 处理创造性任务（分类、摘要）
- **命令层**: 使用正确的 `scope: command` 格式，路由到 Skill
- **Skill 层**: 协调用 Python 脚本和 AI 生成
- **测试层**: pytest 单元测试覆盖确定性功能，结构校验覆盖 AI 功能

**Tech Stack:**
- Python 3.12+ (脚本层)
- Claude Code Plugin System (命令/Skill 层)
- pytest (测试层)
- 依赖: obsidian-skills/obsidian-markdown

---

## Task 0: 定义运行时架构和契约

**Files:**
- Create: `plugins/note-organizer/docs/ARCHITECTURE.md`

**Step 1: 编写架构文档**

```markdown
# Note Organizer 运行时架构

## 组件分层

```
┌─────────────────────────────────────────────────────────┐
│                    命令层 (Commands)                      │
│  /note-process → 路由到 organize-note skill              │
│  /note-batch → 路由到 organize-note skill                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   技能层 (Skill)                          │
│  organize-note → 协调 Python 脚本 + AI 生成               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   脚本层 (Python)                         │
│  clean_timestamps.py    - 时间戳清理                      │
│  batch_scanner.py       - 文件扫描                        │
│  template_renderer.py   - 模板渲染                        │
│  file_writer.py         - 文件写入                        │
└─────────────────────────────────────────────────────────┘
```

## I/O 契约

### 输入
- 单文件: 文本文件路径（.txt, .md）
- 批量: Glob 模式（如 `./notes/*.txt`）

### 处理流程
1. 读取文件内容
2. Python 清理时间戳
3. AI 分析内容并生成元数据
4. 渲染模板
5. 写入输出文件

### 输出
- NotebookLM 格式: `<name>-notebooklm.md`
- Obsidian 格式: `<name>-obsidian.md`

## 错误处理
- 文件读取失败: 返回错误，跳过该文件
- AI 分类失败: 使用默认分类
- 写入冲突: 添加时间戳后缀
```

**Step 2: 提交**

```bash
git add plugins/note-organizer/docs/ARCHITECTURE.md
git commit -m "feat(note-organizer): define runtime architecture"
```

---

## Task 1: 创建插件基础结构

**Files:**
- Create: `plugins/note-organizer/.claude-plugin/plugin.json`
- Create: `plugins/note-organizer/README.md`
- Create: `plugins/note-organizer/LICENSE`
- Create: `plugins/note-organizer/scripts/__init__.py`

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
    "video-notes"
  ]
}
```

**Step 2: 创建 README.md**

```markdown
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
```

**Step 3: 创建 LICENSE（MIT）**

**Step 4: 创建 scripts/__init__.py**

```python
"""Note Organizer - 脚本模块"""
__version__ = "1.0.0"
```

**Step 5: 提交**

```bash
git add plugins/note-organizer/
git commit -m "feat(note-organizer): create plugin base structure"
```

---

## Task 2: 实现时间戳清理模块（Python）

**Files:**
- Create: `plugins/note-organizer/scripts/clean_timestamps.py`
- Create: `plugins/note-organizer/tests/test_clean_timestamps.py`

**Step 1: 编写失败的测试**

```python
# tests/test_clean_timestamps.py
import pytest
from scripts.clean_timestamps import clean_timestamps

def test_simple_timestamp():
    """测试简单时间戳格式 00:01:23"""
    input_text = "[00:01:23] 大家好，今天讲 AI"
    result = clean_timestamps(input_text)
    assert "[00:01:23]" not in result
    assert "大家好，今天讲 AI" in result

def test_bracket_timestamp():
    """测试方括号格式"""
    input_text = "Hello [01:23] world"
    result = clean_timestamps(input_text)
    assert "[01:23]" not in result
    assert "Hello world" in result

def test_chinese_timestamp():
    """测试中文格式"""
    input_text = "第1分23秒 这是内容"
    result = clean_timestamps(input_text)
    assert "第1分23秒" not in result
    assert "这是内容" in result

def test_preserve_content():
    """测试保留正文内容"""
    input_text = "会议时间是 10:30，不是时间戳"
    result = clean_timestamps(input_text)
    # 锚定的正则不应误删
    assert "10:30" in result or "会议时间" in result

def test_multiple_speakers():
    """测试多说话人场景"""
    input_text = """说话人A [00:01:23]: 这是第一句
说话人B [00:01:45]: 这是回应"""
    result = clean_timestamps(input_text)
    assert "说话人A:" in result
    assert "说话人B:" in result
    assert "[00:01:23]" not in result
```

**Step 2: 运行测试确认失败**

```bash
cd plugins/note-organizer
pytest tests/test_clean_timestamps.py -v
# Expected: ModuleNotFoundError or failed tests
```

**Step 3: 实现时间戳清理模块**

```python
# scripts/clean_timestamps.py
import re
from typing import List

# 时间戳正则模式（带锚定，避免误删）
TIMESTAMP_PATTERNS = [
    r"\[\d{1,2}:\d{2}:\d{2}\]",           # [00:01:23]
    r"\(\d{1,2}:\d{2}:\d{2}\)",           # (00:01:23)
    r"\[\d{1,2}:\d{2}\]",                 # [01:23]
    r"\(\d{1,2}:\d{2}\)",                 # (01:23)
    r"第\d+分\d+秒",                      # 第1分23秒
    r"Timestamp:\s*\d{1,2}:\d{2}:\d{2}",  # Timestamp: 00:01:23
    r"时间:\s*\d{1,2}:\d{2}",            # 时间: 01:23
]

def clean_timestamps(text: str) -> str:
    """
    清理文本中的时间戳，保留语义。

    Args:
        text: 包含时间戳的文本

    Returns:
        清理后的文本
    """
    result = text

    # 按顺序清理各种格式的时间戳
    for pattern in TIMESTAMP_PATTERNS:
        result = re.sub(pattern, "", result)

    # 清理多余的空格和空行
    result = re.sub(r"\s+", " ", result)  # 多个空格 -> 单个空格
    result = re.sub(r"(\n\s*){3,}", "\n\n", result)  # 多个空行 -> 两个
    result = result.strip()

    return result

def clean_timestamps_preserve_speakers(text: str) -> str:
    """
    清理时间戳，保留说话人标记。

    Args:
        text: 包含说话人和时间戳的文本

    Returns:
        清理后的文本，保留说话人标记
    """
    # 处理 "说话人 [时间戳]: 内容" 格式
    result = re.sub(r"\s*\[\d{1,2}:\d{2}:\d{2}\]\s*:", ":", text)
    result = re.sub(r"\s*\(\d{1,2}:\d{2}:\d{2}\)\s*:", ":", text)
    result = re.sub(r"\s*\[\d{1,2}:\d{2}\]\s*:", ":", text)
    result = re.sub(r"\s*\(\d{1,2}:\d{2}\)\s*:", ":", text)

    # 清理剩余时间戳
    result = clean_timestamps(result)

    return result
```

**Step 4: 运行测试确认通过**

```bash
cd plugins/note-organizer
pytest tests/test_clean_timestamps.py -v
# Expected: All tests pass
```

**Step 5: 提交**

```bash
git add plugins/note-organizer/scripts/clean_timestamps.py
git add plugins/note-organizer/tests/test_clean_timestamps.py
git commit -m "feat(note-organizer): implement timestamp cleaning module"
```

---

## Task 3: 实现批量扫描器（Python）

**Files:**
- Create: `plugins/note-organizer/scripts/batch_scanner.py`
- Create: `plugins/note-organizer/tests/test_batch_scanner.py`

**Step 1: 编写失败的测试**

```python
# tests/test_batch_scanner.py
import pytest
from pathlib import Path
from scripts.batch_scanner import scan_files, validate_file

def test_scan_files_with_pattern():
    """测试按模式扫描文件"""
    # 创建测试文件
    test_dir = Path("tests/fixtures/scan-test")
    test_dir.mkdir(exist_ok=True)
    (test_dir / "note1.txt").write_text("content 1")
    (test_dir / "note2.txt").write_text("content 2")
    (test_dir / "ignore.md").write_text("ignored")

    result = list(scan_files(test_dir / "*.txt"))

    assert len(result) == 2
    assert any("note1.txt" in str(p) for p in result)
    assert not any("ignore.md" in str(p) for p in result)

def test_validate_readable_file():
    """测试验证可读文件"""
    test_file = Path("tests/fixtures/test.txt")
    test_file.parent.mkdir(exist_ok=True)
    test_file.write_text("test content")

    assert validate_file(test_file) == True

def test_validate_nonexistent_file():
    """测试验证不存在的文件"""
    assert validate_file(Path("nonexistent.txt")) == False
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/test_batch_scanner.py -v
```

**Step 3: 实现批量扫描器**

```python
# scripts/batch_scanner.py
import glob
from pathlib import Path
from typing import Iterator, Optional

def scan_files(pattern: str) -> Iterator[Path]:
    """
    按模式扫描文件。

    Args:
        pattern: Glob 模式（如 "./notes/*.txt"）

    Yields:
        找到的文件路径
    """
    for filepath in glob.glob(pattern, recursive=True):
        path = Path(filepath)
        if validate_file(path):
            yield path

def validate_file(path: Path) -> bool:
    """
    验证文件是否可读。

    Args:
        path: 文件路径

    Returns:
        是否可读
    """
    if not path.exists():
        return False
    if not path.is_file():
        return False
    try:
        # 尝试读取一小块来验证可读性
        with open(path, "r", encoding="utf-8") as f:
            f.read(1024)
        return True
    except Exception:
        return False

def batch_scan(
    pattern: str,
    output_dir: Optional[Path] = None
) -> dict:
    """
    批量扫描并返回结果摘要。

    Args:
        pattern: Glob 模式
        output_dir: 输出目录（验证可写）

    Returns:
        扫描结果摘要
    """
    files = list(scan_files(pattern))

    result = {
        "matched": len(files),
        "valid": len(files),
        "files": [str(f) for f in files],
        "output_dir": str(output_dir) if output_dir else None
    }

    # 验证输出目录
    if output_dir:
        output_dir = Path(output_dir)
        result["output_writable"] = output_dir.exists() or output_dir.mkdir(parents=True, exist_ok=True)

    return result
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/test_batch_scanner.py -v
```

**Step 5: 提交**

```bash
git add plugins/note-organizer/scripts/batch_scanner.py
git add plugins/note-organizer/tests/test_batch_scanner.py
git commit -m "feat(note-organizer): implement batch scanner"
```

---

## Task 4: 创建参考文档（所有 references）

**Files:**
- Create: `plugins/note-organizer/skills/organize-note/SKILL.md`
- Create: `plugins/note-organizer/skills/organize-note/references/transcript-cleaning.md`
- Create: `plugins/note-organizer/skills/organize-note/references/notebooklm-format.md`
- Create: `plugins/note-organizer/skills/organize-note/references/content-structuring.md`
- Create: `plugins/note-organizer/skills/organize-note/references/auto-categorization.md`

**Step 1: 创建主技能文件**

```markdown
---
name: organize-note
version: 1.0.0
description: 智能整理 AI 提取的笔记，去除时间戳、重组结构、自动分类
tags: [note-taking, transcript, organization]
---

# Note Organizer Skill

## 触发条件

当用户需要处理以下内容时激活：
- AI 提取的视频/音频转录笔记
- 带时间戳的会议记录
- 需要整理的碎片化笔记

## 处理步骤

### 1. 调用 Python 脚本清理时间戳

使用 Bash 工具调用：
```bash
python3 scripts/clean_timestamps.py "$INPUT_FILE"
```

### 2. 分析内容并生成元数据

基于 `references/auto-categorization.md` 的规则：
- 识别内容类型（视频/会议/文章）
- 生成层级标签
- 提取关键主题

### 3. 重组内容结构

基于 `references/content-structuring.md` 的模式：
- 生成内容概览
- 提取核心要点
- 组织详细内容

### 4. 格式化输出

根据目标平台应用相应格式：
- NotebookLM: 参考 `references/notebooklm-format.md`
- Obsidian: 调用 `obsidian-markdown` skill

## 输出格式

确保输出符合目标平台的最佳实践。
```

**Step 2: 创建参考文档**

```markdown
<!-- transcript-cleaning.md -->
# 时间戳清理参考

## 支持的格式

- `[00:01:23]` 方括号格式
- `(00:01:23)` 圆括号格式
- `第1分23秒` 中文格式
- `Timestamp: 00:01:23` 描述性格式

## 清理策略

1. 保留说话人标记
2. 保留段落结构
3. 避免误删正文内容
```

```markdown
<!-- notebooklm-format.md -->
# NotebookLM 格式规范

## 元数据结构

```yaml
---
version: 1.0.0
source_type: video_transcript
processing_date: 2026-02-25T10:30:00+08:00
tags:
  - #technology/ai
category: 技术教程
---
```

## 内容结构

1. # H1 标题
2. ## 📋 内容概览
3. ## 🔑 核心要点
4. ## 📚 详细内容
5. ## 🔗 相关资源
6. ## 📝 总结
```

```markdown
<!-- content-structuring.md -->
# 内容重组指南

## 分段策略

- 长内容: 按主题分段，每段 < 1000 字
- 短内容: 单一结构

## 层级结构

```
# H1: 主标题
## H2: 主要章节 (📋🔑📚🔗📝)
### H3: 子章节
#### H4: 细节
```
```

```markdown
<!-- auto-categorization.md -->
# 自动分类指南

## 层级标签

```
#category/subcategory
#project/name
#status/active
#priority/high
#video-content
```

## 分类策略

- 识别关键词
- 分析主题
- 检测领域
```

**Step 3: 提交**

```bash
git add plugins/note-organizer/skills/
git commit -m "feat(note-organizer): add skill and reference documents"
```

---

## Task 5: 创建模板文件

**Files:**
- Create: `plugins/note-organizer/templates/notebooklm-template.md`
- Create: `plugins/note-organizer/scripts/template_renderer.py`
- Create: `plugins/note-organizer/tests/test_template_renderer.py`

**Step 1: 创建模板（使用 Python string.format，而非 Handlebars）**

```markdown
---
version: 1.0.0
source_type: {source_type}
processing_date: {processing_date}
tags:
{tags}
category: {category}
confidence: {confidence}
---

# {title}

## 📋 内容概览

{summary}

## 🔑 核心要点

{key_points}

## 📚 详细内容

{detailed_content}

## 🔗 相关资源

{resources}

## 📝 总结

{conclusion}
```

**Step 2: 编写失败的测试**

```python
# tests/test_template_renderer.py
import pytest
from scripts.template_renderer import render_template

def test_render_notebooklm_template():
    """测试渲染 NotebookLM 模板"""
    data = {
        "source_type": "video_transcript",
        "processing_date": "2026-02-25T10:30:00",
        "tags": "  - #technology/ai\n  - #tutorial",
        "category": "技术教程",
        "confidence": "high",
        "title": "测试标题",
        "summary": "这是一个测试摘要",
        "key_points": "- 要点1\n- 要点2",
        "detailed_content": "详细内容...",
        "resources": "- [[相关笔记]]",
        "conclusion": "总结..."
    }

    result = render_template("notebooklm-template.md", data)

    assert "# 测试标题" in result
    assert "## 📋 内容概览" in result
    assert "#technology/ai" in result
    assert "这是一个测试摘要" in result
```

**Step 3: 运行测试确认失败**

```bash
pytest tests/test_template_renderer.py -v
```

**Step 4: 实现模板渲染器**

```python
# scripts/template_renderer.py
from pathlib import Path
from typing import Dict, Any

def render_template(template_name: str, data: Dict[str, Any]) -> str:
    """
    渲染模板文件。

    Args:
        template_name: 模板文件名
        data: 模板变量数据

    Returns:
        渲染后的文本
    """
    template_path = Path(__file__).parent.parent / "templates" / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template.format(**data)

def format_tags_list(tags: list) -> str:
    """格式化标签列表为 YAML 格式"""
    return "\n".join(f"  - #{tag}" for tag in tags)
```

**Step 5: 运行测试确认通过**

```bash
pytest tests/test_template_renderer.py -v
```

**Step 6: 提交**

```bash
git add plugins/note-organizer/templates/
git add plugins/note-organizer/scripts/template_renderer.py
git add plugins/note-organizer/tests/test_template_renderer.py
git commit -m "feat(note-organizer): implement template renderer"
```

---

## Task 6: 创建 /note-process 命令（正确格式）

**Files:**
- Create: `plugins/note-organizer/commands/process.md`

**Step 1: 创建命令文件**

```markdown
---
description: 处理单个笔记文件，转换为结构化知识库内容
version: "1.0.0"
scope: command
inputs:
  - 笔记文件路径
  - 目标平台 (notebooklm/obsidian/both，默认: both)
outputs:
  - 清理后的笔记文件
  - 结构化笔记输出
evidence: optional
references:
  - ../skills/organize-note/SKILL.md
model: sonnet
---

# Note Process 命令

用户输入: $ARGUMENTS

## 第一步：解析输入

提取文件路径和目标平台：
- 如果是文件路径，设置为输入文件
- 目标平台默认为 "both"

## 第二步：读取文件内容

使用 Read 工具读取文件内容。

## 第三步：调用 organize-note skill

使用 Skill 工具调用 `organize-note`，传入：
- 文件内容
- 目标平台

## 第四步：写入输出文件

使用 Write 工具将结果写入：
- `<basename>-notebooklm.md` (如果目标包含 notebooklm)
- `<basename>-obsidian.md` (如果目标包含 obsidian)
```

**Step 2: 提交**

```bash
git add plugins/note-organizer/commands/process.md
git commit -m "feat(note-organizer): add /note-process command"
```

---

## Task 7: 创建 /note-batch 命令（正确格式）

**Files:**
- Create: `plugins/note-organizer/commands/batch.md`

**Step 1: 创建命令文件**

```markdown
---
description: 批量处理多个笔记文件
version: "1.0.0"
scope: command
inputs:
  - 文件匹配模式 (glob)
  - 输出目录
  - 目标平台 (默认: both)
outputs:
  - 处理结果报告
evidence: optional
references:
  - ../skills/organize-note/SKILL.md
model: sonnet
---

# Note Batch 命令

用户输入: $ARGUMENTS

## 第一步：解析输入

提取 glob 模式、输出目录和目标平台。

## 第二步：扫描文件

使用 Bash 工具调用批量扫描器：
```bash
python3 scripts/batch_scanner.py "$PATTERN"
```

## 第三步：逐个处理文件

对每个文件调用 organize-note skill。

## 第四步：生成报告

输出处理报告：
- 成功数量
- 失败列表
- 输出位置
```

**Step 2: 提交**

```bash
git add plugins/note-organizer/commands/batch.md
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

## Task 9: 更新项目 README

**Files:**
- Modify: `README.md`

**Step 1: 添加 note-organizer 到插件列表**

```markdown
### 3. 笔记整理器 (note-organizer)
- **版本**: 1.0.0
- **描述**: 智能笔记整理插件 - 将 AI 提取的笔记转换为结构化知识库内容
- **类别**: 生产力
- **功能**: 2个命令、时间戳清理、AI 分类、双平台支持
- **架构**: 混合模式（Python + Skill Prompt）
```

**Step 2: 提交**

```bash
git add README.md
git commit -m "docs: add note-organizer to plugin list"
```

---

## Task 10: 创建端到端测试（结构校验）

**Files:**
- Create: `plugins/note-organizer/tests/test_e2e_structure.py`

**Step 1: 创建结构校验测试**

```python
# tests/test_e2e_structure.py
import pytest
from pathlib import Path
from scripts.clean_timestamps import clean_timestamps_preserve_speakers
from scripts.template_renderer import render_template

def test_notebooklm_output_structure():
    """测试 NotebookLM 输出结构（不验证 AI 生成内容）"""

    # 准备测试数据
    cleaned_content = clean_timestamps_preserve_speakers(
        "说话人A [00:01:23]: 测试内容"
    )

    template_data = {
        "source_type": "test",
        "processing_date": "2026-02-25T10:30:00",
        "tags": "  - #test",
        "category": "测试",
        "confidence": "high",
        "title": "测试笔记",
        "summary": "摘要",
        "key_points": "- 要点1",
        "detailed_content": cleaned_content,
        "resources": "- [[相关]]",
        "conclusion": "总结"
    }

    result = render_template("notebooklm-template.md", template_data)

    # 验证结构（不验证具体内容）
    assert result.startswith("---\n")
    assert "version: 1.0.0" in result
    assert "# 测试笔记" in result
    assert "## 📋 内容概览" in result
    assert "## 🔑 核心要点" in result
    assert "## 📚 详细内容" in result
    assert "## 🔗 相关资源" in result
    assert "## 📝 总结" in result

def test_timestamps_removed():
    """测试时间戳被正确移除"""
    input_text = "[00:01:23] 内容 [00:02:00] 更多内容"
    result = clean_timestamps_preserve_speakers(input_text)
    assert "[00:01:23]" not in result
    assert "[00:02:00]" not in result
    assert "内容" in result
    assert "更多内容" in result
```

**Step 2: 运行测试**

```bash
pytest tests/test_e2e_structure.py -v
```

**Step 3: 提交**

```bash
git add plugins/note-organizer/tests/test_e2e_structure.py
git commit -m "test(note-organizer): add end-to-end structure tests"
```

---

## 实现顺序

按照以下顺序实现：

1. Task 0: 定义运行时架构
2. Task 1: 创建插件基础结构
3. Task 2: 实现时间戳清理模块
4. Task 3: 实现批量扫描器
5. Task 4: 创建参考文档（所有 references）
6. Task 5: 创建模板和渲染器
7. Task 6: 创建 /note-process 命令
8. Task 7: 创建 /note-batch 命令
9. Task 8: 更新市场配置
10. Task 9: 更新项目 README
11. Task 10: 创建端到端测试

## 验收标准

- [ ] 所有 pytest 测试通过
- [ ] /note-process 命令能处理单个文件
- [ ] /note-batch 命令能批量处理文件
- [ ] 输出符合 NotebookLM 格式规范
- [ ] 输出符合 Obsidian 格式规范
- [ ] 时间戳正确清理
- [ ] 文档完整

## 依赖检查

开始前确保：
- [ ] Python 3.12+ 已安装
- [ ] obsidian-skills 已安装
- [ ] pytest 已安装
