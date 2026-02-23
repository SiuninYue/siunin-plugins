# Migration Rules Reference

## Source Resolution

1. Read wrapper records from `claude-migration-manifest.json`.
2. Determine plugin name from manifest `source` with path-aware inference:
- Prefer `<...>/plugins/<plugin-name>` when available.
- For cache paths like `<...>/cache/<publisher>/<plugin>/<version>`, use `<plugin>`.
- Fallback to source basename when no structured pattern matches.
3. Resolve source path by policy:
- `workspace-first`: `workspace/plugins/<plugin-name>` first, fallback to manifest source.
- If manifest source is a versioned cache path and the pinned version is missing, auto-fallback to latest available sibling version.
- `manifest-only`: manifest source only.
- `manifest-only` also supports versioned cache fallback to latest sibling version.
- `workspace-only`: workspace source only.

Missing source handling is controlled by `--missing-source-policy`:

- `skip` (default): emit warning and continue with remaining plugins.
- `error`: keep strict behavior and fail the run.

## Include Directory Mapping

Supported manifest include dirs:

- `skills` -> `references/skills`
- `commands` -> `references/commands`
- `agents` -> `references/agents`

Unsupported include dirs are skipped with warnings.

## On-demand Extra Directories

Extra dirs are plugin-level dirs copied to wrapper root:

- `hooks` -> `hooks`
- `scripts` -> `scripts`

Decision by `--extra-dirs`:

- `always`: copy when source dir exists.
- `auto`: copy only if migrated text contains `${CLAUDE_PLUGIN_ROOT}`.
- `never`: do not copy.

## Frontmatter Normalization

### Skills

Target: `references/skills/*/SKILL.md`

- Keep only `name` and `description`.
- Remove all other top-level keys.
- Add missing `name` from folder name.
- Add missing `description` with imported fallback text.

### Commands and Agents

Targets:

- `references/commands/**/*.md`
- `references/agents/**/*.md`

Rules:

- Remove `model` and typo `madel` keys.
- Keep all other top-level keys and body unchanged.
- Add missing `name` from file stem.

## Command-to-Prompt Export (Codex)

Optional export controlled by `--sync-prompts`:

- `none`: do not export prompts.
- `project`: write to `<project-root>/.codex/prompts` (set with `--project-root`).
- `global`: write to `$CODEX_HOME/prompts` (override with `--global-prompts-root`).
- `both`: write to both locations.

Source and conversion rules:

- Source: plugin `commands/*.md`.
- Target filename: same as command filename (for example `prog-next.md`).
- Prompt frontmatter: keep only `description`.
- Prompt body:
  - If command contains `skill: "plugin:<skill-name>"`, convert body to `Use the \`$<skill-name>\` skill now.`
  - If command args are `"{user_input}"`, append `If arguments are provided, treat them as extra context: \`$ARGUMENTS\`.`
  - If command args are a fixed string, append `Pass this exact argument: \`<value>\`.`
  - Otherwise, fallback to original command body.

## Placeholder Handling

Placeholder candidates:

- `${CLAUDE_PLUGIN_ROOT}`
- `$CLAUDE_PLUGIN_ROOT`

Mode behavior:

- `rewrite`: rewrite to `${CODEX_HOME:-$HOME/.codex}/skills/<wrapper_name>`.
- `warn`: keep unchanged, add warning.
- `fail`: abort plugin sync when detected.

## Wrapper Metadata Refresh

After resource sync and conversion:

- Regenerate wrapper-level `SKILL.md` with source path and included dirs.
- Regenerate wrapper-level `agents/openai.yaml` for UI metadata.

## Backup and Replace

For non-dry runs:

1. Build wrapper in temp directory.
2. Backup existing wrapper to `~/.codex/skills/.sync-backups/<timestamp>/<wrapper-name>/`.
3. Move staged wrapper into destination.

Dry run writes nothing to wrapper destinations.
