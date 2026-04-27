#!/usr/bin/env python3
"""Contract tests for plugin manifest traceability fields (repository and homepage)."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"

# Exactly one alphanum/hyphen/underscore segment — rejects foo/bar, .., empty, etc.
_SOURCE_RE = re.compile(r'^\./plugins/([A-Za-z0-9_-]+)$')


def test_all_marketplace_plugins_have_traceability_fields():
    """All marketplace plugins must have homepage and repository fields with correct values."""
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    plugins = marketplace.get("plugins", [])
    assert plugins, "marketplace.json has no plugins"

    for plugin in plugins:
        source = plugin.get("source", "")
        m = _SOURCE_RE.match(source)
        assert m, (
            f"Malformed source: {source!r} — must match './plugins/<name>' "
            f"where <name> is alphanumeric/hyphens/underscores only, single segment"
        )
        plugin_name = m.group(1)
        manifest_path = REPO_ROOT / "plugins" / plugin_name / ".claude-plugin" / "plugin.json"
        assert manifest_path.exists(), f"Missing manifest: {manifest_path}"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_repo = "https://github.com/siunin/Claude-Plugins"
        expected_home = f"https://github.com/siunin/Claude-Plugins/tree/main/plugins/{plugin_name}"

        assert manifest.get("repository") == expected_repo, (
            f"{plugin_name}: wrong/missing 'repository': {manifest.get('repository')!r}"
        )
        assert manifest.get("homepage") == expected_home, (
            f"{plugin_name}: wrong/missing 'homepage': {manifest.get('homepage')!r}"
        )
