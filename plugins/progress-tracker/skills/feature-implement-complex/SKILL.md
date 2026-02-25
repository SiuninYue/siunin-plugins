---
name: feature-implement-complex
description: This skill should be used when feature complexity is complex (score 26-40) and the coordinator delegates architecture-heavy or multi-file implementation. Executes brainstorming, planning, and subagent-driven execution with opus and updates workflow and AI metrics.
model: opus
version: "1.1.0"
scope: skill
user-invocable: false
inputs:
  - feature_id
  - feature_name
  - feature test steps
  - complexity_score
outputs:
  - design plan and execution summary
  - workflow state update
  - ai_metrics update
evidence: optional
references:
  - "brainstorming"
  - "using-git-worktrees"
  - "writing-plans"
  - "subagent-driven-development"
  - "requesting-code-review"
  - "verification-before-completion"
---

# Purpose

Execute high-complexity features with full design, planning, and implementation phases.

# Inputs

- `feature_id`
- `feature_name`
- `test_steps`
- `complexity_score` (26-40)

# Outputs

- Design exploration result
- Implementation plan path
- Execution completed status
- Feature AI metrics with `selected_model = opus`

# State Read/Write

Read:
- `.claude/progress.json`
- `.claude/architecture.md` (if present)

Write:
- `.claude/progress.json` via `progress_manager.py`

# Steps

1. Validate complexity bucket is `complex`.
2. Display complex-mode banner and rationale.
3. Ensure workspace isolation for large refactors:

```text
Skill("using-git-worktrees", args="Set up isolated workspace for feature-<id>")
```

4. Run design phase:

```text
Skill("brainstorming", args="<feature_name>: architecture and approach")
```

If `.claude/architecture.md` exists, include `Execution Constraints` (`CONSTRAINT-*`) in brainstorming context.

5. Update workflow to design complete:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "design_complete" \
  --next-action "planning"
```

6. Run planning phase:

```text
Skill("writing-plans", args="<feature_name>: create implementation plan\nArchitecture constraints:\n- <CONSTRAINT-...>\nPlan path policy: must output under docs/plans/feature-<id>-<slug>.md")
```

7. Update workflow to planning complete with plan path:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "planning_complete" \
  --plan-path "<returned_plan_path>" \
  --next-action "execution"
```

8. Run execution phase:

```text
Skill("subagent-driven-development", args="plan:<returned_plan_path>")
```

9. Run final review + verification gates:

```text
Skill("requesting-code-review", args="Review complex feature implementation: <feature_name>")
Skill("verification-before-completion", args="Verify complex feature evidence for <feature_name>")
```

10. Mark workflow as execution complete and save AI metrics:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "execution_complete" \
  --next-action "verify_and_complete"

python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> \
  --complexity-score <score> \
  --selected-model opus \
  --workflow-path full_design_plan_execute
```

11. Ask user to run `/prog done`.

Compatibility rule:
- Do not perform branch finalization here.
- This skill prepares implementation for `/prog done`, which owns feature completion.

## Plan Path Policy (Required)

`set-workflow-state --plan-path` must only store `docs/plans/*.md`.
If returned path is invalid or missing, regenerate the plan before execution.

# Failure Modes

- If any phase fails, preserve the latest workflow state and return clear recovery guidance.
- Do not mark feature complete here.

# Commands

- `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state ...`
- `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics ...`

# Examples

- Auth system refactor (OAuth2 + JWT)
- Multi-module integration
- Core architecture redesign
