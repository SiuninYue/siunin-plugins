# F3: Enforce plugin metadata traceability fields

## Goal

Add `repository` and `homepage` fields to all marketplace plugin.json manifests, and add a repo-level contract test that enforces their presence and correct values across ALL marketplace plugins.

## Design Decisions

- `repository`: string URL `"https://github.com/siunin/Claude-Plugins"` (fixed value for all plugins)
- `homepage`: per-plugin subdirectory URL `"https://github.com/siunin/Claude-Plugins/tree/main/plugins/<plugin-name>"`
  where `<plugin-name>` is derived from regex capture group `m.group(1)` via `_SOURCE_RE`
- Test location: **`tests/test_plugin_manifest_traceability.py`** (repo-level, same as `test_marketplace_manifest_versions.py`)
  - Rationale: this is a repo-wide contract, not single-plugin contract
- Test scope: traverse `marketplace.json` dynamically — auto-covers future plugins
- Test assertion: verify both presence AND exact value
- Path resolution: strict regex `r'^\./plugins/([A-Za-z0-9_-]+)$'` match — enforces exactly one path segment,
  rejects `./plugins/foo/bar`, `./plugins/..`, `./plugins/` (empty), any dots or slashes in plugin name
- Acceptance gate: pytest is the primary gate; rg command is informational audit only

## Tasks

### T1 (RED): Write failing repo-level contract test
- File: `tests/test_plugin_manifest_traceability.py` (NEW, repo-level)
- Structure:
  ```python
  import json
  import re
  from pathlib import Path

  REPO_ROOT = Path(__file__).resolve().parent.parent
  MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"

  # Exactly one alphanum/hyphen/underscore segment — rejects foo/bar, .., empty, etc.
  _SOURCE_RE = re.compile(r'^\./plugins/([A-Za-z0-9_-]+)$')

  def test_all_marketplace_plugins_have_traceability_fields():
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

          assert manifest.get("repository") == expected_repo, \
              f"{plugin_name}: wrong/missing 'repository': {manifest.get('repository')!r}"
          assert manifest.get("homepage") == expected_home, \
              f"{plugin_name}: wrong/missing 'homepage': {manifest.get('homepage')!r}"
  ```
- Run: `pytest -q tests/test_plugin_manifest_traceability.py` → must FAIL (fields missing)

### T2 (GREEN): Add traceability fields — note-organizer
- File: `plugins/note-organizer/.claude-plugin/plugin.json`
- Add after existing fields:
  ```json
  "repository": "https://github.com/siunin/Claude-Plugins",
  "homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/note-organizer"
  ```

### T3 (GREEN): Add traceability fields — package-manager
- File: `plugins/package-manager/.claude-plugin/plugin.json`
- Add:
  ```json
  "repository": "https://github.com/siunin/Claude-Plugins",
  "homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/package-manager"
  ```

### T4 (GREEN): Add traceability fields — progress-tracker
- File: `plugins/progress-tracker/.claude-plugin/plugin.json`
- Add:
  ```json
  "repository": "https://github.com/siunin/Claude-Plugins",
  "homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/progress-tracker"
  ```

### T5 (GREEN): Add traceability fields — super-product-manager
- File: `plugins/super-product-manager/.claude-plugin/plugin.json`
- Add:
  ```json
  "repository": "https://github.com/siunin/Claude-Plugins",
  "homepage": "https://github.com/siunin/Claude-Plugins/tree/main/plugins/super-product-manager"
  ```

### T6 (Verify): Run acceptance tests
- Primary gate: `pytest -q tests/test_plugin_manifest_traceability.py` — all pass
- Regression: `pytest -q plugins/progress-tracker/tests/test_plugin_manifest_contract.py` — existing tests unbroken
- Informational audit only (no count expectation): `rg -n '"(homepage|repository)"' plugins/*/.claude-plugin/plugin.json`
  — scans all plugins/ dirs including non-marketplace ones; result is for visual inspection only,
  not a correctness gate (pytest contract test is the authoritative check)

## Risks

- Adding fields to plugin.json may conflict with future schema changes or marketplace validation rules
- Strict regex for source path may reject valid plugins with unusual names (mitigated by allowing hyphens/underscores)
- Test traverses marketplace.json dynamically; if marketplace.json structure changes, test may need updating
- Homepage URLs depend on repository staying at github.com/siunin/Claude-Plugins; URL format change would require bulk update

## Acceptance Criteria

1. `pytest -q tests/test_plugin_manifest_traceability.py` passes (primary gate)
2. `pytest -q plugins/progress-tracker/tests/test_plugin_manifest_contract.py` still passes (no regression)
3. Contract test traverses `marketplace.json` dynamically (no hardcoded plugin list)
4. Contract test validates both presence AND exact expected values
5. Contract test validates source with `re.compile(r'^\./plugins/([A-Za-z0-9_-]+)$')` — rejects multi-segment paths, dots, path traversal, empty names
6. No marketplace plugin manifest is missing `repository` or `homepage`
