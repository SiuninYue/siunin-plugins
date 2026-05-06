# Complexity Scoring Prompt (Haiku Subagent)

Score the given feature on 4 weighted dimensions. Return JSON only — no prose.

## Dimensions (raw 0-10 each, then weighted)

- Design Decisions ×4: 0=none | 3=minor pattern | 6=module/API | 10=architecture-level
- Pattern Familiarity ×3: 2=identical exists | 5=similar exists | 8=new-standard | 10=novel
- Integration Surface ×2: 2=pure internal | 5=1-2 external | 8=3-5 systems | 10=cross-service
- File Impact ×1: 2=1-2 files | 5=3-5 | 8=6-10 | 10=10+

Total = sum of weighted scores. Max = 100.

## Buckets

| Range | Bucket | Model | Path |
|-------|--------|-------|------|
| 0-37 | simple | haiku | direct_tdd |
| 38-62 | standard | sonnet | plan_execute |
| 63-100 | complex | opus | full_design_plan_execute |

## Override Rules

Force **complex** when any of these is true:
- Explicit architecture redesign
- Core refactor with unknown dependencies
- Cross-cutting changes across many modules
- Description too vague to assess

Force **simple** when all of these are true:
- Single small bug with known fix
- No design decisions required
- Minimal test surface

## Confidence

- `high` — clear signals, confident assessment
- `medium` — some ambiguity, reasonable estimate
- `low` — insufficient info; caller will upgrade one tier automatically

## Output Format

Return JSON only, no prose before or after:

```json
{
  "score": <0-100>,
  "bucket": "<simple|standard|complex>",
  "model": "<haiku|sonnet|opus>",
  "path": "<direct_tdd|plan_execute|full_design_plan_execute>",
  "confidence": "<high|medium|low>"
}
```
