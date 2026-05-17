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

## Post-Worktree Monorepo Routing

After `using-git-worktrees` creates a worktree, monorepo child projects may have a broken route chain. The first mutating `prog` command (e.g. `prog done`, `prog next`,
`prog set-workflow-state`) will fail with:

```
[Route Preflight] BLOCKED: Child project_code=<X> is not registered in any parent linked_projects.
```

Read-only commands (`prog status`, `prog check`) do **not** reach the route-preflight guard and cannot detect this condition.

### Proactive Verification

Instead of relying on a command to smoke-test, check the child's `progress.json` directly: if
`tracker_role` is `"child"`, proactively run the fix below before issuing any mutating prog commands.
The worktree copy of the child's progress state is a clone — the route chain to the parent repo
must be re-established.

### Fix: Link Child Project Back to Parent

The global `--project-root` is the **child** path, and `--parent-root` is the **parent tracker** root
(the directory whose `progress.json` has `tracker_role: "parent"`).
Both should be explicit to avoid cwd-dependent misapplication:

```bash
# 1. Register the worktree child project in the parent's linked_projects
plugins/progress-tracker/prog \
  --project-root <worktree_path>/plugins/<child_dir> \
  link-project \
  --code <PROJECT_CODE> \
  --parent-root <parent_tracker_root>

# 2. Select the project route
plugins/progress-tracker/prog \
  --project-root <parent_tracker_root> \
  route-select \
  --project <PROJECT_CODE> \
  --feature-ref <CODE>-F<number>
```

After linking, mutating prog commands inside the worktree child project will work normally.

### Why This Happens

`enforce_route_preflight()` calls `_discover_parent_route_bindings_for_child()`, which scans
`repo_root` and `repo_root/plugins/*` for tracker directories with `tracker_role: "parent"` whose
`linked_projects` entries resolve to the child's path. When a worktree is a full repo clone, the
worktree root may lack `tracker_role: "parent"` or its `linked_projects` may reference the wrong
child paths. `parent_project_root` is used for parent-sync/writeback, not for this preflight path.
