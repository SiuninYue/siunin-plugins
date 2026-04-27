# F3: Enforce plugin metadata traceability fields

## Goal

Add `repository` and `homepage` fields to all plugin.json manifests, and add a contract test that enforces their presence.

## Design Decisions

- `repository`: string URL `"https://github.com/siunin/Claude-Plugins"` (matches Claude Code SOP and sync script expectations)
- `homepage`: per-plugin subdirectory URL `"https://github.com/siunin/Claude-Plugins/tree/main/plugins/<plugin-name>"` (traceability goal: directly locates plugin directory)

## Tasks

### T1: Add traceability fields to plugin.json — note-organizer
- File: `plugins/note-organizer/.claude-plugin/plugin.json`
- Add: `"repository": "https://github.com/siunin/Claude-Plugins"` and `"homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/note-organizer"`

### T2: Add traceability fields to plugin.json — package-manager
- File: `plugins/package-manager/.claude-plugin/plugin.json`
- Add: `"repository": "https://github.com/siunin/Claude-Plugins"` and `"homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/package-manager"`

### T3: Add traceability fields to plugin.json — progress-tracker
- File: `plugins/progress-tracker/.claude-plugin/plugin.json`
- Add: `"repository": "https://github.com/siunin/Claude-Plugins"` and `"homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/progress-tracker"`

### T4: Add traceability fields to plugin.json — super-product-manager
- File: `plugins/super-product-manager/.claude-plugin/plugin.json`
- Add: `"repository": "https://github.com/siunin/Claude-Plugins"` and `"homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/super-product-manager"`

### T5: Add contract test for required traceability fields
- File: `plugins/progress-tracker/tests/test_plugin_manifest_contract.py`
- Add: `test_all_plugin_manifests_have_traceability_fields()` — iterates all `plugins/*/.claude-plugin/plugin.json`, asserts `homepage` and `repository` are present and are non-empty strings

### T6: Run acceptance tests
- `pytest -q plugins/progress-tracker/tests/test_plugin_manifest_contract.py`
- `rg -n '"homepage"|"repository"' plugins/*/.claude-plugin/plugin.json` (should show all 4 plugins)

## Acceptance Criteria

1. `rg -n '"homepage"|"repository"' plugins/*/.claude-plugin/plugin.json` shows hits in all 4 plugin.json files
2. `pytest -q plugins/progress-tracker/tests/test_plugin_manifest_contract.py` passes
3. No plugin manifest is missing either key
