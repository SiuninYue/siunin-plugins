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


if __name__ == '__main__':
    main()
