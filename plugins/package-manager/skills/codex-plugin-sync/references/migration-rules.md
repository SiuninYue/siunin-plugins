# Migration Rules Reference

## Source Resolution

1. Read wrapper records from `claude-migration-manifest.json`.
2. Determine plugin name from manifest `source` basename.
3. Resolve source path by policy:
- `workspace-first`: `workspace/plugins/<plugin-name>` first, fallback to manifest source.
- `manifest-only`: manifest source only.
- `workspace-only`: workspace source only.

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
