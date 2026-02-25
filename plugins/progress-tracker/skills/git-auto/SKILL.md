---
name: git-auto
description: This skill should be used when the user asks to "create a git commit", "commit changes", "commit and push", "make a commit", "handle git", "git auto", "git auto start", "git auto done", or "git auto fix", or needs git operations automated with branch/PR/merge decisions.
model: sonnet
version: "1.3.2"
scope: skill
inputs:
  - Current git repository state
  - Optional user intent (feature/bug/refactor)
  - Optional repository protection rules and CI/review signals
  - Optional complexity/scope hint for worktree decision
outputs:
  - Execution plan with reasons, enforcement mode, escalation reason, workspace mode, and worktree decision reason
  - Execution results after confirmation
evidence: optional
references:
  - "using-git-worktrees"
---

# Git Auto

Intelligent Git automation that analyzes repository state and decides branch, worktree, commit, push, PR, and merge actions with explicit governance rules.

## Purpose

Eliminate Git decision fatigue while enforcing stable collaboration defaults:
- Determine whether to use in-place workspace or worktree isolation.
- Determine whether to create or reuse a short-lived branch.
- Detect repository branch-protection policy before choosing direct-main vs PR flow.
- Route low-risk docs/CI changes through a fast PR lane when default branch is protected.
- Determine whether to commit and push now or delay for sync recovery.
- Determine whether to create a Draft PR or update an existing PR.
- Recover automatically from protected-branch push rejection (`GH006`) by falling back to branch + PR.
- Determine whether merge can be recommended under current enforcement mode.
- Execute an accelerated end-to-end path (commit -> push -> PR -> checks -> merge) when the user explicitly requests a full ship/merge flow and policy gates pass.

## Stable Command Interface

Keep command names unchanged:
- `git auto`
- `git auto start <feature-name>`
- `git auto done`
- `git auto fix <bug-description>`

## When to Use

Invoke this skill when:
- User says "handle git", "git auto", "process changes"
- User wants to commit but isn't sure about branching/worktree strategy
- User has changes and wants AI to handle the full workflow
- User wants to automate repetitive Git operations
- User explicitly asks to push/ship quickly, create a PR, or complete the full push+PR+merge sequence

## Explicit Intent Parsing (Required)

Parse user intent before planning and classify exactly one:

- `commit_only`
- `commit_and_push`
- `commit_push_pr`
- `commit_push_pr_merge`

Intent cues:

- If user explicitly says "push", `MUST NOT` stop at commit-only.
- If user explicitly says "PR", `MUST` include PR creation/update.
- If user explicitly says "merge", "合并 main", "走完流程", or "ship it", classify as `commit_push_pr_merge`.
- If user expresses urgency ("快速修复", "hotfix", "urgent"), `SHOULD` prefer Fast PR Lane / accelerated PR flow when eligible.

Every generated plan `MUST` print:

- `Execution Intent: <commit_only|commit_and_push|commit_push_pr|commit_push_pr_merge>`

### Intent normalization for PR-only repositories

When repo policy is known to be `protected_pr_required` and the user asks for a lightweight change flow without explicitly saying "commit only", `git-auto` `SHOULD` normalize intent upward to at least `commit_push_pr`.

Examples:

- "顺手提交一下" on eligible docs/CI small changes in a PR-only repo -> normalize to `commit_push_pr`
- "只提交不要推" -> keep `commit_only` (explicit user override wins)

## Normative Keywords

The terms `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

## Default Collaboration Policy

Apply these defaults unless user gives explicit override:

1. Use trunk-based collaboration with short-lived branches.
2. Treat default branch (`main`/`master`) as policy-controlled; detect actual remote protection before execution.
3. When default branch is protected, route all changes through PR; use a Fast PR Lane for eligible docs/CI small changes.
4. When default branch is not protected, direct-main commits are still exception paths, not the default.
5. Create Draft PR on first push of a new short-lived branch unless user explicitly requests ready-for-review.
6. Recommend squash merge as the default merge strategy.

Mandatory rules:
- `MUST` probe repository policy (protected default branch / PR requirement) before selecting direct-main execution.
- `MUST` classify the change set before branch-strategy selection.
- `MUST` create or switch to a short-lived branch before committing on default branch unless a direct-main exception is explicitly allowed.
- `MUST` create a Draft PR on first push when no PR exists for the branch (unless user explicitly asks for non-draft).
- `MUST` autorun eligible lightweight changes through `push + Draft PR` when intent includes push/PR, sync preflight is clean, and no high-risk gate is triggered.
- `MUST NOT` recommend merge when branch is behind or diverged from upstream.
- `MUST NOT` execute merge unless user intent is `commit_push_pr_merge` (or equivalent explicit merge request).
- `SHOULD` rebase on upstream before push/merge recommendation.
- `MUST` implement `GH006` fallback: if a direct-main push is rejected by branch protection, create/switch to a short-lived branch and continue via PR without losing the local commit.
- `MUST NOT` bypass branch protection, required checks, or required reviews for urgent/fast requests.

## Enforcement Modes

Compute one active mode: `soft`, `hybrid`, or `hard`.

### soft

- Branching: `MUST` use short-lived branch on default branch by default.
- Direct-main exception: `MAY` allow for eligible `docs+ci_small` changes only when default branch is not protected (or protection state is explicitly known to allow direct push).
- PR: `MUST` create Draft PR on first push.
- Pull/Rebase: `SHOULD` run sync checks at session start and pre-merge.
- Merge recommendation: allow only when no critical sync risk is present.

### hybrid

- Includes all `soft` rules.
- Direct-main exception: `SHOULD NOT`; allow only with explicit user override and compatible repo policy.
- Pull/Rebase: `MUST` run sync checks at session start and pre-merge.
- Merge recommendation: `MUST` require clean sync state + passing CI + review-ready signal.

### hard

- Includes all `hybrid` rules.
- Branching: `MUST NOT` allow direct default-branch commit path in plans.
- Direct-main exception: `MUST NOT`.
- Worktree: `MUST` isolate new feature/large refactor starts in worktree.
- Merge recommendation: `MUST` require clean sync state + passing CI + required review approvals + no unresolved blocking discussion.
- Any missing required signal blocks merge recommendation.

## Escalation Threshold Standard (14-day rolling)

Evaluate a 14-day rolling window on every planning run.

### Metrics

1. `sync_risk_events`
   - Count each occurrence of:
     - detached HEAD state
     - diverged branch (ahead > 0 and behind > 0)
     - non-fast-forward push rejection
     - in-progress rebase/merge/cherry-pick/revert conflict state
2. `integration_regressions`
   - Count each revert or hotfix occurring within 24 hours after merge to default branch.
3. `parallel_pressure`
   - `true` when either condition is met:
     - 3+ active contributors in current window
     - high PR concurrency on default branch (multiple concurrent active PRs that materially overlap)

### Transition Rules

Apply transitions exactly:

1. `soft -> hybrid` when:
   - `sync_risk_events >= 2`, or
   - `integration_regressions >= 1`, or
   - `parallel_pressure == true`
2. `hybrid -> hard` when:
   - `sync_risk_events >= 4`, or
   - `integration_regressions >= 2`
3. `hard -> hybrid` when:
   - 14 consecutive clean days with `sync_risk_events = 0` and `integration_regressions = 0`
4. `hybrid -> soft` when:
   - another 14 consecutive clean days with no regression

### Escalation Output Contract

Every generated execution plan `MUST` print:

- `Enforcement Mode: <soft|hybrid|hard>`
- `Escalation Reason: <explicit metric-driven reason>`

## Repository Policy Probe (Required)

Run a remote-policy probe before selecting branch strategy on the default branch.

### Goals

1. Detect whether the default branch is protected.
2. Detect whether PR-only flow is required.
3. Detect whether required checks gate merge (and therefore PR path is expected).
4. Cache evidence from prior push failures (especially `GH006`) when API access is unavailable.

### Preferred Sources (in order)

1. `gh api` branch/ruleset metadata (authoritative when authenticated)
2. Local project policy configuration (if maintained by plugin/project, including exported GitHub branch ruleset JSON with `pull_request` and `required_status_checks`)
3. Observed push errors from current session (e.g., `GH006`)
4. Conservative fallback: treat default branch as protected for planning

### Local policy file hints (recommended)

When checking `local-config`, `git-auto` `SHOULD` probe common repository paths before falling back:

- `.github/rules/main.json`
- `.github/rulesets/main.json`
- `docs/github-rules/main.json`
- `docs/rules/main.json`

If a matching file exists and shows `pull_request` and/or `required_status_checks`, `git-auto` `SHOULD` use `Repo Policy Evidence: local-config`.

### Output Contract

Classify repo policy as one of:

- `protected_pr_required`
- `protected_unknown_rules`
- `unprotected`
- `unknown_conservative`

Every generated plan `MUST` print:

- `Repo Policy: <classification>`
- `Repo Policy Evidence: <gh-api|push-error-gh006|local-config|conservative-default>`

## Change Classification and Fast PR Lane

Classify the current diff before selecting branch strategy.

### Required outputs

- `Change Class: <docs_only|ci_only|docs_ci_small|mixed|code|unknown>`
- `Changed Files: <count>`
- `Change Size: <added+deleted summary>`

### `docs+ci_small` eligibility (default)

`docs+ci_small` is eligible only when **all** conditions are true:

1. Every changed path matches the allowlist:
   - `docs/**`
   - `**/*.md`
   - `.github/workflows/**`
   - `.github/actions/**`
2. No path matches the denylist (examples):
   - application/source code files outside `.github/**`
   - dependency manifests / lockfiles (`package.json`, `package-lock.json`, `pnpm-lock.yaml`, `pyproject.toml`, `Cargo.toml`, etc.)
   - binaries or generated artifacts
3. Total changed files `<= 5`
4. Total changed lines (`insertions + deletions`) `<= 200`

### Strategy implications

- If `Repo Policy` is `protected_pr_required`: use `Fast PR Lane` for `docs+ci_small` (branch + PR, minimal checks path).
- If `Execution Intent` is `commit_push_pr_merge` and merge gates pass, extend the selected PR path through checks + merge instead of stopping after PR creation.
- If `Repo Policy` is `unprotected` and mode allows: direct-main exception `MAY` be used for `docs+ci_small`.
- If classification is `mixed` or `code`: use standard branch + PR flow.

## Lightweight Autorun (Default for Low-Risk Push/PR Intents)

When the user intent includes push or PR (`commit_and_push`, `commit_push_pr`, `commit_push_pr_merge`), `git-auto` `SHOULD` avoid an extra confirmation step for low-risk changes and execute the eligible path automatically.

### Autorun eligibility (all required)

1. `Change Class` is `docs_only`, `ci_only`, or `docs_ci_small`
2. Sync preflight is clean (no detached HEAD, no in-progress operation, no diverged branch, no blocking behind state)
3. `Workspace Mode` resolves to `in-place` (no worktree MUST-trigger)
4. Branch strategy resolves to `fast-pr` or `direct-main-exception` (and the selected strategy is permitted by policy/mode)
5. User did not explicitly ask for preview/plan-only/manual confirmation

### Autorun behavior

- `fast-pr` on protected/PR-required repos: `MUST` autorun through:
  1. create/switch short-lived branch
  2. stage + commit
  3. push branch
  4. create Draft PR
- `direct-main-exception` on unprotected repos: `MAY` autorun through direct push
- If any autorun precondition fails, fall back to the normal confirmation-based path

### Autorun output contract

When autorun is used, plans/results `MUST` print:

- `Execution Mode: autorun`
- `Autorun Reason: <why change qualified>`
- `Autorun Scope: <through push + draft-pr|through push>`

### Lightweight PR presentation (noise control)

For autorun-created lightweight PRs, `git-auto` `SHOULD` apply a compact naming/metadata convention to reduce review noise:

- PR title prefix: `docs:` or `chore:` (based on `Change Class`)
- Optional lightweight marker in title/body: `fast-pr`
- If labels are used in the repo, `SHOULD` add `docs`, `chore`, and/or `fast-pr` labels when available

This keeps high PR volume manageable even when branch protection requires PRs for small changes.

## Accelerated Closeout Path (User-Requested)

When `Execution Intent=commit_push_pr_merge`, `git-auto` `MAY` run a rapid closeout sequence:

1. Commit changes
2. Push branch
3. Create or update PR
4. Check PR status (`gh pr checks`)
5. Merge PR when merge gates pass
6. Optionally delete branch and sync local `main`

Guardrails:

- `MUST` require explicit user merge intent before merge execution.
- `MUST` stop and report blockers when checks/reviews are pending or failing.
- `SHOULD` create a ready PR (not draft) when user explicitly asks for merge and local policy allows.
- `MAY` create Draft PR first, then mark ready when required by the flow.
- `MUST` preserve protected-branch governance; accelerated flow optimizes sequencing only.

## Worktree Decision Gate

Run this gate before branch creation.

### Required Inputs

- Current branch and default branch
- Working tree cleanliness
- Upstream divergence and sync risks
- `parallel_pressure` signal
- `branch_checked_out_elsewhere` signal (from git-sync analysis)
- Optional complexity/scope hint (single-file vs multi-module)

### Decision Rules

#### MUST use worktree (any one is true)

1. New work starts from default branch and local working tree has unrelated/unclassified changes.
2. `parallel_pressure == true`.
3. `branch_checked_out_elsewhere` detected (same branch checked out in another worktree/session).
4. `Enforcement Mode == hard` and work is a new feature or large refactor.

#### SHOULD use worktree (any one is true)

1. `Enforcement Mode == hybrid` and change scope is medium/high (multi-module or broad diff).
2. User explicitly requests isolated development.

#### MAY keep in-place (all are true)

1. Continuing iteration on a non-default branch with an existing PR.
2. Working tree is clean and no parallel conflict signals exist.
3. No high-risk gate is triggered.

### Idempotency Rules

1. If already inside target worktree, `MUST` reuse and skip creation.
2. If worktree for target branch already exists, `MUST` switch/reuse instead of creating duplicate.

### Delegation Boundary

When worktree mode is selected, invoke:

```text
Skill("using-git-worktrees", args="Set up isolated workspace for <branch-or-feature>")
```

`git-auto` owns *when* to use worktree.
`using-git-worktrees` owns directory selection, ignore verification, baseline setup, and readiness checks.

### Workspace Output Contract

Every generated execution plan `MUST` print:

- `Workspace Mode: <in-place|worktree>`
- `Worktree Decision Reason: <triggered rule(s)>`

## Analysis Process (Revised)

### 1. Session Preflight (Sync Node)

Run sync preflight before planning:

```bash
git fetch origin --prune
CURRENT_BRANCH=$(git branch --show-current)
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null || true)
BEHIND_AHEAD=$(git rev-list --left-right --count @{upstream}...HEAD 2>/dev/null || echo "0 0")

GIT_DIR=$(git rev-parse --absolute-git-dir)
test -e "$GIT_DIR/rebase-merge" -o -e "$GIT_DIR/rebase-apply" -o -e "$GIT_DIR/MERGE_HEAD" \
  -o -e "$GIT_DIR/CHERRY_PICK_HEAD" -o -e "$GIT_DIR/REVERT_HEAD" && echo "operation_in_progress"
```

Block plan execution when critical sync risks exist (detached HEAD, divergence, operation in progress).

### 2. Compute Enforcement Mode

Compute 14-day metrics and select mode (`soft|hybrid|hard`) with explicit reason.

### 3. Probe Repository Policy (Required)

When operating on the default branch (or considering direct-main), probe policy before branch-strategy selection.

Preferred command path (when `gh` is available and authenticated):

```bash
# gh commands require elevated execution in this environment
gh api repos/<owner>/<repo>/branches/$DEFAULT_BRANCH --jq '.protected'
```

If API data is unavailable, use conservative fallback (`unknown_conservative`) or evidence from a prior `GH006` rejection in the current session.

### 4. Worktree Decision Gate

Decide `Workspace Mode` and `Worktree Decision Reason` before branch/commit step execution.

### 5. Analyze Change Intent and Classify Risk

```bash
git diff --cached --name-only
git diff --name-only
git diff --shortstat
```

Produce:
- commit/branch naming category
- `Change Class`
- file count and line count
- `docs+ci_small` eligibility (yes/no + reason)

### 6. Resolve Branch Strategy

Select exactly one:

- `standard-pr` (default)
- `fast-pr` (eligible `docs+ci_small` on protected default branch)
- `direct-main-exception` (eligible `docs+ci_small`, mode/policy permit)

### 7. Generate Plan

Every plan `MUST` include policy + strategy fields (not just mode/worktree).

```
## Plan

Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days
Execution Intent: commit_push_pr
Repo Policy: protected_pr_required
Repo Policy Evidence: gh-api
Workspace Mode: in-place
Worktree Decision Reason: no high-risk trigger
Change Class: docs_ci_small
Changed Files: 2
Change Size: 34 insertions, 3 deletions
Branch Strategy: fast-pr
Strategy Reason: protected default branch + eligible docs/CI small change
Fallback on Push Rejection: if GH006, preserve commit and continue via short-lived branch + PR

1. Create or switch to short-lived branch (fast-pr lane)
2. Stage and commit changes
3. Push to remote
4. Create Draft PR (or ready PR if user requested)
5. If intent=`commit_push_pr_merge`, run checks and merge when gates pass

Confirm? (y/n)
```

## Decision Tree (Policy-Aware)

```
SYNC PREFLIGHT -> MODE -> REPO POLICY PROBE -> WORKTREE GATE -> CHANGE CLASSIFIER
      |
      v
Any changes? --no--> Finish ("Nothing to do")
      |
     yes
      |
On default branch?
  |               \
 yes               no
  |                 \
  v                  Commit -> Push -> Update/Create PR
Resolve Branch Strategy
  |
  +--> Repo protected OR unknown_conservative?
  |        |
  |        +--> docs+ci_small eligible? --> yes: fast-pr
  |        |                                 no: standard-pr
  |        |
  |        +--> (never direct-main on protected policy)
  |
  +--> Repo unprotected
           |
           +--> docs+ci_small eligible AND mode permits? --> direct-main-exception
           |                                              (push main)
           |                                                  |
           |                                                  +--> GH006? -> fallback to short-lived branch + PR
           |
           +--> otherwise -> standard-pr
```

## Execution Flow

### Step 1: Present Plan

```
## Execution Plan

Enforcement Mode: soft
Escalation Reason: no threshold trigger in last 14 days
Execution Intent: commit_push_pr
Repo Policy: protected_pr_required
Repo Policy Evidence: gh-api
Workspace Mode: in-place
Worktree Decision Reason: no high-risk trigger
Change Class: docs_ci_small
Branch Strategy: fast-pr
Strategy Reason: docs+CI small change on protected main

1. Create/switch branch docs/update-readme-links
2. Stage and commit changes
3. Push to remote
4. Create Draft PR
5. Stop for review/checks unless user explicitly requested merge

Execute this plan? [y/n]
```

### Step 2: Confirmation Gate (Autorun Exception)

- Default: do not execute until user confirms.
- Autorun exception: if `Lightweight Autorun` eligibility is satisfied and intent includes push/PR, `git-auto` `MUST` proceed automatically through the autorun scope.
- If the user explicitly asks for a plan/preview/manual confirmation, `MUST` disable autorun for that run.

### Step 3: Execute Operations

- When `Workspace Mode=worktree`, call `using-git-worktrees` first.
- When `Branch Strategy=direct-main-exception`, commit on `main` only after policy/mode eligibility checks pass.
- If direct-main push fails with `GH006`, preserve the local commit, create/switch to a short-lived branch, and continue via PR.
- When `Execution Intent=commit_push_pr_merge`, continue through PR checks and merge only if merge gates pass; otherwise stop with a blocker summary and PR state.
- When `Execution Mode=autorun` and `Branch Strategy=fast-pr`, continue automatically through `push + Draft PR` unless a step fails.

### Step 4: Accelerated PR Closeout (Optional)

Only for `Execution Intent=commit_push_pr_merge`.

Preferred command sequence (subject to repo policy and approvals):

```bash
# gh commands require elevated execution in this environment
gh pr create [--draft|--fill|--title ... --body ...]
gh pr checks <pr-number>
gh pr ready <pr-number>          # if draft must be promoted
gh pr merge <pr-number> --squash --delete-branch
```

If merge is blocked by required checks/reviews, stop and report:

- PR URL/number
- blocking checks/reviews
- retry path (`gh pr checks`, fix, push, re-check, merge)

## Scenarios

### Scenario A: `main + dirty` (must use worktree)

```
Enforcement Mode: soft
Workspace Mode: worktree
Worktree Decision Reason: MUST rule #1 (default branch start + unrelated local changes)
Branch Strategy: standard-pr

Action: call using-git-worktrees, then create branch and PR.
```

### Scenario B: active feature branch + open PR + clean (in-place)

```
Enforcement Mode: soft
Workspace Mode: in-place
Worktree Decision Reason: MAY rule satisfied (existing feature PR iteration)
Branch Strategy: standard-pr

Action: commit + push, update existing PR.
```

### Scenario C: protected `main` + eligible docs/CI small change

```
Repo Policy: protected_pr_required
Change Class: docs_ci_small
Branch Strategy: fast-pr

Action: create short-lived docs/ci branch, push, create PR (fast lane).
```

### Scenario C2: protected `main` + eligible docs/CI small change + push/PR intent (autorun)

```
Execution Intent: commit_push_pr
Repo Policy: protected_pr_required
Repo Policy Evidence: local-config (GitHub ruleset JSON) or gh-api
Change Class: docs_ci_small
Branch Strategy: fast-pr
Execution Mode: autorun
Autorun Scope: through push + draft-pr

Action: auto-create branch -> commit -> push -> create Draft PR without extra confirmation.
```

### Scenario D: unprotected `main` + eligible docs/CI small change in `soft`

```
Repo Policy: unprotected
Enforcement Mode: soft
Change Class: docs_ci_small
Branch Strategy: direct-main-exception

Action: commit on main, push main directly.
```

### Scenario E: direct-main attempt rejected with `GH006`

```
Push rejected: GH006 protected branch update failed
Action: keep local commit, create short-lived branch from current HEAD, push branch, create PR.
```

### Scenario F: `branch_checked_out_elsewhere` detected

```
Enforcement Mode: hybrid
Workspace Mode: worktree
Worktree Decision Reason: MUST rule #3 (branch_checked_out_elsewhere)

Action: isolate work in separate worktree to avoid concurrent branch writes.
```

### Scenario G: hard + new feature start

```
Enforcement Mode: hard
Workspace Mode: worktree
Worktree Decision Reason: MUST rule #4 (hard mode + new feature/large refactor)
Branch Strategy: standard-pr
```

### Scenario H: user says "push this quick fix and merge it"

```
Execution Intent: commit_push_pr_merge
Repo Policy: protected_pr_required
Branch Strategy: fast-pr (if eligible) or standard-pr

Action: commit -> push branch -> create PR -> run checks -> merge when gates pass.
If blocked, stop with PR link + blocker summary.
```

## Return Values

- **Success**: Summary of executed operations with results
- **No changes**: Notify user and suggest next action
- **Cancelled**: User cancelled execution
- **Error**: Specific error with recovery suggestion

## Error Handling

### Worktree directory not ignored

```
Worktree directory is not ignored.
Plan:
1. add ignore rule (.worktrees/ or worktrees/)
2. commit ignore fix
3. continue worktree creation
```

### Worktree branch conflict

```
Target branch already has an existing worktree.
Plan: switch/reuse existing worktree path instead of creating duplicate.
```

### Duplicate worktree request

```
Current workspace already matches target worktree.
Plan: reuse current workspace and continue.
```

### Push rejected

```
Push rejected (remote has changes).
Plan:
1. git fetch origin
2. git rebase @{upstream}
3. re-evaluate enforcement/worktree decisions
4. retry push
```

### Push rejected (`GH006` protected branch)

```
Push rejected: GH006 protected branch update failed
Plan:
1. Preserve local commit(s) on current HEAD (do not reset)
2. Create or switch to short-lived branch from current HEAD
3. Push branch to origin
4. Create Draft PR (or ready PR if user requested)
5. Record repo policy evidence = push-error-gh006 for subsequent runs
```

### PR creation failed

```
PR creation failed: draft PR already exists.
Plan: update existing draft PR.
```

### PR checks pending/failed (accelerated closeout)

```
PR checks not green (pending/failed).
Plan:
1. Report PR URL and failing/pending checks
2. Do not merge
3. Offer retry path (re-check after fixes)
```

### Mode escalation during current run

```
Enforcement mode changed during execution: soft -> hybrid
Plan adjustment: keep PR draft/review-ready and enforce stricter merge gates.
```

## Merge Gate Summary

Before any merge recommendation, run pre-merge sync check and mode gates:

1. Sync gate (all modes): no detached HEAD, no operation in progress, not behind, not diverged.
2. `soft`: sync gate required.
3. `hybrid`: sync gate + passing CI + review-ready signal.
4. `hard`: sync gate + passing CI + required approvals + no blocking discussion.

Default merge recommendation:
- `SHOULD` recommend squash merge when all gates pass.

When `Execution Intent=commit_push_pr_merge` and all gates pass:
- `MAY` execute squash merge directly after explicit user confirmation of the generated plan.

## Assumptions and Defaults

1. Rolling window is fixed at 14 days.
2. Escalation is progressive (`soft -> hybrid -> hard`) and de-escalates with clean windows.
3. `Repo Policy` probing may rely on `gh api` (preferred), observed push errors, or conservative fallback when metadata is unavailable.
4. Fast PR Lane optimizes speed by reducing branch/PR friction, not by bypassing protected-branch governance.
5. This is policy-first guidance and does not require immediate hook-level hard blocking.
6. In this environment, `gh` commands typically require elevated execution (auth/keychain access); PR/check/merge steps should note this in the execution plan.
