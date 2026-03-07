"""测试插件基础结构"""
import pytest
from pathlib import Path
import sys
import json
import re

# 计算插件根目录：从测试文件位置向上查找
TEST_FILE = Path(__file__).resolve()
# 测试文件在 tests/test_base_structure.py
# 插件根目录是 tests/ 的父目录
PLUGIN_ROOT = TEST_FILE.parent.parent.resolve()


def test_architecture_document_exists():
    """验证架构文档存在"""
    assert (PLUGIN_ROOT / "docs" / "ARCHITECTURE.md").exists(), \
        f"架构文档应存在于 {PLUGIN_ROOT / 'docs' / 'ARCHITECTURE.md'}"


def test_plugin_manifest_exists():
    """验证插件清单存在"""
    assert (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").exists(), \
        f"插件清单应存在于 {PLUGIN_ROOT / '.claude-plugin' / 'plugin.json'}"


def test_readme_exists():
    """验证 README 存在"""
    assert (PLUGIN_ROOT / "README.md").exists(), \
        f"README 应存在于 {PLUGIN_ROOT / 'README.md'}"


def test_scripts_module_exists():
    """验证脚本模块存在"""
    assert (PLUGIN_ROOT / "scripts" / "__init__.py").exists(), \
        f"脚本模块应存在于 {PLUGIN_ROOT / 'scripts' / '__init__.py'}"


def test_plugin_manifest_content():
    """验证 plugin.json 内容"""
    manifest_path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    assert manifest_path.exists(), "plugin.json 应该存在"

    with open(manifest_path) as f:
        manifest = json.load(f)

    assert manifest["name"] == "note-organizer", "插件名应为 note-organizer"
    assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"]), \
        f"版本应为 semver 格式，实际为 {manifest['version']}"
    assert "智能笔记整理插件" in manifest["description"], "描述应包含关键词"
    assert "note-taking" in manifest["keywords"], "关键词应包含 note-taking"


def test_scripts_module_version():
    """验证脚本模块版本"""
    # 使用计算的插件根目录
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))

    from scripts import __version__

    manifest_path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    assert __version__ == manifest["version"], \
        f"scripts.__version__ 应与 manifest 版本一致，manifest={manifest['version']} scripts={__version__}"
