---
description: Complete current feature via deterministic acceptance gatekeeping
version: "2.4.1"
scope: command
inputs:
  - User request to complete current feature
outputs:
  - Test execution results
  - Feature marked as completed or finish-pending
  - Git closeout result (merge-first with policy gates; fallback to blocker summary)
  - Next step recommendation
evidence: optional
references: []
model: sonnet
---

`/prog-done` uses a split architecture:
- Skill layer (`progress-tracker:feature-complete`) handles orchestration and user-facing flow.
- CLI layer (`progress_manager.py done`) enforces deterministic gates, acceptance execution, report writing, and completion state updates.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--commit <hash>` | HEAD | Git commit hash to record for this completion |
| `--run-all` | false | Run all acceptance tests even if one fails |
| `--skip-archive` | false | Skip document archiving after completion |
| `--no-cleanup` | false | Skip automatic post-done cleanup of worktree and feature branch |
| `--check` | false | Run all validation gates (acceptance included) without persisting state |

### --check exit codes

`prog done --check` uses gate-native exit codes:

- `0`: all gates pass
- non-zero: the **first failing gate's original exit code** (not a generic `1`)
- typical failures include `2` (workflow phase), `3` (acceptance), `6` (evaluator), `7` (reviews), `8` (ship-check), `9` (sprint ledger), `10` (reconcile), `11` (plan validation)

### --no-cleanup

By default, `prog done` automatically cleans up the feature workspace after successful completion:

1. Removes the git worktree (worktree mode only)
2. Deletes the local feature branch (`git branch -d`)
3. Deletes the remote tracking branch (`git push origin --delete`, non-blocking)

Cleanup failures are **non-blocking** — they print a `[CLEANUP] WARN` message but do not change the exit code or affect the completed feature state.

Use `--no-cleanup` when:
- You want to inspect the worktree state before removing it
- Cleanup is handled by CI/CD
- You need to cherry-pick or diff against the feature branch after done

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:feature-complete"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
