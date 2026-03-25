#!/usr/bin/env python3
"""Template renderer for note organization.

Provides NoteData dataclass and template rendering functions.
"""
from dataclasses import dataclass, field
from datetime import datetime
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
        created: 创建时间 (ISO 8601 格式，默认为当前时间)
        updated: 更新时间 (ISO 8601 格式，默认为当前时间)
    """
    title: str
    note_type: str
    tags: List[str]
    summary: str
    key_points: str
    content: str
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.now().isoformat())

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


def format_tags_yaml(tags: List[str]) -> str:
    """将标签列表格式化为 YAML 数组

    Args:
        tags: 标签列表，如 ["tech/ai", "tutorial"]

    Returns:
        YAML 数组格式的字符串，每行一个标签带 "- " 前缀
        空列表返回空字符串

    Examples:
        >>> format_tags_yaml(["tech/ai", "tutorial"])
        "\\n  - tech/ai\\n  - tutorial"
    """
    if not tags:
        return ""
    return "\n  - ".join([""] + tags)


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
        "tags_yaml": format_tags_yaml(data.tags),
        "inline_tags": format_inline_tags(data.tags),
        "summary": data.summary,
        "key_points": data.key_points,
        "content": data.content,
        "created": data.created,
        "updated": data.updated
    }

    # Step 4: 使用 str.format() 替换占位符
    try:
        rendered = template_content.format(**render_context)
    except KeyError as e:
        raise KeyError(f"Template placeholder not defined in data: {e}")

    # Step 5: 返回渲染结果
    return rendered


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

    # 优先级 1: stdin (只有在非 tty 且有数据时)
    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read()
        if stdin_data.strip():  # 确保不是空数据
            json_input = stdin_data

    # 优先级 2: --input 文件 (只有在 stdin 没有数据时)
    if json_input is None and args.input:
        try:
            with open(args.input, 'r', encoding='utf-8') as f:
                json_input = f.read()
        except FileNotFoundError:
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(3)

    # 优先级 3: 位置参数 (只有在前面都没有数据时)
    if json_input is None and args.json_data:
        json_input = args.json_data

    # 如果没有任何输入源，显示帮助并退出
    if json_input is None:
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


if __name__ == '__main__':
    main()
