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

### Step 5: Handle Verification Result

#### Pass Path

1. Confirm all required checks passed.
2. Ensure code is committed (either existing commit hash or create commit).
3. Mark feature complete:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete <feature_id> --commit <commit_hash>
```

4. Finalize AI metrics:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py complete-feature-ai-metrics <feature_id>
```

5. Clear workflow state:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py clear-workflow-state
```

6. Show next step:
- `/prog next` when pending features remain
- project complete summary when all features are done

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

- Message: plan path invalid/missing or required sections missing.
- Next action: rebuild plan, then rerun `/prog done`.

### Git Commit Not Available

- Message: completion requires a commit hash.
- Next action: commit fix, rerun completion.

## Required Output Shape

Always include:

1. Feature ID and name
2. Verification summary (pass/fail per test step)
3. Progress update result
4. Next command recommendation

For full examples of pass/fail conversations, read `references/session-examples.md`.
