---
name: codex-plugin-sync
description: This skill should be used when the user asks to "sync codex skills", "migrate Claude plugin resources to Codex", "refresh migrated skills/commands/agents", "fix Codex compatibility for migrated plugins", or mentions `${CLAUDE_PLUGIN_ROOT}` compatibility in migrated resources.
version: 0.1.0
---

# Codex Plugin Sync

Synchronize Claude plugin resources into Codex wrapper skills under `~/.codex/skills`, with compatibility normalization for frontmatter and plugin-root placeholders.

## Use Cases

Activate this skill when:

- A plugin in `plugins/*` has been updated and Codex wrappers are stale.
- Migrated `skills/commands/agents` must be refreshed in Codex.
- Frontmatter compatibility (`model`/`madel`) needs normalization.
- `${CLAUDE_PLUGIN_ROOT}` placeholders must work in Codex runtime.

## Defaults

Run with these defaults unless explicitly overridden:

- `--source-policy workspace-first`
- `--extra-dirs auto`
- `--placeholder-mode rewrite`

These defaults target functional completeness with Codex compatibility.

## Primary Command

Use the sync script:

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins all \
  --source-policy workspace-first \
  --extra-dirs auto \
  --placeholder-mode rewrite
```

## Common Operations

### 1) Preview changes only

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker,package-manager \
  --dry-run \
  --report /tmp/codex-sync-report.json
```

### 2) Sync one plugin

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker
```

### 3) Strict placeholder validation

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins super-product-manager \
  --placeholder-mode fail
```

## Compatibility Rules

Apply the following transforms during sync:

- `skills/*/SKILL.md`: keep only `name` and `description`; fill missing values.
- `commands/*.md` and `agents/*.md`: remove `model`/`madel`; preserve other keys; fill missing `name`.
- Rewrite `${CLAUDE_PLUGIN_ROOT}` to `${CODEX_HOME:-$HOME/.codex}/skills/<wrapper_name>` when `--placeholder-mode rewrite`.

## Safety

- Use `--dry-run` before bulk updates.
- Non-dry runs create timestamped backups under `~/.codex/skills/.sync-backups/`.
- Review summary output and JSON report for warnings/errors.

## Additional Resources

- `references/migration-rules.md` for detailed transformation and path mapping behavior.
- `scripts/sync_codex_imports.py` for executable migration logic.
