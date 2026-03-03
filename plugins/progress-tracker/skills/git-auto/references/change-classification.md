# Change Classification

Classify current diff before branch strategy selection.

## Required Outputs

- `Change Class: <docs_only|ci_only|docs_ci_small|mixed|code|unknown>`
- `Changed Files: <count>`
- `Change Size: <insertions/deletions>`

## `docs_ci_small` Eligibility

All conditions required:

1. Files only in `docs/**`, `**/*.md`, `.github/workflows/**`, `.github/actions/**`.
2. No source code or dependency/lockfile changes.
3. `changed_files <= 5`.
4. `insertions + deletions <= 200`.

## Strategy Mapping

- Protected default branch + `docs_ci_small` -> `fast-pr`.
- Unprotected + mode allows + `docs_ci_small` -> `direct-main-exception`.
- Otherwise -> `standard-pr`.
