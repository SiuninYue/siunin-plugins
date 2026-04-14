---
name: feature-complete
description: This skill should be used when the user asks to "/prog done", "complete feature", "mark feature as done", "finish implementation", or runs the prog-done command. Handles feature verification, progress tracking updates, and Git commits.
model: sonnet
version: "2.2.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
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

3. If `Branch` is present: verify the checked-out branch matches (do not switch — worktrees are already on a specific branch):
   ```bash
   cd <worktree_path> && git branch --show-current
   ```
   If branch doesn't match, warn the user but continue; do not run `git checkout`.

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

### Step 1: Load Active Feature

Read `docs/progress-tracker/state/progress.json` and locate `current_feature_id`.

- If no active feature: stop and guide user to `/prog next`.
- If feature already completed: show status and stop.

### Step 2: Validate Workflow State

Inspect `workflow_state.phase`.

- Required phase: `execution_complete`.
- If not `execution_complete`, do not complete feature.
- Also inspect execution/runtime context alignment from `docs/progress-tracker/state/progress.json` (or `check` output):
  - If worktree/branch mismatches the recorded execution context, show a strong warning and ask user to switch first.
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

### Step 5: Handle Verification Result

#### Pass Path

1. Confirm all required checks passed.
2. Run final code review if none was recorded during implementation:

```text
Skill("superpowers:requesting-code-review", args="Final review before marking feature <feature_id> complete")
```

3. Ensure no unresolved Critical/Important review findings remain.
4. Automatically run git closeout (no user confirmation needed):

```text
Skill("progress-tracker:git-auto",
      args="git auto done — feature <feature_id> closeout, autorun authorized, intent: commit_push_pr_merge")
```

   Parse the Execution Result Block (`=== Git Auto Result ===` … `=== End Result ===`):
   - `Status: ok` → extract `CommitHash`, continue to step 5
   - `Status: blocked` → display `BlockReason`, STOP — wait for user to resolve, then re-run `/prog done`
   - GH006 fallback is handled internally by git-auto; still yields `Status: ok` + real `CommitHash`

5. Mark feature complete using the `CommitHash` extracted in step 4:

```bash
plugins/progress-tracker/prog --project-root <project_root> complete <feature_id> --commit <CommitHash_from_step4>
```

This step will automatically:
- Move associated plan and test documents to `docs/progress-tracker/archive/`
- Rename archived plans to `feature-{id}-{original-name}.md` for consistency
- Support both legacy (`feature-N-*.md`) and current date-based naming patterns (`YYYY-MM-DD-*.md`)

6. Append capability memory (non-blocking):

- Build one capability payload from the completed feature:
  - `title`: feature name
  - `summary`: concise completion summary
  - `tags`: optional feature tags
  - `confidence`: `1.0`
  - `source.origin`: `prog_done`
  - `source.feature_id`: current feature ID
  - `source.commit_hash`: completion commit hash
- Persist via:

```bash
plugins/progress-tracker/prog --project-root <project_root> memory append --payload-json '<capability_json>'
```

Legacy CLI equivalent: `project_memory.py append`.

- If this command fails:
  - print a warning
  - do not roll back feature completion
  - continue remaining completion steps

7. Finalize AI metrics:

```bash
plugins/progress-tracker/prog --project-root <project_root> complete-feature-ai-metrics <feature_id>
```

8. Clear workflow state:

```bash
plugins/progress-tracker/prog --project-root <project_root> clear-workflow-state
```

9. Show next step and output a Context Handoff Block:

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

10. Merge-first closeout policy:

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

- Workflow Context Mismatch (warning path):
  - Message: current session branch/worktree differs from recorded execution context.
  - Next action: switch to recorded context, then rerun `/prog done`; if user confirms verification was done in current context, continue manually.

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
