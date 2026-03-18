# Communication Templates (Progress Recovery)

## Template: Resume Available

```markdown
## Resume Available

Project: <project>
Progress: <done>/<total>
Current feature: <id> - <name>
Phase: <phase>
Plan valid: <yes/no>

Recommended next action:
1. <primary>
2. <secondary>
```

## Template: Plan Invalid

```markdown
## Plan Requires Repair

Current plan cannot be used safely.

Reason:
- <validation error>

Next:
1. Recreate plan.
2. Resume execution.
```

## Template: Risky Git State

```markdown
## Uncommitted Changes Detected

Current resume path may conflict with local edits.

Choose one:
1. Commit current changes.
2. Stash current changes.
3. Cancel recovery.
```

## Template: No Recovery Needed

```markdown
No interrupted work detected.
Use `/prog next` to start the next feature.
```

---

## Context Handoff Block (use at END of every response)

Generate this block at the end of every response. It is designed to be pasted into a **new conversation** so the AI resumes instantly without reading any files or re-running setup.

**Choose the correct invocation based on phase:**

### Phase = `execution_complete` → use `prog-done`

```
---
**Paste into a new session to complete this feature:**

/progress-tracker:prog-done

Feature: <feature_id> "<feature_name>" | Phase: execution_complete
Plan: <plan_path> | Tasks: <total>/<total> done
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Switch to worktree/branch above first if not already there.
---
```

### Phase = `execution` or `planning_complete` → use `prog-next`

```
---
**Paste into a new session to resume:**

/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: <phase>
Plan: <plan_path> | Tasks: <completed>/<total> done
Next: <next_task_id> — <next_task_title>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Switch to worktree/branch above first if not already there.
---
```

### Phase = `planning` (fresh start, no plan yet) → use `prog-next`

```
---
**Paste into a new session to continue planning:**

/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: planning
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded.
---
```

### Phase = `planning:clarifying` → use `prog-next`

```
---
**Paste into a new session to continue planning:**

/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: planning:clarifying
Questions: <Q1> | <Q2> | <Q3>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Answer questions above to continue.
---
```

### Phase = `planning:draft` → use `prog-next`

```
---
**Paste into a new session to review plan draft:**

/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: planning:draft
Plan: <plan_path>
PlanSummary: <单行; 分号分隔; 3-5 要点>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Review plan and confirm or request changes.
---
```

### Phase = `planning:approved` → use `prog-next`

```
---
**Paste into a new session to begin implementation:**

/progress-tracker:prog-next

Feature: <feature_id> "<feature_name>" | Phase: planning:approved
Plan: <plan_path>
PlanSummary: <同上，保持不变>
Bucket: <simple|standard|complex>
Tasks: <total_count>
Branch: <branch>[ | Worktree: <worktree_path>]
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Routes by Bucket field. No planning questions.
---
```

**Rules:**
- `ProjectRoot` always included (even in-place workflows)
- `PlanSummary` must be single line, semicolon-separated
- `Tasks` omitted in clarifying/draft/planning phases
- `Questions` only present in `planning:clarifying` block
- `Bucket` only present in `planning:approved` block
- Worktree line: include only if a worktree is in use; omit otherwise
- Plan line: omit if `plan_path` not yet set
- Tasks line: omit if phase is `planning`
- Next line: include specific task title, not generic descriptions
- Keep block ≤ 8 lines of content — no narrative

**Why this saves tokens in new sessions:**
The receiving skill checks for this inline context and skips `progress.json` reading, memory overlap check, git preflight, and plan re-validation for resume scenarios.
