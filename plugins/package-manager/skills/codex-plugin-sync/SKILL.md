---
name: codex-plugin-sync
description: Use when syncing Claude plugins to Codex wrappers, or converting Claude plugins into Codex plugin SOP packages while keeping legacy sync flow available.
version: 0.1.0
---

# Codex Plugin Sync

This skill now supports two outputs from Claude plugin sources:

1. Legacy wrapper sync to `~/.codex/skills` (kept for backward compatibility).
2. Codex plugin SOP conversion to `.codex-plugin/plugin.json`-based plugin directories.

## Use Cases

Activate this skill when:

- A plugin in `plugins/*` has been updated and Codex wrappers are stale.
- You want to convert Claude plugins to Codex plugin packages.
- Migrated `skills/commands/agents` must be refreshed in Codex.
- Frontmatter compatibility (`model`/`madel`) needs normalization.
- `${CLAUDE_PLUGIN_ROOT}` placeholders must work in Codex runtime.

## Defaults

Run with these defaults unless explicitly overridden:

- `--source-policy workspace-first`
- `--missing-source-policy skip`
- `--extra-dirs auto`
- `--placeholder-mode rewrite`
- `--hook-event-map none`
- `--prompt-args-token '$ARGUMENTS'`

These defaults target functional completeness with Codex compatibility.

## Primary Command

Default (legacy wrapper) sync:

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins all \
  --source-policy workspace-first \
  --missing-source-policy skip \
  --extra-dirs auto \
  --placeholder-mode rewrite \
  --hook-event-map none \
  --prompt-args-token '$ARGUMENTS' \
  --sync-prompts none
```

Codex plugin SOP conversion:

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins all \
  --record-source workspace \
  --output-mode codex-plugin \
  --codex-plugins-root /Users/siunin/Projects/Claude-Plugins/plugins-codex \
  --source-policy workspace-first \
  --missing-source-policy skip \
  --extra-dirs auto \
  --placeholder-mode rewrite \
  --hook-event-map none \
  --prompt-args-token '$ARGUMENTS' \
  --sync-prompts none
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

### 2.1) Convert one Claude plugin into Codex plugin SOP

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker \
  --record-source workspace \
  --output-mode codex-plugin \
  --codex-plugins-root /Users/siunin/Projects/Claude-Plugins/plugins-codex
```

### 3) Strict placeholder validation

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins super-product-manager \
  --placeholder-mode fail
```

### 3.1) Strict missing-source validation

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins all \
  --missing-source-policy error
```

### 4) Sync progress-tracker commands into Codex project prompts

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker \
  --source-policy workspace-first \
  --extra-dirs auto \
  --placeholder-mode rewrite \
  --sync-prompts project \
  --project-root /absolute/path/to/project
```

### 5) Sync commands into both project and global prompts

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker \
  --sync-prompts both \
  --project-root /absolute/path/to/project
```

### 6) Keep old wrapper mode but force workspace records

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker \
  --record-source workspace \
  --output-mode wrapper-skill
```

### 7) Map hook event `UserPromptSubmit` to `BeforeAgent`

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins hookify \
  --hook-event-map userpromptsubmit-beforeagent
```

### 8) Export prompts with a custom user-input token

```bash
python3 /Users/siunin/Projects/Claude-Plugins/plugins/package-manager/skills/codex-plugin-sync/scripts/sync_codex_imports.py \
  --plugins progress-tracker \
  --sync-prompts project \
  --prompt-args-token '{{args}}' \
  --project-root /absolute/path/to/project
```

## Compatibility Rules

Apply the following transforms during sync:

- `skills/*/SKILL.md`: keep only `name` and `description`; fill missing values.
- `commands/*.md` and `agents/*.md`: remove `model`/`madel`; preserve other keys; fill missing `name`.
- Wrapper mode rewrite target: `${CODEX_HOME:-$HOME/.codex}/skills/<wrapper_name>`.
- Codex plugin mode rewrite target: `${CODEX_HOME:-$HOME/.codex}/plugins/<plugin_name>`.
- Optional hook event mapping in `hooks.json`: `UserPromptSubmit -> BeforeAgent` via `--hook-event-map userpromptsubmit-beforeagent`.
- Optional prompt export: map plugin `commands/*.md` to Codex prompt files in `.codex/prompts` (project) and/or `$CODEX_HOME/prompts` (global) via `--sync-prompts`.
- Prompt export argument token is configurable with `--prompt-args-token` (default: `$ARGUMENTS`).

## Safety

- Use `--dry-run` before bulk updates.
- Wrapper mode backups: `~/.codex/skills/.sync-backups/`.
- Codex plugin mode backups: `<codex-plugins-root>/.sync-backups/`.
- Review summary output and JSON report for warnings/errors.

## Additional Resources

- `references/migration-rules.md` for detailed transformation and path mapping behavior.
- `scripts/sync_codex_imports.py` for executable migration logic.
