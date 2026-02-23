#!/usr/bin/env python3
"""Contract tests for marketplace/plugin manifest version consistency."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def test_marketplace_versions_match_local_plugin_manifests():
    """Marketplace plugin versions should match each local plugin manifest version."""
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))

    for plugin in marketplace.get("plugins", []):
        source = plugin.get("source")
        assert source, f"Missing source for marketplace plugin entry: {plugin}"

        manifest_path = REPO_ROOT / source / ".claude-plugin" / "plugin.json"
        assert manifest_path.exists(), f"Missing plugin manifest: {manifest_path}"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert plugin.get("version") == manifest.get("version"), (
            f"Marketplace version mismatch for {plugin.get('name')}: "
            f"{plugin.get('version')} != {manifest.get('version')}"
        )
