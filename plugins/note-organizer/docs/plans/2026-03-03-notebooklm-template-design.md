# NotebookLM 模板和渲染器设计文档

**日期**: 2026-03-03
**功能**: Feature #5 - NotebookLM template and renderer
**状态**: 设计阶段 (v2 - 修复 codex 审查问题)

## 概述

创建 NotebookLM 模板文件和 Python 渲染器模块，支持将处理后的笔记内容渲染为适合导入 NotebookLM 的 Markdown 格式。

## 架构

```
templates/
├── notebooklm-template.md    # NotebookLM 模板文件
scripts/
└── template_renderer.py      # 渲染器模块
```

## 数据结构

```python
from dataclasses import dataclass, asdict
from typing import List

@dataclass
class NoteData:
    """笔记数据结构"""
    title: str           # 标题
    note_type: str       # 类型: tutorial/conversation/technical/meeting/other
    tags: List[str]      # 标签列表，如 ["tech/ai", "tutorial"]
    summary: str         # 摘要 (50-100字)
    key_points: str      # 关键要点 (每行一条，- 开头)
    content: str         # 正文内容

    def validate(self) -> None:
        """验证必填字段非空
        Raises:
            ValueError: 必填字段为空
        """
```

## API 设计

```python
def format_tags_list(tags: List[str]) -> str:
    """将标签列表格式化为逗号分隔的字符串

    Args:
        tags: 标签列表，如 ["tech/ai", "tutorial"]

    Returns:
        逗号分隔的标签字符串，如 "tech/ai, tutorial"

    Examples:
        >>> format_tags_list(["tech/ai", "tutorial"])
        "tech/ai, tutorial"
    """

def render_template(template_path: str, data: NoteData) -> str:
    """渲染模板

    Args:
        template_path: 模板文件路径
        data: 笔记数据

    Returns:
        渲染后的 Markdown 文本

    Raises:
        FileNotFoundError: 模板文件不存在
        ValueError: 必填字段为空或数据验证失败
        KeyError: 模板中有未定义的占位符

    流程:
        1. 读取模板文件内容
        2. 验证数据 (data.validate())
        3. 构建 render_context: 将 data.tags 转换为逗号分隔字符串
        4. 使用 str.format() 替换占位符
        5. 返回渲染结果
    """
```

## 渲染数据映射

| NoteData 字段 | 类型 | 模板占位符 | 渲染值 |
|--------------|------|-----------|--------|
| title | str | {title} | 原值 |
| note_type | str | {note_type} | 原值 |
| tags | List[str] | {tags} | 逗号分隔字符串: "tag1, tag2, tag3" |
| summary | str | {summary} | 原值 |
| key_points | str | {key_points} | 原值 |
| content | str | {content} | 原值 |

## 模板内容

`templates/notebooklm-template.md`:

```markdown
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

## CLI 接口

```bash
# 方式 1: 从 stdin 读取 JSON (推荐，避免 shell 转义问题)
cat data.json | python3 scripts/template_renderer.py templates/notebooklm-template.md

# 方式 2: 从文件读取 JSON
python3 scripts/template_renderer.py templates/notebooklm-template.md --input data.json

# 方式 3: 直接传入 JSON (仅适用于简单数据，有 shell 转义风险)
python3 scripts/template_renderer.py templates/notebooklm-template.md '{"title": "示例", ...}'
```

**JSON 数据格式**:
```json
{
  "title": "Claude Code 使用指南",
  "note_type": "tutorial",
  "tags": ["tech/ai", "tutorial"],
  "summary": "本指南介绍...",
  "key_points": "- 第一点\n- 第二点",
  "content": "详细内容..."
}
```

## 错误处理

| 场景 | 异常类型 | 错误码 (CLI) |
|------|---------|-------------|
| 模板文件不存在 | `FileNotFoundError` | 1 |
| 必填字段为空 | `ValueError` | 2 |
| JSON 格式错误 | `json.JSONDecodeError` | 3 |
| 模板占位符未定义 | `KeyError` | 4 |
| 字段类型不匹配 | `TypeError` | 5 |

## 测试策略

```python
# tests/test_template_renderer.py

class TestFormatTagsList:
    def test_empty_list(self):
        assert format_tags_list([]) == ""

    def test_single_tag(self):
        assert format_tags_list(["tech/ai"]) == "tech/ai"

    def test_multiple_tags(self):
        assert format_tags_list(["tech/ai", "tutorial"]) == "tech/ai, tutorial"

class TestNoteDataValidation:
    def test_valid_data(self):
        data = NoteData(title="Test", note_type="tutorial", tags=[], ...)
        data.validate()  # 不应抛出

    def test_missing_required_field(self):
        data = NoteData(title="", note_type="tutorial", tags=[], ...)
        with pytest.raises(ValueError):
            data.validate()

class TestRenderTemplate:
    def test_render_basic(self):
        # 测试完整渲染流程
        result = render_template(template_path, valid_data)
        assert "# Test Title" in result

    def test_missing_template(self):
        with pytest.raises(FileNotFoundError):
            render_template("nonexistent.md", valid_data)

    def test_template_undefined_placeholder(self):
        # 模板包含 {undefined} 占位符
        with pytest.raises(KeyError):
            render_template(template_with_undefined, valid_data)

class TestCLI:
    def test_stdin_input(self):
        # 测试从 stdin 读取 JSON
        ...

    def test_file_input(self):
        # 测试从文件读取 JSON
        ...

    def test_invalid_json(self):
        # 测试 JSON 格式错误
        ...
```

## 验收标准

1. **文件存在验证**
   - `ls plugins/note-organizer/templates/notebooklm-template.md`
   - `ls plugins/note-organizer/scripts/template_renderer.py`

2. **单元测试通过**
   - `pytest tests/test_template_renderer.py -v` 全部通过

3. **功能验证**
   - `format_tags_list(["tech/ai", "tutorial"])` 返回 `"tech/ai, tutorial"`
   - 完整渲染测试: 输入 NoteData，输出符合模板格式的 Markdown

4. **错误处理验证**
   - 模板不存在时抛出 `FileNotFoundError`
   - 必填字段为空时抛出 `ValueError`
   - 占位符未定义时抛出 `KeyError`

5. **CLI 验证**
   - stdin 输入正常工作
   - --input 文件输入正常工作
   - 错误情况下返回正确退出码

## 设计决策

| 决策 | 理由 |
|------|------|
| 外部 MD 模板文件 | 模板与代码解耦，易于修改；符合验收要求 |
| dataclass 数据结构 | 类型安全，IDE 友好，支持 asdict() |
| 标签格式: 逗号分隔 | 遵守现有 template-fields.md 规范 |
| tags 字段在模板中使用逗号分隔字符串 | 与现有规范一致，避免不兼容 |
| CLI 支持 stdin 和 --input | 避免长文本 shell 转义问题 |
| 错误处理使用异常 | 符合 Python 惯例，调用方可选择处理方式 |

## 与现有规范的兼容性

- **模板字段**: 遵守 `template-fields.md` 中定义的 `{title}`, `{note_type}`, `{tags}`, `{summary}`, `{key_points}`, `{content}`
- **标签格式**: `{tags}` 使用逗号分隔字符串 (如 "tech/ai, tutorial")，与规范一致
- **模板结构**: 使用规范中定义的 NotebookLM 输出格式

## 修订记录

- **v1 (初始)**: 使用 `{formatted_tags}` 和 hashtag 格式
- **v2 (当前)**: 修复 P1 问题，使用 `{tags}` 逗号分隔格式，与现有规范一致
  - 修复模板占位符与数据结构不匹配问题
  - 修复与 template-fields.md 冲突问题
  - 改进 CLI 输入方式，支持 stdin
  - 补充完整的测试覆盖
  - 明确渲染数据映射流程
  - 统一错误契约
