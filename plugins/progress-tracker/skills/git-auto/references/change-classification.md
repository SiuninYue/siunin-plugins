# Change Classification

Classify current diff before branch strategy selection.

## Required Outputs

- `Change Class: <docs_only|ci_only|low_impact|mixed|code|unknown>`
- `Changed Files: <count>`
- `Change Size: <insertions/deletions>`

## Class Boundary Rules

- `docs_only`: every changed file is under docs/** or is *.md.
- `ci_only`: every changed file is under .github/workflows/** or .github/actions/**.
- `low_impact`: mixed docs + CI/config files that meet the eligibility guidelines below. If a change qualifies as docs_only or ci_only, use the more specific class instead of low_impact.
- `mixed`: contains both low-risk and source-code files.
- `code`: primarily source code changes.
- `unknown`: cannot classify.

## low_impact Eligibility

Guidelines (not hard cutoffs):

1. Files typically in docs/**, **/*.md, .github/workflows/**, .github/actions/**
2. No source code or dependency/lockfile changes
3. Typically ≤5 files, ≤200 lines changed
4. CI path changes that alter deployment or release pipelines are NOT
   low_impact regardless of size

## Strategy Mapping

- Protected default branch + `docs_only|ci_only|low_impact` → `fast-pr`.
- Unprotected + mode allows (see direct-main-exception table) + `docs_only|low_impact` → `direct-main-exception`.
- Otherwise → `standard-pr`.

## direct-main-exception Eligibility

| Enforcement Mode | direct-main-exception |
|-----------------|----------------------|
| soft            | Allowed (low risk)   |
| hybrid          | Allowed (low_impact only) |
| hard            | Denied               |

Plus: Repo Policy = unprotected, Change Class ∈ {docs_only, low_impact}.