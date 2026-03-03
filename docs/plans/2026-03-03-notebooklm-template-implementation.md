# NotebookLM 模板和渲染器实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 创建 NotebookLM 模板文件和 Python 渲染器模块，支持将笔记内容渲染为适合导入 NotebookLM 的 Markdown 格式。

**架构:** 外部 MD 模板文件 + Python 渲染器模块，采用 dataclass 数据结构，支持模块导入和 CLI 双重调用方式。

**技术栈:** Python 3.12+, dataclasses, pytest, 标准库 (json, sys, pathlib)

---

## 前置检查

```bash
# 确认项目结构
cd /Users/siunin/Projects/Claude-Plugins/plugins/note-organizer
ls -la scripts/ templates/ tests/
```

---

## Task 1: 创建测试文件骨架

**文件:**
- 创建: `plugins/note-organizer/tests/test_template_renderer.py`

**Step 1: 创建测试文件骨架**

```bash
cat > plugins/note-organizer/tests/test_template_renderer.py << 'EOF'
"""Tests for template_renderer module"""
import pytest
from scripts.template_renderer import NoteData, format_tags_list, render_template


class TestFormatTagsList:
    """Test format_tags_list function"""

    def test_empty_list(self):
        result = format_tags_list([])
        assert result == ""

    def test_single_tag(self):
        result = format_tags_list(["tech/ai"])
        assert result == "tech/ai"

    def test_multiple_tags(self):
        result = format_tags_list(["tech/ai", "tutorial"])
        assert result == "tech/ai, tutorial"


class TestNoteDataValidation:
    """Test NoteData.validate method"""

    def test_valid_data(self):
        data = NoteData(
            title="Test Title",
            note_type="tutorial",
            tags=["tech/ai"],
            summary="A summary",
            key_points="- Point 1",
            content="Content"
        )
        data.validate()  # Should not raise

    def test_empty_title_raises_value_error(self):
        data = NoteData(
            title="",
            note_type="tutorial",
            tags=[],
            summary="Summary",
            key_points="- Point",
            content="Content"
        )
        with pytest.raises(ValueError, match="title"):
            data.validate()

    def test_empty_note_type_raises_value_error(self):
        data = NoteData(
            title="Title",
            note_type="",
            tags=[],
            summary="Summary",
            key_points="- Point",
            content="Content"
        )
        with pytest.raises(ValueError, match="note_type"):
            data.validate()

    def test_tags_wrong_type_raises_type_error(self):
        """TypeError is raised when tags is not a list"""
        with pytest.raises(TypeError, match="tags.*list"):
            NoteData(
                title="Title",
                note_type="tutorial",
                tags="not-a-list",  # type: ignore
                summary="Summary",
                key_points="- Point",
                content="Content"
            ).validate()


class TestRenderTemplate:
    """Test render_template function"""

    def test_render_basic(self, tmp_path):
        # Create a test template
        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n类型: {note_type}\n标签: {tags}\n")

        data = NoteData(
            title="Test Title",
            note_type="tutorial",
            tags=["tech/ai", "tutorial"],
            summary="Summary",
            key_points="- Point 1\n- Point 2",
            content="Content"
        )

        result = render_template(str(template_file), data)

        assert "# Test Title" in result
        assert "类型: tutorial" in result
        assert "标签: tech/ai, tutorial" in result

    def test_template_not_found_raises_file_not_found_error(self):
        data = NoteData(
            title="Title",
            note_type="tutorial",
            tags=[],
            summary="S",
            key_points="- P",
            content="C"
        )
        with pytest.raises(FileNotFoundError):
            render_template("nonexistent-template.md", data)

    def test_template_undefined_placeholder_raises_key_error(self, tmp_path):
        # Template with undefined placeholder
        template_file = tmp_path / "bad-template.md"
        template_file.write_text("# {title}\n{undefined_field}\n")

        data = NoteData(
            title="Title",
            note_type="tutorial",
            tags=[],
            summary="S",
            key_points="- P",
            content="C"
        )

        with pytest.raises(KeyError):
            render_template(str(template_file), data)


class TestCLI:
    """Test CLI interface"""

    def test_stdin_input(self, tmp_path, capsys):
        import subprocess
        import json

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n{content}\n")

        input_data = {
            "title": "CLI Test",
            "note_type": "tutorial",
            "tags": ["test"],
            "summary": "S",
            "key_points": "- P",
            "content": "Content from stdin"
        }

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            cwd="plugins/note-organizer"
        )

        assert result.returncode == 0
        assert "# CLI Test" in result.stdout
        assert "Content from stdin" in result.stdout

    def test_file_input_with_flag(self, tmp_path, capsys):
        import subprocess

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n{content}\n")

        input_file = tmp_path / "input.json"
        input_file.write_text('{"title": "File Test", "note_type": "tutorial", "tags": [], "summary": "S", "key_points": "- P", "content": "Content"}')

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file), "--input", str(input_file)],
            capture_output=True,
            text=True,
            cwd="plugins/note-organizer"
        )

        assert result.returncode == 0
        assert "# File Test" in result.stdout

    def test_invalid_json_exits_with_code_3(self, tmp_path):
        import subprocess

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n{content}\n")

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file)],
            input="invalid json{",
            capture_output=True,
            text=True,
            cwd="plugins/note-organizer"
        )

        assert result.returncode == 3

    def test_missing_template_exits_with_code_1(self, tmp_path):
        import subprocess

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", "nonexistent.md"],
            input='{"title": "T", "note_type": "t", "tags": [], "summary": "S", "key_points": "- P", "content": "C"}',
            capture_output=True,
            text=True,
            cwd="plugins/note-organizer"
        )

        assert result.returncode == 1

    def test_empty_field_exits_with_code_2(self, tmp_path):
        import subprocess

        template_file = tmp_path / "test-template.md"
        template_file.write_text("# {title}\n")

        result = subprocess.run(
            ["python3", "scripts/template_renderer.py", str(template_file)],
            input='{"title": "", "note_type": "t", "tags": [], "summary": "S", "key_points": "- P", "content": "C"}',
            capture_output=True,
            text=True,
            cwd="plugins/note-organizer"
        )

        assert result.returncode == 2
EOF
```

**Step 2: 运行测试确认失败**

```bash
cd plugins/note-organizer && pytest tests/test_template_renderer.py -v
```

预期: FAIL - `ModuleNotFoundError: No module named 'scripts.template_renderer'`

**Step 3: 提交测试文件**

```bash
git add plugins/note-organizer/tests/test_template_renderer.py
git commit -m "test: add test skeleton for template_renderer"
```

---

## Task 2: 创建 NoteData 数据类和 format_tags_list 函数

**文件:**
- 创建: `plugins/note-organizer/scripts/template_renderer.py`

**Step 1: 创建模块骨架和数据类**

```bash
cat > plugins/note-organizer/scripts/template_renderer.py << 'EOF'
#!/usr/bin/env python3
"""Template renderer for note organization.

Provides NoteData dataclass and template rendering functions.
"""
from dataclasses import dataclass
from typing import List
import json
import sys


@dataclass
class NoteData:
    """笔记数据结构

    Attributes:
        title: 笔记标题
        note_type: 笔记类型 (tutorial/conversation/technical/meeting/other)
        tags: 标签列表
        summary: 内容摘要 (50-100字)
        key_points: 关键要点 (每行一条，- 开头)
        content: 处理后的正文内容
    """
    title: str
    note_type: str
    tags: List[str]
    summary: str
    key_points: str
    content: str

    def validate(self) -> None:
        """验证必填字段非空

        Raises:
            ValueError: 必填字段 (title, note_type) 为空
            TypeError: tags 字段类型不正确 (必须是 list)
        """
        if not self.title or not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.note_type or not self.note_type.strip():
            raise ValueError("note_type cannot be empty")
        if not isinstance(self.tags, list):
            raise TypeError("tags must be a list")


def format_tags_list(tags: List[str]) -> str:
    """将标签列表格式化为逗号分隔的字符串

    Args:
        tags: 标签列表，如 ["tech/ai", "tutorial"]

    Returns:
        逗号分隔的标签字符串，如 "tech/ai, tutorial"
        空列表返回空字符串

    Examples:
        >>> format_tags_list(["tech/ai", "tutorial"])
        "tech/ai, tutorial"
        >>> format_tags_list([])
        ""
    """
    return ", ".join(tags)


if __name__ == '__main__':
    main()
EOF
```

**Step 2: 运行相关测试**

```bash
cd plugins/note-organizer && pytest tests/test_template_renderer.py::TestFormatTagsList -v
```

预期: PASS

```bash
cd plugins/note-organizer && pytest tests/test_template_renderer.py::TestNoteDataValidation -v
```

预期: PASS

**Step 3: 提交**

```bash
git add plugins/note-organizer/scripts/template_renderer.py
git commit -m "feat: add NoteData dataclass and format_tags_list function"
```

---

## Task 3: 实现 render_template 函数

**文件:**
- 修改: `plugins/note-organizer/scripts/template_renderer.py`

**Step 1: 添加 render_template 函数**

在 `format_tags_list` 函数后添加：

```python
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
    """
    # Step 1: 读取模板文件
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Template file not found: {template_path}")

    # Step 2: 验证数据
    data.validate()

    # Step 3: 构建 render_context，将 tags 转换为逗号分隔字符串
    render_context = {
        "title": data.title,
        "note_type": data.note_type,
        "tags": format_tags_list(data.tags),
        "summary": data.summary,
        "key_points": data.key_points,
        "content": data.content
    }

    # Step 4: 使用 str.format() 替换占位符
    try:
        rendered = template_content.format(**render_context)
    except KeyError as e:
        raise KeyError(f"Template placeholder not defined in data: {e}")

    # Step 5: 返回渲染结果
    return rendered
```

**Step 2: 运行测试**

```bash
cd plugins/note-organizer && pytest tests/test_template_renderer.py::TestRenderTemplate -v
```

预期: PASS

**Step 3: 提交**

```bash
git add plugins/note-organizer/scripts/template_renderer.py
git commit -m "feat: add render_template function"
```

---

## Task 4: 实现 CLI main 函数

**文件:**
- 修改: `plugins/note-organizer/scripts/template_renderer.py`

**Step 1: 实现 main 函数**

在文件末尾添加（在 `if __name__ == '__main__'` 之前）：

```python
def main() -> None:
    """CLI 入口

    输入优先级 (从高到低):
        1. stdin (如果有数据)
        2. --input 指定的文件
        3. 位置参数 (JSON 字符串)

    退出码:
        0: 成功
        1: 模板文件不存在
        2: 必填字段为空
        3: JSON 格式错误
        4: 模板占位符未定义
        5: 字段类型不匹配
    """
    import argparse

    parser = argparse.ArgumentParser(description="Render notebook templates")
    parser.add_argument("template", help="Path to template file")
    parser.add_argument("--input", "-i", help="Input JSON file (default: stdin or arg)")
    parser.add_argument("json_data", nargs="?", help="JSON data as string (fallback)")

    args = parser.parse_args()

    # 确定输入源 (优先级: stdin > --input > json_data)
    json_input = None

    # 优先级 1: stdin
    if not sys.stdin.isatty():
        json_input = sys.stdin.read()

    # 优先级 2: --input 文件
    elif args.input:
        try:
            with open(args.input, 'r', encoding='utf-8') as f:
                json_input = f.read()
        except FileNotFoundError:
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(3)

    # 优先级 3: 位置参数
    elif args.json_data:
        json_input = args.json_data

    else:
        parser.print_help()
        sys.exit(1)

    # 解析 JSON
    try:
        data_dict = json.loads(json_input)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(3)

    # 创建 NoteData
    try:
        note_data = NoteData(
            title=data_dict.get("title", ""),
            note_type=data_dict.get("note_type", ""),
            tags=data_dict.get("tags", []),
            summary=data_dict.get("summary", ""),
            key_points=data_dict.get("key_points", ""),
            content=data_dict.get("content", "")
        )
    except TypeError as e:
        print(f"Error: Type mismatch in data: {e}", file=sys.stderr)
        sys.exit(5)

    # 渲染模板
    try:
        result = render_template(args.template, note_data)
        print(result, end='')
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(4)
```

**Step 2: 添加可执行权限**

```bash
chmod +x plugins/note-organizer/scripts/template_renderer.py
```

**Step 3: 运行测试**

```bash
cd plugins/note-organizer && pytest tests/test_template_renderer.py::TestCLI -v
```

预期: PASS

**Step 4: 提交**

```bash
git add plugins/note-organizer/scripts/template_renderer.py
git commit -m "feat: add CLI interface with input priority (stdin > --input > arg)"
```

---

## Task 5: 创建 NotebookLM 模板文件

**文件:**
- 创建: `plugins/note-organizer/templates/notebooklm-template.md`

**Step 1: 创建模板文件**

```bash
mkdir -p plugins/note-organizer/templates
cat > plugins/note-organizer/templates/notebooklm-template.md << 'EOF'
# {title}

类型: {note_type}
标签: {tags}

## 摘要

{summary}

## 关键要点

{key_points}

## 内容

{content}
EOF
```

**Step 2: 验证模板文件**

```bash
ls -la plugins/note-organizer/templates/notebooklm-template.md
cat plugins/note-organizer/templates/notebooklm-template.md
```

预期: 文件存在，内容正确

**Step 3: 提交**

```bash
git add plugins/note-organizer/templates/
git commit -m "feat: add NotebookLM template file"
```

---

## Task 6: 手动验证完整流程

**Step 1: 测试格式化标签**

```bash
cd plugins/note-organizer
python3 -c 'from scripts.template_renderer import format_tags_list; print(format_tags_list(["tech/ai", "tutorial"]))'
```

预期输出: `tech/ai, tutorial`

**Step 2: 测试完整渲染**

```bash
cd plugins/note-organizer
echo '{"title": "Claude Code 使用指南", "note_type": "tutorial", "tags": ["tech/ai", "tutorial"], "summary": "本指南介绍 Claude Code 的基本使用方法", "key_points": "- 安装和配置\n- 基本命令\n- 常见问题", "content": "详细内容..."}' | python3 scripts/template_renderer.py templates/notebooklm-template.md
```

预期输出: 完整的渲染后 Markdown

**Step 3: 运行全部测试**

```bash
cd plugins/note-organizer && pytest tests/test_template_renderer.py -v
```

预期: 全部 PASS

**Step 4: 提交**

```bash
git add -A
git commit -m "test: verify complete template rendering workflow"
```

---

## 验收检查清单

完成所有任务后，运行以下命令验证：

```bash
# 1. 文件存在验证
ls plugins/note-organizer/templates/notebooklm-template.md
ls plugins/note-organizer/scripts/template_renderer.py

# 2. 单元测试
cd plugins/note-organizer && pytest tests/test_template_renderer.py -v

# 3. 功能验证
python3 -c 'from scripts.template_renderer import format_tags_list; print(format_tags_list(["tech/ai", "tutorial"]))'
# 预期: tech/ai, tutorial

# 4. CLI 验收
echo '{"title": "Test", "note_type": "tutorial", "tags": ["test"], "summary": "S", "key_points": "- P", "content": "C"}' | python3 scripts/template_renderer.py templates/notebooklm-template.md
```

---

## 实现注意事项

1. **CLI 输入优先级** (按 codex 审查建议):
   - stdin > --input > JSON 位置参数
   - 已在 main() 函数中明确实现

2. **TypeError 触发条件** (按 codex 审查建议):
   - 在 NoteData.validate() 中检查 tags 是否为 list 类型
   - 如果不是 list，抛出 TypeError

3. **与现有规范兼容**:
   - 标签格式使用逗号分隔 (tech/ai, tutorial)
   - 模板占位符使用 {tags} 而非 {formatted_tags}

4. **TDD 流程**:
   - 每个功能先写测试，再实现代码
   - 频繁提交，每个任务独立提交

5. **错误码契约**:
   - 1: FileNotFoundError (模板不存在)
   - 2: ValueError (必填字段为空)
   - 3: json.JSONDecodeError (JSON 格式错误)
   - 4: KeyError (占位符未定义)
   - 5: TypeError (字段类型不匹配)
