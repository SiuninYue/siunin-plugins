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
  - "requesting-code-review"
  - "verification-before-completion"
  - "finishing-a-development-branch"
  - "./references/verification-playbook.md"
  - "./references/session-examples.md"
---

# Feature Completion Skill

Finalize the active feature only after verification passes, then update tracking state and Git metadata.

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

Read `.claude/progress.json` and locate `current_feature_id`.

- If no active feature: stop and guide user to `/prog next`.
- If feature already completed: show status and stop.

### Step 2: Validate Workflow State

Inspect `workflow_state.phase`.

- Required phase: `execution_complete`.
- If not `execution_complete`, do not complete feature.

Return an actionable message:

- current phase value
- what is missing
- how to continue (`/prog`, `/prog next`, or recovery)

### Step 3: Validate Plan Contract

Before running acceptance, validate plan path and required sections:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py validate-plan
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
Skill("verification-before-completion", args="Verify acceptance evidence for feature <feature_id>")
```

### Step 5: Handle Verification Result

#### Pass Path

1. Confirm all required checks passed.
2. Run final code review if none was recorded during implementation:

```text
Skill("requesting-code-review", args="Final review before marking feature <feature_id> complete")
```

3. Ensure no unresolved Critical/Important review findings remain.
4. Ensure code is committed (either existing commit hash or create commit).
5. Mark feature complete:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <commit_hash>
```

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
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py append --payload-json '<capability_json>'
```

- If this command fails:
  - print a warning
  - do not roll back feature completion
  - continue remaining completion steps

7. Finalize AI metrics:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete-feature-ai-metrics <feature_id>
```

8. Clear workflow state:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
```

9. Show next step:
- `/prog next` when pending features remain
- project complete summary when all features are done

10. If all features are complete, first detect whether current branch already has a PR:

```bash
CURRENT_BRANCH=$(git branch --show-current)
EXISTING_PR_URL=$(gh pr list --head "$CURRENT_BRANCH" --json url --jq '.[0].url' 2>/dev/null || true)
```

11. Apply duplicate-finish guard:

- If `EXISTING_PR_URL` is non-empty and not `null`:
  - report existing PR URL
  - skip branch finishing flow automatically (avoid duplicate PR/cleanup actions)
- If no existing PR and user wants immediate integration/cleanup, invoke:

```text
Skill("finishing-a-development-branch", args="Complete branch integration after progress-tracker project completion")
```

#### Fail Path

- Keep feature in progress.
- Provide failed checks, observed symptoms, and immediate remediation path.
- Recommend `/prog-fix "<issue>"` when failure is bug-like.

### Step 6: Optional Quality and Debt Capture

If project defines `quality_gates.pre_commit_checks`, run them before completion.

If user identifies technical debt during verification, record it in bug system:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py add-bug \
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

### PR Detection Unavailable

- Message: unable to detect PR status (e.g. `gh` unavailable or unauthenticated).
- Next action: do not auto-run branch finishing; ask user whether to proceed manually.

## Required Output Shape

Always include:

1. Feature ID and name
2. Verification summary (pass/fail per test step)
3. Progress update result
4. Next command recommendation

For full examples of pass/fail conversations, read `references/session-examples.md`.
