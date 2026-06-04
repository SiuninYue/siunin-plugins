# Complexity Scoring Prompt (Haiku Subagent)

Score the given feature on 4 weighted dimensions. Return JSON only, with no prose.

Dimensions (raw 0-10 each, then weighted):
- Design Decisions x4: 0=none | 3=minor pattern | 6=module/API | 10=architecture-level
- Pattern Familiarity x3: 2=identical exists | 5=similar exists | 8=new-standard | 10=novel
- Integration Surface x2: 2=pure internal | 5=1-2 external | 8=3-5 systems | 10=cross-service
- File Impact x1: 2=1-2 files | 5=3-5 | 8=6-10 | 10=10+

Total = sum of weighted scores. Max = 100.

Buckets:
- 0-37 = simple (haiku/direct_tdd)
- 38-62 = standard (sonnet/plan_execute)
- 63-100 = complex (opus/full_design_plan_execute)

Force complex when any is true:
- architecture redesign
- core refactor with unknown dependencies
- cross-cutting multi-module changes
- description too vague to assess

Force simple when all are true:
- single small bug with known fix
- no design decisions
- minimal test surface

Confidence:
- high = clear signals
- medium = some ambiguity
- low = insufficient info (caller will upgrade one tier)

Return:

```json
{
  "score": 0,
  "bucket": "simple",
  "model": "haiku",
  "path": "direct_tdd",
  "confidence": "high"
}
```
