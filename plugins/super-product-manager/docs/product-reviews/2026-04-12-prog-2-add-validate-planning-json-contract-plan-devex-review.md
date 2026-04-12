# Plan DevEx Review: PROG-2 add validate-planning json contract

- Date: 2026-04-12
- Score: 8/10

## Frictions
- message field is prose-only making scripting fragile
- no feature-id inference from context requires explicit supply
- error path for missing feature or empty refs undefined

## Improvements
- Define message as machine-readable key with optional description field
- Support implicit feature resolution from current_feature_id
- Document exit codes: 0=ready/warn 1=missing for shell chaining

## Recommendation
- Proceed with score 8/10. Clarify message semantics and exit codes before beta usage in hooks/CI.

## Lane Trigger Hint
- devex lane suggested by categories: no
