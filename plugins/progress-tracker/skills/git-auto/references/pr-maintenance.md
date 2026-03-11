# PR Maintenance (Comments + CI)

Detailed contract for the optional post-push maintenance lane used by `git-auto`.

## Scope

- Applies only when an open PR exists (or a PR number/URL is provided).
- Keeps stable command interface unchanged (`git auto*` commands remain the same).
- Supports three activation modes:
  - `address-comments`
  - `fix-ci`
  - `address-comments+fix-ci`

## Required Gates

1. Authentication:
   - MUST run `gh auth status` before any `gh` operation.
   - If unauthenticated, stop and ask user to run `gh auth login`.
2. Provider scope:
   - For check providers outside GitHub Actions, report the `detailsUrl` only.
   - MUST NOT attempt external provider remediation in this lane.

## PR Resolution

- Prefer current branch PR:
  - `gh pr view --json number,url`
- If user provides PR number/URL, use that target directly.

## Bundled Scripts

- `scripts/fetch_comments.py` (vendored from `openai/skills/.curated/gh-address-comments`)
- `scripts/inspect_pr_checks.py` (vendored from `openai/skills/.curated/gh-fix-ci`)

## Comment Handling (`address-comments`)

1. Enumerate comment threads:
   - `python3 scripts/fetch_comments.py`
2. Summarize each thread/comment with numbering and required change scope.
3. Implement only user-selected comments.
4. Re-summarize remaining unresolved comments after updates.

## CI Handling (`fix-ci`)

1. Inspect PR checks and logs:
   - `python3 scripts/inspect_pr_checks.py --repo "."`
2. Collect failure summary: check name, run URL, concise failure snippet.
3. Draft a fix plan and request explicit user approval before implementing.
4. After fixes, rerun/recheck:
   - local validation commands relevant to failure
   - `gh pr checks`

## Merge Gate Behavior

- For `Execution Intent=commit_push_pr_merge`, merge MUST be blocked while required checks fail.
- If `fix-ci` is active and the user approved implementation, iterate commit/push/recheck until checks pass or the user stops.

## Plan Reporting Fields

When PR maintenance lane is active, include these optional plan lines:

- `PR Maintenance: <none|address-comments|fix-ci|address-comments+fix-ci>`
- `PR URL: <url|n/a>`
- `CI Status: <green|failing|unknown|external-checks>`
- `Comment Status: <none|pending|resolved|unknown>`
