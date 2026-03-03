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
