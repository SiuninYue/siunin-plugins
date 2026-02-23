<!-- GENERATED FROM docs/PROG_COMMANDS.md. DO NOT EDIT DIRECTLY. -->

# PROG Command Help

## Primary Commands

- `/prog plan <project description>`: architecture planning and stack decisions.
- `/prog init <goal description>`: initialize tracking and feature decomposition.
- `/prog`: show progress status and recommendations.
- `/prog sync`: sync capability memory from incremental Git history.
- `/prog next`: begin next feature using deterministic routing.
- `/prog done`: run acceptance checks and complete current feature.
- `/prog-fix [description|BUG-ID]`: report/list/fix bugs.
- `/prog undo`: revert most recently completed feature.
- `/prog reset`: reset tracking files with confirmation.
- `/progress-tracker:help`: show plugin command help (namespaced).
- `/prog-ui`: launch web UI server and open browser.

## Operational Notes

- Command docs in README/readme-zh are generated from this file.
- Use `generate_prog_docs.py --check` in CI-style validation.
- Use `generate_prog_docs.py --write` after changing this source.
