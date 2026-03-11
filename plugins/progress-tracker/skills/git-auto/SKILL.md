---
name: git-auto
description: This skill should be used when the user asks to "create a git commit", "commit changes", "commit and push", "make a commit", "handle git", "git auto", "git auto start", "git auto done", or "git auto fix", or needs git operations automated with branch/PR/merge decisions.
model: sonnet
version: "2.1.0"
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

## Normative Keywords

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

## Output Language Requirements

**Output MUST use English OR Chinese ONLY.** DO NOT use Korean or any other language:

- Plan descriptions MUST use English or Chinese
- All reason text MUST use English or Chinese
- Status messages MUST use English or Chinese
- Any user-facing content MUST use English or Chinese
- **DO NOT use Korean** - this is a bug to prevent

Examples of CORRECT output:
- `Escalation Reason: 单独项目，14天内无 sync risk 事件`
- `Worktree Decision Reason: MAY rule — 重复使用 feature branch，无冲突信号`
- `Change Size: ~154 insertions, ~12,579 deletions (主要是旧文档归档移动)`

Examples of INCORRECT output (DO NOT DO THIS):
- `Escalation Reason: 단독 프로젝트, 14일간 sync risk event 없음` ❌
- `Worktree Decision Reason: MAY rule — 기존 feature branch 반복, 충돌 신호 없음` ❌

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
5. Prefer squash merge.

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

## Policy And Strategy Resolution

After preflight:

1. Compute enforcement mode from rolling risk metrics.
2. Probe repository policy (gh-api -> local-config -> GH006 evidence -> conservative fallback).
3. Classify change set (`docs_only|ci_only|docs_ci_small|mixed|code|unknown`).
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
- Merge execution is allowed only for `Execution Intent=commit_push_pr_merge` and all merge gates pass.

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
- `Autorun Scope: <through push|through push + draft-pr>`

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

## Compatibility Guarantees

- Stable command interface remains unchanged.
- Existing plan field names remain unchanged.
- New optional fields may be added, but existing fields MUST NOT be renamed.
