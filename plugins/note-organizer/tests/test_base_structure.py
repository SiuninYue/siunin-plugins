"""测试插件基础结构"""
import pytest
from pathlib import Path
import sys


def test_architecture_document_exists():
    """验证架构文档存在"""
    assert Path("plugins/note-organizer/docs/ARCHITECTURE.md").exists(), \
        "架构文档应存在于 docs/ARCHITECTURE.md"


def test_plugin_manifest_exists():
    """验证插件清单存在"""
    assert Path("plugins/note-organizer/.claude-plugin/plugin.json").exists(), \
        "插件清单应存在于 .claude-plugin/plugin.json"


def test_readme_exists():
    """验证 README 存在"""
    assert Path("plugins/note-organizer/README.md").exists(), \
        "README 应存在于根目录"


def test_scripts_module_exists():
    """验证脚本模块存在"""
    assert Path("plugins/note-organizer/scripts/__init__.py").exists(), \
        "脚本模块应存在于 scripts/__init__.py"


def test_plugin_manifest_content():
    """验证 plugin.json 内容"""
    import json

    manifest_path = Path("plugins/note-organizer/.claude-plugin/plugin.json")
    assert manifest_path.exists(), "plugin.json 应该存在"

    with open(manifest_path) as f:
        manifest = json.load(f)

    assert manifest["name"] == "note-organizer", "插件名应为 note-organizer"
    assert manifest["version"] == "1.0.0", "版本应为 1.0.0"
    assert "智能笔记整理插件" in manifest["description"], "描述应包含关键词"
    assert "note-taking" in manifest["keywords"], "关键词应包含 note-taking"


def test_scripts_module_version():
    """验证脚本模块版本"""
    # 添加到路径以便导入
    plugin_root = Path("plugins/note-organizer")
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))

    from scripts import __version__
    assert __version__ == "1.0.0", f"版本应为 1.0.0，实际为 {__version__}"
