---
name: git-auto
description: This skill should be used when the user asks to "create a git commit", "commit changes", "commit and push", "make a commit", "handle git", "git auto", "git auto start", "git auto done", or "git auto fix", or needs git operations automated with branch/PR/merge decisions.
model: sonnet
version: "2.2.0"
scope: skill
inputs:
  - Current git repository state
  - Optional user intent (feature/bug/refactor)
  - Optional repository protection rules and CI/review signals
outputs:
  - Execution plan with reasons, enforcement mode, escalation reason, workspace mode, and worktree decision reason
  - Execution results after confirmation or autorun
evidence: optional
references:
  - "superpowers:using-git-worktrees"
  - "./references/enforcement-modes.md"
  - "./references/repo-policy-probe.md"
  - "./references/change-classification.md"
  - "./references/worktree-decision.md"
  - "./references/closeout-and-recovery.md"
  - "./references/pr-maintenance.md"
---

# Git Auto

Policy-first Git automation for branch, worktree, commit, push, PR, and merge decisions.

## Stable Command Interface

Keep command names unchanged:

- `git auto`
- `git auto start <feature-name>`
- `git auto done`
- `git auto fix <bug-description>`

### Command Semantics

| Command | Intent | Branch | Path |
|---------|--------|--------|------|
| `git auto` | Parsed from user message | Determined by strategy | Fast or Full |
| `git auto start <name>` | commit_and_push | Create `feat/<name>` | Full Path |
| `git auto done` | commit_push_pr_merge | Use current branch | Full Path + Merge Gate |
| `git auto fix <desc>` | commit_push_pr | Create `fix/<desc>` | Full Path |

## Normative Keywords

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

## Output Language Requirements

Output language MUST follow the user's active language. If the user
writes in Chinese, respond in Chinese. If in English, respond in
English. Do not mix languages within a single output block.

## Required Intent Parsing

Classify exactly one intent:

- `commit_only`
- `commit_and_push`
- `commit_push_pr`
- `commit_push_pr_merge`

Every plan MUST print:

- `Execution Intent: <commit_only|commit_and_push|commit_push_pr|commit_push_pr_merge>`

Intent rules:

- If user explicitly says "push", do not stop at commit-only.
- If user explicitly says "PR", include PR create/update.
- If user explicitly says "merge/ship", classify as `commit_push_pr_merge`.

## Default Collaboration Policy

1. Prefer short-lived branch + PR.
2. Treat default branch as policy-controlled; probe protection first.
3. Keep direct-main as exception, not default.
4. Prefer Draft PR on first push unless user asks ready-for-review.
   **Exception:** For `Execution Intent=commit_push_pr` or `commit_push_pr_merge`,
   create ready-for-review PR (not draft) since these indicate completion/ship intent.
5. MUST use squash merge for `commit_push_pr_merge`: `gh pr merge --squash --delete-branch`.
   After merge, `CommitHash` MUST be read from the default branch HEAD (`git rev-parse origin/<default_branch>` after `git fetch`), NOT from the feature branch HEAD.

## Unified Preflight (Single Fact Source)

Always run this command before branch strategy/workspace decisions:

```bash
plugins/progress-tracker/prog git-auto-preflight --json
```

The preflight result is the only source for:

- `status`
- `workspace_mode`
- `branch`
- `issues`
- `decision`
- `reason_codes`
- `default_branch`

Decision mapping:

- `DELEGATE_GIT_AUTO`: handle blockers first (detached head, operations in progress, divergence, branch checked out elsewhere).
- `REQUIRE_WORKTREE`: call `using-git-worktrees` before branch/commit flow.
- `ALLOW_IN_PLACE`: continue without workspace switch.

Every plan MUST print:

- `Workspace Mode: <in-place|worktree>`
- `Worktree Decision Reason: <reason_codes>`

## Dual-Path Execution

After Preflight, classify execution into Fast Path or Full Path.

### Fast Path Conditions

All must hold:
- Enforcement Mode = soft
- Change Class ∈ {docs_only, ci_only, low_impact}
- Preflight decision = ALLOW_IN_PLACE
- Execution Intent ≠ commit_push_pr_merge
- No PR Maintenance activation

### Fast Path Output (5 metadata fields + 1 action step)

```text
## Fast Path
Execution Intent: ...
Enforcement Mode: ...
Workspace Mode: ...
Change Class: ...
Branch Strategy: ...
1. ...
```

### Full Path Output

(Unchanged from Plan Template below)

## Policy And Strategy Resolution

After preflight:

1. Compute enforcement mode from rolling risk metrics.
2. Probe repository policy (gh-api -> local-config -> GH006 evidence -> conservative fallback).
3. Classify change set (`docs_only|ci_only|low_impact|mixed|code|unknown`).
4. Select branch strategy:
   - `standard-pr`
   - `fast-pr`
   - `direct-main-exception`

Every plan MUST print:

- `Enforcement Mode: <soft|hybrid|hard>`
- `Escalation Reason: <metric-driven reason>`
- `Repo Policy: <classification>`
- `Repo Policy Evidence: <source>`
- `Change Class: <class>`
- `Changed Files: <count>`
- `Change Size: <summary>`
- `Branch Strategy: <standard-pr|fast-pr|direct-main-exception>`
- `Strategy Reason: <why selected>`

## Execution Rules

- If `Workspace Mode=worktree`, call `using-git-worktrees` first.
- If strategy is `direct-main-exception`, verify policy and mode allow it.
- If push fails with `GH006`, preserve local commits and switch to branch + PR fallback.
- **PR Draft/Ready Decision:**
  - If `Execution Intent=commit_push_pr` or `commit_push_pr_merge`: create ready-for-review PR
  - Otherwise: create draft PR (default for first push)
- Merge execution is allowed only for `Execution Intent=commit_push_pr_merge` and all merge gates pass.
- **Squash merge (commit_push_pr_merge only):** Run `gh pr merge --squash --delete-branch`. After merge:
  1. Run `git fetch origin` to sync local state.
  2. Read squash commit SHA: `git rev-parse origin/<default_branch>`. Use this as `CommitHash`.
  3. Do NOT use the feature branch's last commit SHA as `CommitHash`.
  4. Remote branch deletion is handled by `--delete-branch`; also run `git branch -D <feature-branch>` locally (non-blocking; failures MUST NOT abort closeout).
- If `using-git-worktrees` fails to create a worktree:
  1. Report the failure reason.
  2. Ask user to choose: (a) retry with different path, (b) proceed
     in-place with explicit acknowledgment, (c) abort.
  3. Do NOT proceed without explicit user choice.

## PR Maintenance Extensions (Comments + CI)

`git-auto` MAY run a post-push PR maintenance lane when users ask to address review comments and/or fix CI.

Core rules (details in `references/pr-maintenance.md`):
- Keep stable command interface unchanged.
- Run `gh auth status` before any `gh` operations.
- Use activation modes: `address-comments`, `fix-ci`, `address-comments+fix-ci`.
- Block merge for `commit_push_pr_merge` when required checks are failing.
- Treat non-GitHub-Actions checks as external and report details URL only.

## Lightweight Autorun

When intent includes push/PR and low-risk conditions are satisfied, autorun MAY execute without extra confirmation.

When used, output MUST include:

- `Execution Mode: autorun`
- `Autorun Reason: <qualification>`
- `Autorun Scope: <through push|through push + draft-pr|through push + ready-pr>`

## Plan Template (Required)

```text
## Plan
Execution Intent: ...
Enforcement Mode: ...
Escalation Reason: ...
Repo Policy: ...
Repo Policy Evidence: ...
Workspace Mode: ...
Worktree Decision Reason: ...
Change Class: ...
Changed Files: ...
Change Size: ...
Branch Strategy: ...
Strategy Reason: ...

1. ...
2. ...
3. ...
```

Optional lines when PR maintenance is active:

- `PR Maintenance: <none|address-comments|fix-ci|address-comments+fix-ci>`
- `PR URL: <url|n/a>`
- `CI Status: <green|failing|unknown|external-checks>`
- `Comment Status: <none|pending|resolved|unknown>`

## References

- Enforcement rules: `references/enforcement-modes.md`
- Policy probing: `references/repo-policy-probe.md`
- Classification and strategy: `references/change-classification.md`
- Worktree decision contract: `references/worktree-decision.md`
- Autorun/closeout/recovery: `references/closeout-and-recovery.md`
- PR maintenance lane: `references/pr-maintenance.md`

## Execution Result Block

After completing all git operations, output the following result block verbatim. This block is machine-parsed by `/prog done`.

```
=== Git Auto Result ===
CommitHash: <full_40_char_sha>
Branch: <actual-branch-used>
PR: <url|draft_url|none>
Status: <ok|blocked>
BlockReason: <reason>
=== End Result ===
```

Rules:
- `Status: ok` → `CommitHash` MUST be the real 40-character SHA (never `none` or a placeholder).
- **Squash merge:** `CommitHash` MUST be the squash commit on the default branch (`git rev-parse origin/<default_branch>` after `git fetch`). MUST NOT be the feature branch's HEAD SHA.
- `Branch` is the actual branch pushed to (may differ from expected after GH006 fallback).
- `Branch` MUST NOT be `none`.
- `Status: blocked` → `CommitHash` MAY be `none`; `BlockReason` MUST describe why.
- `BlockReason` line is **only** output when `Status: blocked`.
- When `Status: blocked`, append recovery suggestions after `BlockReason`:
  - CI failing → "Run `git auto fix-ci` or manually fix and re-push"
  - Review pending → "Wait for approvals or `git auto address-comments`"
  - Merge conflict → "Rebase onto <branch> and retry"
- `PR` is `none` when no PR was created/updated.
- `/prog done` only parses content between `=== Git Auto Result ===` and `=== End Result ===`.
- GH006 fallback (branch + PR) is handled internally; still outputs `Status: ok` + real `CommitHash`.

The Plan Template (pre-execution output) remains unchanged and does NOT include `CommitHash`, `PR`, or `Status` fields. Those appear only in the Execution Result Block.

## Command Disambiguation

| Command | Scope | Effect |
|---------|-------|--------|
| `git auto done` | Git only | commit + push + PR + merge |
| `/prog done` | Feature lifecycle | progress state archive + delegates to `git auto done` |

## Compatibility Guarantees

- Stable command interface remains unchanged.
- Existing plan field names remain unchanged.
- New optional fields may be added, but existing fields MUST NOT be renamed.
