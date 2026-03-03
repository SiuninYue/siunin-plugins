# Worktree Decision

Use `plugins/progress-tracker/prog git-auto-preflight --json` as the only workspace fact source.

## Decision Contract

- `ALLOW_IN_PLACE`
- `REQUIRE_WORKTREE`
- `DELEGATE_GIT_AUTO`

## Decision Priority

1. `critical` issues or conflict markers -> `DELEGATE_GIT_AUTO`.
2. Default-branch feature work in-place -> `REQUIRE_WORKTREE`.
3. Otherwise -> `ALLOW_IN_PLACE`.

## Required Output Fields

- `Workspace Mode: <in-place|worktree>`
- `Worktree Decision Reason: <reason_codes>`

## Delegation Boundary

- `git-auto` decides **whether** worktree isolation is needed.
- `using-git-worktrees` handles directory selection and setup.
