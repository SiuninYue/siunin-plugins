# Migration Rules Reference

## Output Modes

- `wrapper-skill` (legacy): sync into `~/.codex/skills/<wrapper-name>`.
- `codex-plugin` (new): convert into `<codex-plugins-root>/<plugin-name>` with `.codex-plugin/plugin.json`.

## Source Resolution

Record source is selected by `--record-source`:

- `manifest`: read wrapper records from `claude-migration-manifest.json`.
- `workspace`: scan `--workspace-plugins` directories directly.
- `auto`:
  - `wrapper-skill` mode defaults to manifest (with selector fallback to workspace when needed).
  - `codex-plugin` mode defaults to workspace.

Plugin name inference:

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

- In `wrapper-skill` mode:
  - `skills` -> `references/skills`
  - `commands` -> `references/commands`
  - `agents` -> `references/agents`
- In `codex-plugin` mode:
  - `skills` -> `skills`
  - `commands` -> `commands`
  - `agents` -> `agents`

Unsupported include dirs are skipped with warnings.

## On-demand Extra Directories

Extra dirs are plugin-level dirs copied to wrapper root:

- `hooks` -> `hooks`
- `scripts` -> `scripts`

Decision by `--extra-dirs`:

- `always`: copy when source dir exists.
- `auto`:
  - `wrapper-skill`: copy only if migrated text contains `${CLAUDE_PLUGIN_ROOT}`.
  - `codex-plugin`: copy when source dir exists.
- `never`: do not copy.

`codex-plugin` mode also copies optional plugin directories/files when present:

- Directories: `templates/`, `assets/`
- Files: `.mcp.json`, `.app.json`, `mcp.json`, `app.json`

## Frontmatter Normalization

### Skills

Targets:

- `wrapper-skill`: `references/skills/*/SKILL.md`
- `codex-plugin`: `skills/*/SKILL.md`

- Keep only `name` and `description`.
- Remove all other top-level keys.
- Add missing `name` from folder name.
- Add missing `description` with imported fallback text.

### Commands and Agents

Targets:

- `wrapper-skill`: `references/commands/**/*.md`, `references/agents/**/*.md`
- `codex-plugin`: `commands/**/*.md`, `agents/**/*.md`

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
  - If command args are `"{user_input}"`, append `If arguments are provided, treat them as extra context: \`<token>\`.`
  - `<token>` defaults to `$ARGUMENTS` and can be changed with `--prompt-args-token`.
  - If command args are a fixed string, append `Pass this exact argument: \`<value>\`.`
  - Otherwise, fallback to original command body.

## Hook Event Compatibility Mapping

Optional mapping controlled by `--hook-event-map`:

- `none` (default): keep hook event names unchanged.
- `userpromptsubmit-beforeagent`: for `hooks.json`, map event key/token `UserPromptSubmit` to `BeforeAgent`.

## Placeholder Handling

Placeholder candidates:

- `${CLAUDE_PLUGIN_ROOT}`
- `$CLAUDE_PLUGIN_ROOT`

Mode behavior:

- `rewrite`:
  - `wrapper-skill`: `${CODEX_HOME:-$HOME/.codex}/skills/<wrapper_name>`
  - `codex-plugin`: `${CODEX_HOME:-$HOME/.codex}/plugins/<plugin_name>`
- `warn`: keep unchanged, add warning.
- `fail`: abort plugin sync when detected.

## Wrapper Metadata Refresh

In `wrapper-skill` mode:

- Regenerate wrapper-level `SKILL.md` with source path and included dirs.
- Regenerate wrapper-level `agents/openai.yaml` for UI metadata.

In `codex-plugin` mode:

- Generate `.codex-plugin/plugin.json`.
- Preserve source plugin metadata when available (`version`, `description`, `author`, `keywords`, `license`, optional `homepage`/`repository`).
- Generate `interface` metadata with derived defaults and capability tags.

## Backup and Replace

For non-dry runs:

1. Build output in a temp directory.
2. Backup existing destination to `<output-root>/.sync-backups/<timestamp>/<name>/`.
3. Move staged output into destination.

Dry run writes nothing to destination roots.
