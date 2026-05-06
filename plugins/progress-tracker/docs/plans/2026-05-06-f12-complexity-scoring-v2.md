# PT-F12: Complexity Scoring V2 — Weighted Rubric via Haiku Subagent

## Goal

Replace the Python keyword-counting `complexity_analyzer.py` with a haiku-subagent-based rubric,
update the scoring scale from 0-40 to 0-100, persist `ai_metrics.scoring_v2` fields (including
final routed bucket distinct from raw score bucket), and remove the old rubric file from
coordinator context.

## Acceptance Tests

1. Remove/deprecate `complexity_analyzer.py` and `complexity-assessment.md`
2. Haiku subagent scoring on 3 fixed known features matches expected bucket (see T3b)
3. `ai_metrics.scoring_v2` fields persisted: `raw_score_bucket`, `routed_bucket`, `confidence`
4. `pytest -q tests/` → zero regressions

---

## Tasks

### T1 — Update `determine_complexity_bucket` thresholds (RED first)

**File:** `hooks/scripts/progress_manager.py`

Write failing test first:
- `test_complexity_bucket_v2_thresholds` — asserts:
  - score 0 → "simple", score 37 → "simple"
  - score 38 → "standard", score 62 → "standard"
  - score 63 → "complex", score 100 → "complex"

Then update `determine_complexity_bucket`:
```python
def determine_complexity_bucket(score: int) -> str:
    if score <= 37:
        return "simple"
    if score <= 62:
        return "standard"
    return "complex"
```

Also update CLI help text at ~line 10918: change "Must be in range 0-40" → "Must be in range 0-100"
and score validation: `score < 0 or score > 100`.

Update existing test `test_set_feature_ai_metrics_records_fields`:
- Change input score `18 → 50` (maps to "standard" in v2 scale: 38-62)

### T2 — Add `scoring_v2` + sync `complexity_bucket` to `routed_bucket` (RED first)

**Problems addressed:**
- `scoring_v2.routed_bucket` captures post-confidence-upgrade/force-rule bucket
- **Routing sync (P1 fix):** `ai_metrics.complexity_bucket` (read by existing routing fallback in
  SKILL.md inline context fast path) must also be set to `routed_bucket`, not raw bucket.
  Strategy: **always write `complexity_bucket = routed_bucket`**. This keeps existing consumers
  correct without requiring them to know about `scoring_v2`.

**File:** `hooks/scripts/progress_manager.py`

Write failing tests first:
- `test_scoring_v2_routed_bucket_differs_from_raw` — calls with score=35 (raw="simple"),
  `bucket_override="standard"`, `confidence="low"`;
  asserts:
  - `ai_metrics["complexity_bucket"] == "standard"` (routing consumer reads correct bucket)
  - `scoring_v2["raw_score_bucket"] == "simple"`
  - `scoring_v2["routed_bucket"] == "standard"`

- `test_scoring_v2_no_override_complexity_bucket_equals_raw` — calls with score=50, no override;
  asserts `ai_metrics["complexity_bucket"] == "standard"` and
  `scoring_v2["raw_score_bucket"] == scoring_v2["routed_bucket"] == "standard"`

Update function signature:
```python
def set_feature_ai_metrics(
    feature_id: int,
    complexity_score: int,
    selected_model: str,
    workflow_path: str,
    confidence: str = "medium",
    bucket_override: str | None = None,
) -> bool:
```

Persist in `ai_metrics`:
```python
raw_bucket = determine_complexity_bucket(complexity_score)
routed_bucket = bucket_override if bucket_override else raw_bucket
ai_metrics.update({
    "complexity_score": complexity_score,
    "complexity_bucket": routed_bucket,      # ← routing consumers read this; must be final bucket
    "selected_model": selected_model,
    "workflow_path": workflow_path,
    "scoring_v2": {
        "score": complexity_score,
        "raw_score_bucket": raw_bucket,
        "routed_bucket": routed_bucket,
        "confidence": confidence,
    },
})
```

**Note on T6:** SKILL.md inline context fast path at `Bucket` field reads
`feature.ai_metrics.complexity_bucket` as fallback. No change needed there — it will now always
get `routed_bucket` automatically.

### T3 — Add `--confidence` and `--bucket-override` CLI arguments

**File:** `hooks/scripts/progress_manager.py` (CLI parser section ~line 10913)

Add to `ai_metrics_parser`:
```python
ai_metrics_parser.add_argument(
    "--confidence", choices=["high", "medium", "low"], default="medium"
)
ai_metrics_parser.add_argument(
    "--bucket-override", choices=["simple", "standard", "complex"], default=None,
    help="Override routed_bucket when confidence upgrade or force rules apply"
)
```

Pass both to `set_feature_ai_metrics` call at ~line 11360.

### T3b — Add contract tests: threshold regression + haiku output parsing

**Problem addressed (P2):** T3b must cover two distinct behaviors:
1. **Threshold regression** — `determine_complexity_bucket` maps scores correctly (already in T1)
2. **Haiku output parsing** — given a JSON response from haiku, the coordinator correctly extracts
   `bucket`, applies confidence upgrade, and assembles the `set-feature-ai-metrics` call.
   This is the testable proxy for "haiku prompt produces correct bucket for real feature text."

**File:** `tests/test_complexity_scoring_v2_contract.py` (new file)

```python
"""
Contract tests for v2 complexity scoring pipeline.

Two layers:
  Layer 1 — threshold regression (deterministic, always passes)
  Layer 2 — haiku response parsing contract (mocks haiku JSON; tests coordinator logic)

For acceptance test #2 ("haiku scores 3 features correctly"), the manual verification
template is embedded in the @pytest.mark.manual test below.
"""

HAIKU_FIXTURE_RESPONSES = {
    "fix typo in CLI help text": {
        "score": 5, "bucket": "simple", "model": "haiku",
        "path": "direct_tdd", "confidence": "high"
    },
    "add --confidence flag to CLI with bucket_override support": {
        "score": 48, "bucket": "standard", "model": "sonnet",
        "path": "plan_execute", "confidence": "high"
    },
    "refactor progress_manager.py into layered modules": {
        "score": 78, "bucket": "complex", "model": "opus",
        "path": "full_design_plan_execute", "confidence": "high"
    },
}

class TestHaikuResponseParsingContract:
    """Layer 2: coordinator correctly parses haiku JSON and applies routing rules."""

    @pytest.mark.parametrize("feature_text,expected_bucket", [
        ("fix typo in CLI help text", "simple"),
        ("add --confidence flag to CLI with bucket_override support", "standard"),
        ("refactor progress_manager.py into layered modules", "complex"),
    ])
    def test_parse_haiku_response_routes_correctly(self, feature_text, expected_bucket):
        """Given a haiku-style JSON response, routed_bucket matches expected."""
        response = HAIKU_FIXTURE_RESPONSES[feature_text]
        # Simulate coordinator routing logic
        confidence = response["confidence"]
        raw_bucket = response["bucket"]
        UPGRADE = {"simple": "standard", "standard": "complex", "complex": "complex"}
        routed_bucket = UPGRADE[raw_bucket] if confidence == "low" else raw_bucket
        assert routed_bucket == expected_bucket

    def test_low_confidence_upgrades_bucket(self):
        """confidence=low must upgrade one tier regardless of score."""
        low_conf_response = {"score": 30, "bucket": "simple", "model": "haiku",
                             "path": "direct_tdd", "confidence": "low"}
        UPGRADE = {"simple": "standard", "standard": "complex", "complex": "complex"}
        routed = UPGRADE[low_conf_response["bucket"]]
        assert routed == "standard"
```

**Manual verification template** (embedded as `@pytest.mark.manual` docstring, executed by
running `pytest -m manual -v` with real haiku calls):

```
For each fixture in HAIKU_FIXTURE_RESPONSES:
  1. Send feature_text to haiku subagent using complexity-scoring-haiku-prompt.md
  2. Assert returned JSON["bucket"] == HAIKU_FIXTURE_RESPONSES[feature_text]["bucket"]
  3. Log actual score + confidence for calibration reference
```

This provides a repeatable acceptance #2 verification path: `pytest -m manual` with haiku enabled
OR visual inspection against fixture values when running offline.

### T4 — Deprecate `complexity_analyzer.py`

**File:** `hooks/scripts/complexity_analyzer.py`

Insert after the module docstring (before first import):
```python
import warnings
warnings.warn(
    "complexity_analyzer is deprecated since PT-F12. Use haiku subagent scoring instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

Keep the file to avoid breaking `test_integration.py` TestComplexityAnalyzer tests.

### T5 — Create haiku scoring prompt

**New file:** `skills/feature-implement/references/complexity-scoring-haiku-prompt.md`

```markdown
# Complexity Scoring Prompt (Haiku Subagent)

Score the given feature on 4 weighted dimensions. Return JSON only — no prose.

Dimensions (raw 0-10 each, then weighted):
- Design Decisions ×4: 0=none | 3=minor pattern | 6=module/API | 10=architecture-level
- Pattern Familiarity ×3: 2=identical exists | 5=similar exists | 8=new-standard | 10=novel
- Integration Surface ×2: 2=pure internal | 5=1-2 external | 8=3-5 systems | 10=cross-service
- File Impact ×1: 2=1-2 files | 5=3-5 | 8=6-10 | 10=10+

Total = sum of weighted scores. Max = 100.

Buckets: 0-37=simple(haiku/direct_tdd) | 38-62=standard(sonnet/plan_execute) | 63-100=complex(opus/full_design_plan_execute)

Force complex (override score): architecture redesign | core refactor with unknown deps | cross-cutting multi-module changes | description too vague to assess
Force simple (override score): single small bug with known fix | no design decisions | minimal test surface

Confidence: high=clear signals | medium=some ambiguity | low=insufficient info (caller will upgrade one tier)

Return:
{"score": <0-100>, "bucket": "<simple|standard|complex>", "model": "<haiku|sonnet|opus>",
 "path": "<direct_tdd|plan_execute|full_design_plan_execute>", "confidence": "<high|medium|low>"}
```

### T6 — Deprecate `complexity-assessment.md`, update SKILL.md

**File:** `skills/feature-implement/references/complexity-assessment.md`

Prepend:
```
> DEPRECATED (PT-F12): Replaced by haiku subagent scoring.
> See `complexity-scoring-haiku-prompt.md` for the active rubric.
```

**File:** `skills/feature-implement/SKILL.md`

Changes (addressing P2 and P3):

1. **frontmatter `references:` (line 22):** Replace old entry with new:
   ```yaml
   - "./references/complexity-scoring-haiku-prompt.md"   # replaces complexity-assessment.md
   ```

2. **Step 3 complexity scoring block:** Replace inline rubric with haiku subagent call:
   ```
   1. Spawn haiku subagent using prompt from `references/complexity-scoring-haiku-prompt.md`
      + feature name/description as input.
   2. Parse returned JSON: {score, bucket, model, path, confidence}
   3. Apply routing rules:
      - confidence=low → upgrade one tier: simple→standard, standard→complex (set bucket_override)
      - force rules already applied by haiku (reflected in returned bucket)
   4. Persist via CLI:
      plugins/progress-tracker/prog set-feature-ai-metrics <feature_id> \
        --complexity-score <score> --selected-model <model> --workflow-path <path> \
        --confidence <confidence> [--bucket-override <bucket_override_if_upgraded>]
   ```

3. **Step 4 section headers:** Update bucket ranges from old 0-40 to v2 0-100:
   - `4A) Simple (0-15)` → `4A) Simple (0-37)`
   - `4B) Standard (16-25)` → `4B) Standard (38-62)`
   - `4C) Complex (26-40)` → `4C) Complex (63-100)`

4. **Additional Resources section:** Replace:
   ```
   - `references/complexity-assessment.md`:
     - scoring rubric and forced override rules.
   ```
   With:
   ```
   - `references/complexity-scoring-haiku-prompt.md`:
     - haiku subagent scoring prompt, v2 rubric and forced override rules.
   ```

### T7 — Run full test suite, verify zero regressions

```bash
cd plugins/progress-tracker && python -m pytest -q tests/
```

Expected: all tests pass (new tests from T1/T2/T3b included).

---

## File Ownership

| File | Action |
|------|--------|
| `hooks/scripts/progress_manager.py` | Modify: thresholds, scoring_v2, CLI args (T1, T2, T3) |
| `hooks/scripts/complexity_analyzer.py` | Deprecate: add DeprecationWarning (T4) |
| `skills/feature-implement/references/complexity-assessment.md` | Deprecate: add header (T6) |
| `skills/feature-implement/references/complexity-scoring-haiku-prompt.md` | Create (T5) |
| `skills/feature-implement/SKILL.md` | Modify: references, Step 3, Step 4 headers (T6) |
| `tests/test_progress_manager.py` | Update existing + add T1/T2 tests |
| `tests/test_complexity_scoring_v2_contract.py` | Create: T3b haiku parsing contract tests |

## Risks

- **Haiku non-determinism:** LLM-based scoring may produce inconsistent scores across runs for the same feature text. Mitigation: contract tests use mock fixtures; manual calibration tests provide drift detection.
- **Threshold migration:** Existing features scored under 0-40 scale have no automatic remapping; their bucket labels may be stale. Mitigation: only new features use v2 scoring; old records are left unchanged.
- **Deprecated file confusion:** Keeping `complexity_analyzer.py` and `complexity-assessment.md` as deprecated-but-present may confuse developers who don't see the deprecation warnings. Mitigation: clear deprecation headers in both files.
- **Mock/real divergence:** Contract tests mock haiku JSON responses; real haiku output format may drift from expected schema. Mitigation: manual verification template in T3b for periodic calibration.

## Out of Scope

- Deleting `test_integration.py` TestComplexityAnalyzer tests (file kept deprecated, tests still pass)
- Calibrating thresholds (37/62) with real production data
- Updating `workflow.md` / `README.md` file tree diagrams
