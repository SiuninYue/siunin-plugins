---
name: feature-implement-simple
description: This skill should be used when feature complexity is simple (score 0-15) and the coordinator delegates low-risk tasks such as single-file changes, clear requirements, and limited test steps. Executes direct TDD with haiku and updates workflow and AI metrics.
model: haiku
version: "1.0.0"
scope: skill
user-invocable: false
inputs:
  - feature_id
  - feature_name
  - feature test steps
  - complexity_score
outputs:
  - direct_tdd execution summary
  - workflow state update
  - ai_metrics update
evidence: optional
references: ["test-driven-development"]
---

# Purpose

Execute low-complexity features quickly with a direct TDD flow.

# Inputs

- `feature_id`
- `feature_name`
- `test_steps`
- `complexity_score` (0-15)

# Outputs

- Implementation finished via direct TDD
- `workflow_state.phase = execution_complete`
- Feature AI metrics recorded with `selected_model = haiku`

# State Read/Write

Read:
- `.claude/progress.json`

Write:
- `.claude/progress.json` via `progress_manager.py`

# Steps

1. Validate feature context exists and complexity bucket is `simple`.
2. Display execution banner with feature and model selection.
3. Invoke `test-driven-development`:

```text
Skill("test-driven-development", args="<feature_name>: <one_line_description>")
```

4. On success, update workflow and metrics:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state \
  --phase "execution_complete" \
  --next-action "verify_and_complete"

python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics <feature_id> \
  --complexity-score <score> \
  --selected-model haiku \
  --workflow-path direct_tdd
```

5. Ask user to run `/prog done`.

# Failure Modes

- If TDD skill invocation fails, return control to caller with clear failure reason.
- Do not mark feature complete here.

# Commands

- `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-workflow-state ...`
- `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py set-feature-ai-metrics ...`

# Examples

- Single-file config fix
- Simple form validation fix
- Straightforward UI text/state update
