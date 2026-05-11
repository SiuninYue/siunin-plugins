# F13 Plan: `prog-smart` AI-First Intent Routing

## Goal
Introduce `prog-smart` as the single natural-language intake path for adding work items to PROG, with classification owned by AI (not backend heuristics).

## Context
- Current behavior should avoid backend auto-classification fallback.
- User preference: AI decides `bug` vs `feature` vs `update`.
- If AI cannot decide confidently, it must ask one clarification question and stop before any write.

## Scope
- Add a new `prog-smart` command/skill path.
- Route classified intents to exactly one write command:
  - `prog add-bug`
  - `prog add-feature`
  - `prog add-update`
- Add explicit ambiguity policy in skill contract.
- Keep `prog-note` focused on structured progress updates only.

## Non-Goals
- Re-introducing backend keyword-based auto classification.
- Adding hidden fallback writes when intent is ambiguous.
- Changing bug lifecycle semantics in `prog-fix`.

## Decisions
1. Classification is performed by AI/skill orchestration layer.
2. Backend `progress_manager.py` stays as deterministic executor.
3. Ambiguous intent must trigger one user clarification question.
4. No default route to `idea` for ambiguous items.

## Implementation Steps
1. Add `commands/prog-smart.md` that invokes `progress-tracker:prog-smart`.
2. Add `skills/prog-smart/SKILL.md` with routing contract and ambiguity guard.
3. Ensure command discovery and docs include `/prog-smart`.
4. Add focused tests for:
   - explicit bug route -> `add-bug`
   - explicit feature route -> `add-feature`
   - explicit update route -> `add-update`
   - ambiguous input -> ask clarification, no mutation

## Acceptance Criteria
- `/prog-smart "<input>"` performs exactly one mutation when intent is clear.
- Ambiguous input produces clarification prompt and no file mutation.
- `prog-note` remains a note/update tool, not a router.
- Existing `prog-fix` and `prog-note` command contracts remain valid.

## Risk & Mitigation
- Risk: misclassification in edge wording.
  - Mitigation: hard ambiguity branch + explicit confirmation.
- Risk: command overlap confusion.
  - Mitigation: clear command docs (`prog-smart` vs `prog-note` vs `prog-fix`).

## Verification Plan
- Contract tests for new command/skill wiring.
- Unit tests for route selection behavior.
- Integration check: no unexpected changes to progress state on ambiguous input.

## Rollback
- Remove `prog-smart` command/skill and command-doc entries.
- Keep core write commands unchanged.
