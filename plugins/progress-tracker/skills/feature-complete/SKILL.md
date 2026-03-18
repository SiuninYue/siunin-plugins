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
   - If `ProjectRoot` is present: use it as the working directory for all `prog` commands.

2. If `Worktree` is present: **switch to it immediately**:
   ```bash
   cd <worktree_path>
   ```
   If `cd` fails, warn and stop.

3. If `Branch` is present: verify and switch if needed:
   ```bash
   git checkout <branch>
   ```

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
plugins/progress-tracker/prog validate-plan
```

- If validation fails: stop completion and request plan recovery.

### Step 4: Run Acceptance Verification

Use `feature.test_steps` as source of truth.

- Execute command-based checks where possible.
- For manual checks, collect explicit pass/fail evidence.
- Keep output concise but audit-friendly.

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
      args="git auto done — feature <feature_id> closeout, autorun authorized, intent: commit_push_pr")
```

   Parse the Execution Result Block (`=== Git Auto Result ===` … `=== End Result ===`):
   - `Status: ok` → extract `CommitHash`, continue to step 5
   - `Status: blocked` → display `BlockReason`, STOP — wait for user to resolve, then re-run `/prog done`
   - GH006 fallback is handled internally by git-auto; still yields `Status: ok` + real `CommitHash`

5. Mark feature complete using the `CommitHash` extracted in step 4:

```bash
plugins/progress-tracker/prog complete <feature_id> --commit <CommitHash_from_step4>
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
plugins/progress-tracker/prog memory append --payload-json '<capability_json>'
```

Legacy CLI equivalent: `project_memory.py append`.

- If this command fails:
  - print a warning
  - do not roll back feature completion
  - continue remaining completion steps

7. Finalize AI metrics:

```bash
plugins/progress-tracker/prog complete-feature-ai-metrics <feature_id>
```

8. Clear workflow state:

```bash
plugins/progress-tracker/prog clear-workflow-state
```

9. Show next step and output a Context Handoff Block:

If pending features remain, output:
```
---
**Paste into a new session to start the next feature:**

/progress-tracker:prog-next

Project: <done>/<total> features done | F<feature_id> "<feature_name>" ✓ just completed
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-selects and starts next pending feature.
---
```

If all features are complete: output project completion summary instead (no handoff block needed).

10. If all features are complete, first detect whether current branch already has a PR:

```bash
CURRENT_BRANCH=$(git branch --show-current)
EXISTING_PR_URL=$(gh pr list --head "$CURRENT_BRANCH" --json url --jq '.[0].url' 2>/dev/null || true)
```

11. Apply duplicate-finish guard:

- If `EXISTING_PR_URL` is non-empty and not `null`:
  - report existing PR URL
  - skip branch finishing flow automatically (avoid duplicate PR/cleanup actions)
- Only invoke `finishing-a-development-branch` when **both** conditions are true:
  1. No existing PR found
  2. The handoff block that triggered this run explicitly contains `Intent: commit_push_pr_merge`
- For normal `/prog done` runs (standard `commit_push_pr` intent from git-auto), do NOT invoke `finishing-a-development-branch` — git-auto's commit + push + PR is sufficient.

```text
Skill("superpowers:finishing-a-development-branch", args="Complete branch integration after progress-tracker project completion")
```

#### Fail Path

- Keep feature in progress.
- Provide failed checks, observed symptoms, and immediate remediation path.
- Recommend `/prog-fix "<issue>"` when failure is bug-like.

### Step 6: Optional Quality and Debt Capture

If project defines `quality_gates.pre_commit_checks`, run them before completion.

If user identifies technical debt during verification, record it in bug system:

```bash
plugins/progress-tracker/prog add-bug \
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

- Message: unable to detect PR status (e.g. `gh` unavailable or unauthenticated).
- Next action: do not auto-run branch finishing; ask user whether to proceed manually.

- Workflow Context Mismatch (warning path):
  - Message: current session branch/worktree differs from recorded execution context.
  - Next action: switch to recorded context, then rerun `/prog done`; if user confirms verification was done in current context, continue manually.

## Required Output Shape

Always include:

1. Feature ID and name
2. Verification summary (pass/fail per test step)
3. Progress update result
4. Context Handoff Block (see Step 9 template above)

For full examples of pass/fail conversations, read `references/session-examples.md`.
