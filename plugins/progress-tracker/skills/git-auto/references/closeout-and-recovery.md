# Closeout And Recovery

## Lightweight Autorun

When intent includes push/PR and change is low-risk, autorun may execute through push + draft PR.

Required autorun outputs:

- `Execution Mode: autorun`
- `Autorun Reason: <qualification>`
- `Autorun Scope: <through push|through push + draft-pr>`

## Accelerated Closeout

For `Execution Intent=commit_push_pr_merge` only:

1. Commit
2. Push
3. Create or update PR
4. Check PR status
5. Merge if gates pass

## Recovery

- `GH006`: preserve local commit, switch to short-lived branch, push branch, create PR.
- Push rejected (non-ff): fetch/rebase, then retry.
- Existing draft PR: update instead of creating duplicate.
- Pending/failing checks: stop and return blocker summary.

## Closeout Result Block

After closeout completes (commit + push + PR), output the Execution Result Block in the same format as `git-auto/SKILL.md`:

```
=== Git Auto Result ===
CommitHash: <full_40_char_sha>
PR: <url|draft_url|none>
Status: <ok|blocked>
=== End Result ===
```

`BlockReason: <reason>` is appended when `Status: blocked`.

## Merge Gates

- `soft`: sync clean.
- `hybrid`: sync clean + passing CI + review-ready.
- `hard`: sync clean + passing CI + required approvals + no blocking discussion.
