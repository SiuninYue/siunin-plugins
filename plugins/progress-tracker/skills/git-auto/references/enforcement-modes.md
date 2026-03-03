# Enforcement Modes

Compute one mode from 14-day signals: `soft`, `hybrid`, `hard`.

## Escalation Inputs

- `sync_risk_events`: detached head, diverged branch, non-fast-forward rejection, operation in progress.
- `integration_regressions`: revert/hotfix within 24h after merge to default branch.
- `parallel_pressure`: 3+ active contributors or concurrent overlapping PRs.

## Transition Rules

- `soft -> hybrid` when `sync_risk_events >= 2` or `integration_regressions >= 1` or `parallel_pressure=true`.
- `hybrid -> hard` when `sync_risk_events >= 4` or `integration_regressions >= 2`.
- `hard -> hybrid` after 14 clean days.
- `hybrid -> soft` after another 14 clean days.

## Required Output Fields

Every plan includes:

- `Enforcement Mode: <soft|hybrid|hard>`
- `Escalation Reason: <metric-driven reason>`
