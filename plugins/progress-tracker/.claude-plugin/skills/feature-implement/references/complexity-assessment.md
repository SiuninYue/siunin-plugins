# Complexity Assessment Rules

## Purpose

Provide deterministic complexity scoring for model routing.

## Inputs

- Feature name and description
- Number and complexity of test steps
- Expected file impact
- Familiarity with existing patterns

## Scoring Dimensions (0-10 each)

### 1) File Impact

- 1-2 files: 2
- 3-5 files: 5
- 6-10 files: 8
- 10+ files: 10

### 2) Test Complexity

- <3 steps: 2
- 3-5 steps: 5
- 6-8 steps: 8
- >8 steps: 10

### 3) Design Decisions

- None: 0
- Minor pattern choice: 3
- Module/API design: 6
- Architecture-level decisions: 10

### 4) Pattern Familiarity

- Identical pattern exists: 2
- Similar pattern exists: 5
- New but standard pattern: 8
- Novel pattern / no precedent: 10

## Buckets

- 0-15: `simple` -> delegate to `feature-implement-simple` (`haiku`)
- 16-25: `standard` -> execute in coordinator (`sonnet`)
- 26-40: `complex` -> delegate to `feature-implement-complex` (`opus`)

## Override Rules

Force `complex` when any of these is true:
- Explicit architecture redesign
- Core subsystem refactor with unknown dependencies
- Cross-cutting changes across many modules

Force `simple` when all are true:
- Single small bug with known fix
- No architectural/design decisions
- Minimal test surface

## Output Contract

Return these fields for downstream use:

- `complexity_score`
- `complexity_bucket`
- `selected_model`
- `workflow_path`
