---
name: feature-implement-complex
description: This skill should be used when feature complexity is complex (score 26-40) and the coordinator delegates architecture-heavy or multi-file implementation. Executes brainstorming, planning, and subagent-driven execution with opus and updates workflow and AI metrics.
model: opus
version: "1.0.0"
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
references: ["superpowers:brainstorming", "superpowers:writing-plans", "superpowers:subagent-driven-development"]
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
3. Run design phase:

```text
Skill("superpowers:brainstorming", args="<feature_name>: architecture and approach")
```

4. Update workflow to design complete:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "design_complete" \
  --next-action "planning"
```

5. Run planning phase:

```text
Skill("superpowers:writing-plans", args="<feature_name>: create implementation plan")
```

6. Update workflow to planning complete with plan path:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "planning_complete" \
  --plan-path "<returned_plan_path>" \
  --next-action "execution"
```

7. Run execution phase:

```text
Skill("superpowers:subagent-driven-development", args="plan:<returned_plan_path>")
```

8. Mark workflow as execution complete and save AI metrics:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "execution_complete" \
  --next-action "verify_and_complete"

python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> \
  --complexity-score <score> \
  --selected-model opus \
  --workflow-path full_design_plan_execute
```

9. Ask user to run `/prog done`.

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
