<!-- GENERATED FROM docs/PROG_COMMANDS.md. DO NOT EDIT DIRECTLY. -->

# PROG Command Help

## Primary Commands

- `/progress-tracker:prog-plan <project description>` (alias: `/prog-plan`): architecture planning and stack decisions.
- `/progress-tracker:prog-init <goal description>` (alias: `/prog-init`): initialize tracking and feature decomposition.
- `/progress-tracker:prog` (alias: `/prog`): show progress status and recommendations.
- `/progress-tracker:prog-sync` (alias: `/prog-sync`): sync capability memory from incremental Git history.
- `/progress-tracker:prog-update` (alias: `/prog-update`): append structured updates and optional owner assignments.
- `/progress-tracker:prog-next` (alias: `/prog-next`): begin next feature using deterministic routing.
- `/progress-tracker:prog-done` (alias: `/prog-done`): run acceptance checks and complete the current feature.
- `/progress-tracker:prog-fix [description|BUG-ID]` (alias: `/prog-fix`): report/list/fix bugs.
- `/progress-tracker:prog-undo` (alias: `/prog-undo`): revert the most recently completed feature.
- `/progress-tracker:prog-reset` (alias: `/prog-reset`): reset active tracking files with confirmation (auto-archive previous snapshot).
- `/progress-tracker:help`: show plugin command help (prefer namespaced form to avoid `/help` conflicts).
- `/progress-tracker:prog-ui` (alias: `/prog-ui`): launch web UI server and open browser.

## Operational Notes

- Command docs in README/readme-zh are generated from this file.
- Namespaced command format must not include a space after `:` (use `/progress-tracker:prog`, not `/progress-tracker: prog`).
- Runtime boundary:
  - Slash commands are for daily workflow.
  - CLI commands are for diagnostics/admin/automation.
- Cross-runtime backend path:
  - Codex/local shell: `plugins/progress-tracker/prog --project-root plugins/<name> <command>`.
  - Claude plugin internals: `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py ...`.
- In monorepo root contexts, pass `--project-root plugins/<name>` to `progress_manager.py`, `project_memory.py`, and `progress_ui_server.py`.
- Use `generate_prog_docs.py --check` in CI-style validation.
- Use `generate_prog_docs.py --write` after changing this source.
