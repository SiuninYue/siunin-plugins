# Obsidian Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create Obsidian-compatible template with YAML frontmatter, ISO 8601 timestamps, and dual tag format support.

**Architecture:** Extend existing template_renderer.py to support timestamp generation and YAML array tags. Create obsidian-template.md following Obsidian best practices.

**Tech Stack:** Python 3.14+, pytest, YAML frontmatter

---

### Task 1: Create Obsidian Template File

**Files:**
- Create: `plugins/note-organizer/templates/obsidian-template.md`

- [ ] **Step 1: Write the template file**

```bash
cat > plugins/note-organizer/templates/obsidian-template.md << 'EOF'
---
type: {note_type}
status: active
tags:
  - {tags}
created: {created}
updated: {updated}
cssclass: {note_type}
---

# {title}

## 摘要

{summary}

## 关键要点

{key_points}

## 内容

{content}

---
**标签**: {inline_tags}
EOF
```

- [ ] **Step 2: Verify template created**

Run: `ls -la plugins/note-organizer/templates/obsidian-template.md`
Expected: File exists, readable

- [ ] **Step 3: Commit**

```bash
git add plugins/note-organizer/templates/obsidian-template.md
git commit -m "feat(note-organizer): add Obsidian template with YAML frontmatter"
```

---

### Task 2: Extend NoteData with Timestamp Fields

**Files:**
- Modify: `plugins/note-organizer/scripts/template_renderer.py`

- [ ] **Step 1: Update NoteData dataclass**

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

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
        created: 创建时间 (ISO 8601, 自动生成)
        updated: 更新时间 (ISO 8601, 自动生成)
    """
    title: str
    note_type: str
    tags: List[str]
    summary: str
    key_points: str
    content: str
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.now().isoformat())
```

- [ ] **Step 2: Run existing tests**

Run: `pytest plugins/note-organizer/tests/test_template_renderer.py -v`
Expected: All tests pass (backward compatible)

- [ ] **Step 3: Commit**

```bash
git add plugins/note-organizer/scripts/template_renderer.py
git commit -m "feat(note-organizer): add timestamp fields to NoteData"
```

---

### Task 3: Add YAML Array Tags Support

**Files:**
- Modify: `plugins/note-organizer/scripts/template_renderer.py`

- [ ] **Step 1: Add YAML tags formatter**

```python
def format_tags_yaml(tags: List[str]) -> str:
    """将标签列表格式化为 YAML 数组

    Args:
        tags: 标签列表，如 ["tech/ai", "tutorial"]

    Returns:
        YAML 数组格式的字符串，每行一个标签带 "- " 前缀
        空列表返回空字符串

    Examples:
        >>> format_tags_yaml(["tech/ai", "tutorial"])
        "- tech/ai\\n- tutorial"
    """
    if not tags:
        return ""
    return "\n  - ".join([""] + tags) if tags else ""
```

- [ ] **Step 2: Add inline tags formatter**

```python
def format_inline_tags(tags: List[str]) -> str:
    """将标签列表格式化为内联 #tag 格式

    Args:
        tags: 标签列表，如 ["tech/ai", "tutorial"]

    Returns:
        空格分隔的 #tag 字符串
        空列表返回空字符串

    Examples:
        >>> format_inline_tags(["tech/ai", "tutorial"])
        "#tech/ai #tutorial"
    """
    if not tags:
        return ""
    return " ".join(f"#{tag}" for tag in tags)
```

- [ ] **Step 3: Update render_template context**

```python
def render_template(template_path: str, data: NoteData) -> str:
    # ... existing code ...

    # Step 3: 构建 render_context，添加新字段
    render_context = {
        "title": data.title,
        "note_type": data.note_type,
        "tags": format_tags_list(data.tags),  # 逗号分隔（兼容）
        "tags_yaml": format_tags_yaml(data.tags),  # YAML 数组
        "inline_tags": format_inline_tags(data.tags),  # 内联标签
        "summary": data.summary,
        "key_points": data.key_points,
        "content": data.content,
        "created": data.created,
        "updated": data.updated
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest plugins/note-organizer/tests/test_template_renderer.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add plugins/note-organizer/scripts/template_renderer.py
git commit -m "feat(note-organizer): add YAML and inline tag formatters"
```

---

### Task 4: Write Obsidian Template Tests

**Files:**
- Modify: `plugins/note-organizer/tests/test_template_renderer.py`

- [ ] **Step 1: Add YAML tags test**

```python
def test_format_tags_yaml():
    from scripts.template_renderer import format_tags_yaml
    result = format_tags_yaml(["tech/ai", "tutorial"])
    assert result == "\n  - tech/ai\n  - tutorial"

def test_format_tags_yaml_empty():
    from scripts.template_renderer import format_tags_yaml
    result = format_tags_yaml([])
    assert result == ""
```

- [ ] **Step 2: Add inline tags test**

```python
def test_format_inline_tags():
    from scripts.template_renderer import format_inline_tags
    result = format_inline_tags(["tech/ai", "tutorial"])
    assert result == "#tech/ai #tutorial"

def test_format_inline_tags_empty():
    from scripts.template_renderer import format_inline_tags
    result = format_inline_tags([])
    assert result == ""
```

- [ ] **Step 3: Add Obsidian template render test**

```python
def test_render_obsidian_template(tmp_path):
    from scripts.template_renderer import render_template, NoteData
    import datetime

    # Create test template
    template_file = tmp_path / "test-obsidian.md"
    template_file.write_text("""---
type: {note_type}
tags:
  - {tags_yaml}
created: {created}
cssclass: {note_type}
---

# {title}

{summary}
""")

    # Test data
    data = NoteData(
        title="Test Note",
        note_type="tutorial",
        tags=["python", "testing"],
        summary="Test summary",
        key_points="- Point 1",
        content="Test content"
    )

    # Render and verify
    result = render_template(str(template_file), data)
    assert "type: tutorial" in result
    assert "- python" in result
    assert "- testing" in result
    assert "cssclass: tutorial" in result
```

- [ ] **Step 4: Run tests**

Run: `pytest plugins/note-organizer/tests/test_template_renderer.py::TestFormatTagsYaml -v`
Run: `pytest plugins/note-organizer/tests/test_template_renderer.py::test_render_obsidian_template -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add plugins/note-organizer/tests/test_template_renderer.py
git commit -m "test(note-organizer): add Obsidian template tests"
```

---

### Task 5: Verify Template Variable Requirements

**Files:**
- Test: `plugins/note-organizer/templates/obsidian-template.md`

- [ ] **Step 1: Check {note_type} variable exists**

Run: `grep '{note_type}' plugins/note-organizer/templates/obsidian-template.md`
Expected: Variable found in template

- [ ] **Step 2: Check cssclass exists**

Run: `grep 'cssclass:' plugins/note-organizer/templates/obsidian-template.md`
Expected: cssclass field present in frontmatter

- [ ] **Step 3: Run full test suite**

Run: `pytest plugins/note-organizer/tests/test_template_renderer.py -v`
Expected: All tests pass (including new Obsidian tests)

- [ ] **Step 4: Final commit if needed**

```bash
# If any adjustments made
git add plugins/note-organizer/templates/obsidian-template.md
git commit -m "fix(note-organizer): ensure Obsidian template meets requirements"
```

---

## Acceptance Criteria

- [ ] `obsidian-template.md` exists with valid YAML frontmatter
- [ ] Template supports `{note_type}`, `{tags_yaml}`, `{created}`, `{updated}`, `cssclass:` variables
- [ ] NoteData includes `created` and `updated` timestamp fields
- [ ] Tests pass for YAML array formatting and inline tag generation
- [ ] Backward compatibility maintained with existing NotebookLM template

## Testing Commands

```bash
# Run all template tests
pytest plugins/note-organizer/tests/test_template_renderer.py -v

# Run specific Obsidian tests
pytest plugins/note-organizer/tests/test_template_renderer.py::test_render_obsidian_template -v

# Verify template variables
grep '{note_type}\|cssclass:' plugins/note-organizer/templates/obsidian-template.md
```
