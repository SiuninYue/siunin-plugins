---
name: feature-complete
description: This skill should be used when the user asks to "/prog done", "complete feature", "mark feature as done", "finish implementation", or runs the prog-done command. Handles feature verification, progress tracking updates, and Git commits.
model: sonnet
references:
  - "testing-standards"
  - "superpowers:requesting-code-review"
  - "superpowers:verification-before-completion"
  - "superpowers:finishing-a-development-branch"
  - "./references/verification-playbook.md"
  - "./references/session-examples.md"
---

# Feature Completion Skill

Finalize the active feature only after verification passes, then update tracking state and Git metadata.

## Inline Context Fast Path

**Check this FIRST before any other step.**

If the invocation includes inline context lines (`Feature:`, `Phase:`, `Plan:`, `Branch:`, `Worktree:`, `ProjectRoot:`), treat them as pre-loaded state:

1. Parse inline context: `feature_id`, `feature_name`, `plan_path`, `branch`, `worktree_path`, `project_root`.
   - If `ProjectRoot` is present: pass `--project-root <project_root>` to **every** `prog` CLI call below.

2. If `Worktree` is present: **store `worktree_path` as the execution root for all acceptance test commands**.

   > **Claude Code — CWD does NOT persist between Bash tool calls.**  
   > A standalone `cd <worktree_path>` affects only that single call and has no effect on subsequent calls.  
   > Do NOT use a bare `cd` to set context.  
   > Instead, prefix **every** acceptance test shell command in Step 4 with:  
   > `cd <worktree_path> && <command>`

   Verify the path is accessible before proceeding:
   ```bash
   ls <worktree_path>
   ```
   If the path is inaccessible, warn and stop.

3. If `Branch` is present: verify the checked-out branch matches.
   - If `worktree_path` is present:
     ```bash
     cd <worktree_path> && git branch --show-current
     ```
   - If `worktree_path` is absent (in-place session):
     ```bash
     git branch --show-current
     ```
   If branch doesn't match, **auto-switch** with a safety check:
   ```bash
   git status --porcelain
   ```
   - **Working tree clean** → run `git switch <branch>` and continue.
   - **Uncommitted changes** → STOP: warn the user that switching would discard or lose changes, ask them to commit or stash first.

4. **Skip** Step 1 (load active feature from file) and Step 2 (validate workflow state from file) — trust the inline `Phase: execution_complete`.

5. Proceed directly to Step 3 (validate plan contract) using the inline `Plan` path.

**The inline context is the source of truth.**

---

## Core Responsibilities

1. Validate that workflow execution actually completed.
2. Run acceptance verification from feature test steps.
3. Record failures and keep feature open when verification fails.
4. Mark feature complete only after passing checks.
5. Clear workflow state and finalize AI metrics.

## Use This Skill For

- `/prog done`
- Requests to mark the current feature complete
- End-of-feature verification and commit handoff

## Main Flow

### Step 0: Preflight Check (RECOMMENDED)

**ALWAYS run this first.** It validates all gates in a single pass and reports every blocking issue at once, avoiding the frustrating fix-one-gate-at-a-time loop.

```bash
plugins/progress-tracker/prog --project-root <project_root> done --check
```

This runs all validation gates (preconditions, reconcile, plan document, sprint ledger, acceptance tests, evaluator, reviews, ship check) in batch mode and reports ALL results at once. Acceptance tests are executed but state is NOT persisted (no finish_pending written, no report saved to disk).

**Exit codes:**
- `0` = all gates pass. Proceed to Step 1 for the full flow. (Acceptance tests already passed during preflight; evaluator subagent still needs to run in Step 4.5.)
- Non-zero = some gates FAILED. Fix ALL reported issues, then re-run `prog done --check`.

### Step 1: Load Active Feature

Read `docs/progress-tracker/state/progress.json` and locate `current_feature_id`.

- If no active feature: stop and guide user to `/prog next`.
- If feature already completed: show status and stop.

### Step 2: Validate Workflow State

Inspect 顶层 `workflow_state.phase`（不要读 `features[n].workflow_state`）。

- Required phase: `execution_complete`.
- If not `execution_complete`, do not complete feature.
- Also inspect execution/runtime context alignment from `docs/progress-tracker/state/progress.json` (or `check` output):
  - If branch mismatches, auto-switch with safety check: `git status --porcelain` → if clean, `git switch <expected_branch>`; if dirty, warn and stop.
  - Do not silently mutate progress state to "fix" mismatch.

Return an actionable message:

- current phase value
- what is missing
- context mismatch details (if any)
- how to continue (`/prog`, `/prog next`, or recovery)

### Step 3: Validate Plan Contract

Before running acceptance, validate plan path and required sections:

```bash
plugins/progress-tracker/prog --project-root <project_root> validate-plan
```

- If validation fails: stop completion and request plan recovery.

### Step 4: Run Acceptance Verification

Use `feature.test_steps` as source of truth.

- Execute command-based checks where possible.
- For manual checks, collect explicit pass/fail evidence.
- Keep output concise but audit-friendly.
- **If `worktree_path` is set (from inline context):** prefix every shell command with `cd <worktree_path> && ` so it runs in the correct branch directory.  
  Example: `cd /path/to/worktree && pytest tests/`

If user provides acceptance notes or test docs, format/report via `testing-standards`.

Detailed checklists and output templates are in `references/verification-playbook.md`.

Before claiming pass, invoke:

```text
Skill("superpowers:verification-before-completion", args="Verify acceptance evidence for feature <feature_id>")
```

### Step 4.5: Run Evaluator Gate in a Fresh Subagent (PR-3, ADR-009)

**BEFORE calling `prog done`, dispatch a NEW subagent** to run the evaluator gate independently.

```text
Agent(
  subagent_type="superpowers:code-reviewer",   // or "superpowers:security-auditor" for security-sensitive features
  prompt="Run evaluator_gate.assess() for feature <feature_id>. "
         "Read quality rubric from feature.acceptance_scenarios and test_steps. "
         "Collect signals: test_coverage from pytest --cov output, defects from code review. "
         "Persist result via progress_manager._store_evaluator_result(feature_id, result). "
         "Pass evaluator_model=<model_id_used>. "
         "Report status (pass/retry/required_reviews), score, and defect list."
)
```

**Isolation requirement (ADR-009):** The evaluator subagent MUST run in a separate context from the generator that produced the feature code. Do not call `assess()` in the same session that ran the implementation — this defeats the generator/evaluator separation discipline.

**Gate rule:**
- `status == "pass"` → proceed to Step 5
- `status == "retry"` → fix blocking defects, re-run evaluator subagent, do NOT call `prog done`
- `status == "required_reviews"` → escalate to human review lane, do NOT call `prog done`

If `quality_gates.evaluator.status != "pass"` when `prog done` is invoked, the CLI will exit with code 6 and block archiving.

### Step 5: Handle Verification Result

#### Pass Path

1. Confirm all required checks passed (acceptance + evaluator gate).
2. Run final code review if none was recorded during implementation:

```text
Skill("superpowers:requesting-code-review", args="Final review before marking feature <feature_id> complete")
```

3. Ensure no unresolved Critical/Important review findings remain.
4. Record lane-specific review evidence (CLI `--evidence` is optional but this skill path treats it as required):

```bash
# eng lane: code review artifact
plugins/progress-tracker/prog --project-root <project_root> review-pass \
  --feature-id <feature_id> --lane eng \
  --evidence "<code_review_artifact_path_or_summary>"

# qa lane: pre-done acceptance evidence
plugins/progress-tracker/prog --project-root <project_root> review-pass \
  --feature-id <feature_id> --lane qa \
  --evidence "<acceptance_log_or_manual_verification_summary>"

# docs lane: plan/documentation evidence
plugins/progress-tracker/prog --project-root <project_root> review-pass \
  --feature-id <feature_id> --lane docs \
  --evidence "<plan_path_or_docs_sync_note>"
```

If required lanes include `design` or `devex`, also record them with dedicated evidence.

5. Run ship-check before final closeout:

```bash
plugins/progress-tracker/prog --project-root <project_root> ship-check --feature-id <feature_id>
```

6. Automatically run git closeout (no user confirmation needed):

```text
Skill("progress-tracker:git-auto",
      args="git auto done — feature <feature_id> closeout, autorun authorized, intent: commit_push_pr_merge")
```

   Parse the Execution Result Block (`=== Git Auto Result ===` … `=== End Result ===`):
   - `Status: ok` → extract `CommitHash`, continue to step 7
   - `Status: blocked` → display `BlockReason`, STOP — wait for user to resolve, then re-run `/prog done`
   - GH006 fallback is handled internally by git-auto; still yields `Status: ok` + real `CommitHash`

   **Squash merge verification (不可跳过):**
   - `git-auto done` MUST use squash merge (`gh pr merge --squash --delete-branch`).
   - `CommitHash` MUST be the squash commit on the default branch, NOT the feature branch HEAD.
   - Verify: after receiving `Status: ok`, confirm `CommitHash` equals `git rev-parse origin/<default_branch>`.
   - Feature branch should be deleted (remote via `--delete-branch`, local via `git branch -D`); branch cleanup failure is non-blocking.

7. Invoke deterministic done gate with the extracted commit hash:

```bash
plugins/progress-tracker/prog --project-root <project_root> done --commit <CommitHash_from_step6>
```

`prog done` now owns finalize I/O ordering and post-finalize side effects (audit/archive/memory/reset).
After marking the feature complete, `prog done` internally calls `project_memory.py append` to record a capability memory entry for this feature. If the memory append or archive step fails, do not roll back feature completion — those side-effects are non-fatal and the feature remains marked as complete.

8. Show next step and output a Context Handoff Block:

Before outputting, read `docs/progress-tracker/state/progress.json` to find:
- `project_name`
- count of `completed == true` features and `total` features
- the **first** feature with `completed == false` (next feature: its `id` and `name`)
- the absolute project root path (from `runtime_context.tracker_root` or resolve from CWD)

If pending features remain, output this exact block (fill in all placeholders from live data):

```
---
**粘贴到新会话以启动下一个功能：**

/progress-tracker:prog-next

  Project: <project_name> | <done>/<total> completed
  Feature: F<next_id> "<next_name>"
  ProjectRoot: <abs_project_root>
  → Context pre-loaded. Auto-selects and starts next pending feature.
---
```

Also show the next feature's `test_steps` as a preview so the user knows what's coming:

```
**下一个功能预览：**
- ID: F<next_id>
- Name: <next_name>
- Test steps:
  1. <step1>
  2. <step2>
  ...
```

If all features are complete: output project completion summary instead (no handoff block needed).

9. Merge-first closeout policy:

- `/prog done` defaults to `commit_push_pr_merge`.
- `git-auto` is the single authority for merge gating and execution.
- Do NOT invoke `finishing-a-development-branch` automatically inside normal `/prog done` flow; this avoids duplicate closeout decisions and worktree/main drift.
- Only invoke `finishing-a-development-branch` when the user explicitly requests a manual integration path after `/prog done`.

#### Fail Path

- Keep feature in progress.
- Provide failed checks, observed symptoms, and immediate remediation path.
- Recommend `/progress-tracker:prog-fix "<issue>"` when failure is bug-like.

### Step 6: Optional Quality and Debt Capture

If project defines `quality_gates.pre_commit_checks`, run them before completion.

If user identifies technical debt during verification, record it in bug system:

```bash
plugins/progress-tracker/prog --project-root <project_root> add-bug \
  --description "<technical debt item>" \
  --status pending_investigation \
  --priority medium \
  --category technical_debt
```

## Error Handling

### No Current Feature

- Message: no in-progress feature exists.
- Next action: `/prog next`.

### Plan Validation Failed

- Message: plan path invalid/missing, or mandatory plan structure missing (`Tasks`; plus either strict sections or Superpowers header fields).
- Next action: rebuild plan, then rerun `/prog done`.

### Git Commit Not Available

- Message: completion requires a commit hash.
- Next action: commit fix, rerun completion.

### Git Auto Closeout Blocked

- Trigger: `Status: blocked` in Execution Result Block from `git-auto`.
- Message: display `BlockReason` from result block; do not mark feature complete.
- Next action: user resolves blocker (e.g., merge conflict, auth error), then re-runs `/prog done`.
- Feature remains open until `Status: ok` is received.

### PR Detection Unavailable

- Message: `git-auto` could not complete merge-first closeout due to missing PR/gh context.
- Next action: keep feature open, surface blocker details, and ask user whether to proceed with manual integration.

- Workflow Context Mismatch (auto-recovery path):
  - Message: current session branch/worktree differs from recorded execution context.
  - Auto-switch: `git status --porcelain` → if clean, `git switch <expected_branch>`; if dirty, warn and stop.
  - After switching, continue `/prog done` normally.

## Required Output Shape

Always include:

1. Feature ID and name
2. Verification summary (pass/fail per test step)
3. Progress update result
4. Context Handoff Block (next feature or project complete):

**If pending features remain:**
```text
/progress-tracker:prog-next

Project: <done>/<total> features done | F<feature_id> "<feature_name>" ✓ just completed
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-selects and starts next pending feature.
```

**If ALL features complete:** Output project completion summary instead (no handoff block).

For full examples of pass/fail conversations, read `references/session-examples.md`.
