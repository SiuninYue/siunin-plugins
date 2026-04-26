# Drift Prevention P0 Status

This document is the canonical status map for:

- `Plan: Progress Tracker Drift Prevention with Claude Code Plugin and Codex Skill Compatibility`
- `Plan: 低学习成本优先的命令分层（保留能力，隐藏复杂度）`

It exists to prevent tracker/docs drift and to clarify what is done vs. pending.

## Completed

### Batch 1: Drift detection + reconcile + gates

- Backend-first drift analysis in `progress_manager.py` (`analyze_reconcile_state`).
- Stable CLI command `prog reconcile` with fixed diagnosis and next-step outputs.
- `status` shows `Reality Check` when drift is detected.
- `prog check` includes drift data in recovery payload.
- `prog next-feature` blocks when active feature should be closed first.
- `prog complete` blocks on `scope_mismatch` / `context_mismatch`.
- Hooks remain advisory (`SessionStart -> check`), not the sole correctness gate.

### Batch 2: Low-learning-cost command layering

- Daily path kept simple:
  - `/prog`
  - `/prog-next`
  - `/prog-done`
- Admin path is explicit but optional:
  - `prog check`
  - `prog reconcile`
  - `prog defer`
  - `prog resume`
  - `prog next-feature --json`
- README/readme-zh command docs now document this layering.

## Pending (Not Yet Implemented)

These items are still open against the original drift-prevention P0:

- Scope preset CLI:
  - `prog scope set <project-root>`
  - `prog scope show`
  - `prog scope clear`
- Default scope persistence in `.claude/progress-tracker.local.md`.
- Full-completion snapshot archive flow:
  - `docs/progress-tracker/archive/completions/<timestamp>-<slug>.progress.json`
  - `docs/progress-tracker/archive/completions/<timestamp>-<slug>.progress.md`
  - `progress_history.json` entry with `reason=completed`
  - Active state entrypoint rewritten to completed summary + archive pointer.

## Tracker Mapping (Current)

- Completed:
  - Feature 1-10: normalization backlog delivery (`baseline -> summary projection`).
  - Feature 13: `P0 Batch 1: Reconcile engine + check/next/done gates`
  - Feature 14: `Plan: 低学习成本优先的命令分层（保留能力，隐藏复杂度）`
- Pending:
  - Feature 11: `命令文档与帮助更新（含 Drift Prevention/Codex 兼容）`
  - Feature 12: `全量回归与验收报告`

## Usage Notes

- Claude Code plugin and Codex skill should both call the same backend CLI (`plugins/progress-tracker/prog ...`).
- In monorepo root, prefer explicit `--project-root` until scope preset commands are implemented.
