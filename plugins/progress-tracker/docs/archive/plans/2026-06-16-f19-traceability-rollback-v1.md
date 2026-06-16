# F19 Traceability and Rollback v1 Implementation Plan

> **For agentic workers:** Resume from this file task-by-task. Treat the current session as planning only. Implementation must move to an isolated worktree before editing source files because `prog git-auto-preflight` returned `REQUIRE_WORKTREE` on dirty `main`.

**Goal:** Add a fail-closed traceability system for high-risk `progress-tracker` changes: structured change records, generated changelog output, and a deterministic rollback SOP that works across archive-restore and `git revert` fallback paths.

**Architecture:** Keep `docs/changes/index.jsonl` as the single writable ledger, normalize the existing ledger before fail-closed enforcement, generate a managed traceability block inside `CHANGELOG.md` from that ledger while preserving frozen pre-F19 release history in v1, and enforce the contract from pre-commit through focused validator/renderer scripts plus targeted regression coverage. Ship one dogfood record so the workflow is self-demonstrating.

**Tech Stack:** Python 3, Bash pre-commit hook, JSONL, Markdown docs, `pytest`, existing `prog` state/docs checks.

**Plan path:** `docs/plans/2026-06-16-f19-traceability-rollback-v1.md`

**Working directory for all shell commands in this plan:** `/Users/siunin/Projects/Claude-Plugins`

## Command Root Convention

- All shell commands below assume monorepo-root cwd and therefore use repo-root-relative paths such as `plugins/progress-tracker/...`.
- `plan_path` and ledger `record_path` values remain project-root-relative to `plugins/progress-tracker`, for example `docs/plans/...` and `docs/changes/...`.
- Do not mix repo-root-relative shell paths with plugin-root-relative shell paths in the same implementation pass.
- Absolute paths may still appear in prose when naming historical reference files, but not in shell command examples.

---

## Execution Constraints

- Do not fabricate planning evidence or rollback outcomes. Required artifacts must come from real files and real command output.
- `plugins/progress-tracker/docs/changes/index.jsonl` stays the single writable ledger for generated traceability data.
- Ledger rows must use the canonical field set `change_id/date/component/summary/root_cause/fixes/touched_files/test_command/test_result/rollback_strategy/record_path`.
- `record_path` values stored in the ledger must be project-root-relative to `plugins/progress-tracker`, using the form `docs/changes/<file>.md`.
- Validator and renderer must resolve detail records from `record_path` only. They must not derive detail file names from `change_id`, file stem heuristics, or round/module metadata.
- Before fail-closed validation is enabled, all existing ledger rows must be normalized to the canonical contract. Malformed historical rows must be repaired or replaced; they must not be silently skipped.
- Existing historical `change_id` values are immutable once published because commit lookup uses them as search anchors. v1 format enforcement applies only to newly added ledger rows in the current implementation and later commits; historical rows must not be renamed solely to satisfy the new suffix convention.
- `plugins/progress-tracker/CHANGELOG.md` v1 must preserve existing manual release history outside a managed generated block. The renderer must not delete legacy sections until a separate history-backfill feature lands.
- The managed generated block must live under `## [Unreleased]` with explicit begin/end markers so release history above it remains byte-stable.
- Inside `## [Unreleased]`, the managed generated block must have a fixed relative position after the existing manual subsections/prose for that release train. The renderer may replace only the marker-delimited block body and must leave adjacent manual `Unreleased` content byte-stable.
- High-risk scope must be derived from the current post-F27 codebase, not the older F18 topology alone:
  - use `docs/progress-tracker/architecture/progress-manager-module-map.md` as the owner map for extracted clusters through the latest documented module-map snapshot
  - because that module map currently stops before the completed F26/F27 rounds, supplement it with the archived F26/F27 plans and current `progress.json` feature records when seeding the list
  - include any still-facade-owned high-risk paths in `progress_manager.py` until those clusters are fully extracted
  - for F19 v1 specifically, treat `hooks/scripts/progress_manager.py` itself as high-risk because the validator matches at file granularity and the file still contains reconcile/workflow/install-hook residual paths that cannot be isolated by line-level matching
- Validation is fail-closed:
  - record contract failure -> non-zero and block commit
  - validator internal crash -> distinct non-zero code and block commit
- Validator scope is split intentionally:
  - full-ledger checks: JSONL syntax, required fields, duplicate `change_id`, readable `record_path`
  - newly added row checks: `YYYYMMDD-<slug>-<4hex>` naming convention and any v1-only stricter formatting rules
- Commit lookup must use `git log --all --diff-filter=A -S '"change_id": "<id>"'`.
- `walkthrough_git_worktree.md` is preserved as a historical/legacy reference, not the primary template for new records.
- `plugins/progress-tracker/hooks/pre-commit` is only the tracked source of truth. Real enforcement in developer workflows occurs only after copying that file into the active Git hooks directory via `prog install-git-hooks`.
- Bootstrap rule: do not install the live F19 pre-commit hook into `.git/hooks` until the first canonical F19 ledger row and detail record are fully staged in the same working tree. The first commit exercised by the live hook must already satisfy the change-record contract.
- `prog install-git-hooks` resolves hook targets through `git rev-parse --git-path hooks`, so live hook installation must be treated as a shared repository mutation that may affect sibling worktrees using the same common Git directory.
- Real-hook verification must therefore happen as late as possible in the isolated worktree, record the absolute installed hook paths as evidence, and define how shared hook state is restored or refreshed if F19 verification is aborted or paused before merge.
- `prog install-git-hooks` copies hook sources from the current worktree checkout (`Path(__file__).parent / ../pre-commit` and sibling sources), so rerunning it inside the F19 worktree will always reinstall the F19 payload. Restoring the main-branch payload therefore requires either restoring an explicit backup copy or rerunning `install-git-hooks` from a main-branch worktree.
- If F19 implementation needs any new CLI-visible entrypoint during execution, keep `progress_manager.py` as wrapper/dispatch only; new business logic must live in dedicated submodules under `hooks/scripts/`.
- Because this feature touches `plugins/progress-tracker/**`, every implementation pass must finish with:
  - `bash scripts/check_pm_boundary.sh`
  - `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check`

## File Targets

- Modify `plugins/progress-tracker/docs/changes/index.jsonl`
- Add `plugins/progress-tracker/docs/changes/high_risk_scripts.txt`
- Normalize any existing `plugins/progress-tracker/docs/changes/*.md` detail records whose metadata/path references conflict with the canonical contract
- Add one new `plugins/progress-tracker/docs/changes/YYYYMMDD-*.md` dogfood record
- Add `plugins/progress-tracker/hooks/scripts/validate_change_record.py`
- Add `plugins/progress-tracker/hooks/scripts/render_changelog_from_index.py`
- Modify `plugins/progress-tracker/hooks/pre-commit`
- Modify the managed generated section inside `plugins/progress-tracker/CHANGELOG.md`
- Update `plugins/progress-tracker/tests/test_git_hooks_install.py` if installed-hook copy behavior changes
- Update any docs that describe rollback or change-record handling, including the legacy note for `/Users/siunin/Projects/Claude-Plugins/walkthrough_git_worktree.md`
- Add focused tests for ledger normalization, validator, renderer, and pre-commit behavior

## Task 0: Workspace Prep

- [ ] Create or switch to an isolated worktree/branch for F19 before source edits.
- [ ] Capture baseline evidence:
  - `plugins/progress-tracker/prog --project-root plugins/progress-tracker git-auto-preflight --json`
  - `uv run pytest plugins/progress-tracker/tests/ -q`
- [ ] Record the chosen worktree path in the next `/prog-next` handoff block.

## Task 1: Legacy Ledger Normalization and Compatibility

**Files:**
- Modify `plugins/progress-tracker/docs/changes/index.jsonl`
- Modify any impacted `plugins/progress-tracker/docs/changes/*.md`
- Modify `plugins/progress-tracker/CHANGELOG.md`

- [ ] Inventory current ledger rows and classify each as canonical, repairable, or incompatible legacy data.
- [ ] Normalize all retained ledger rows to the canonical field set before any validator/render hook is allowed to fail closed on the full file.
- [ ] Preserve every retained historical `change_id` verbatim, even when it does not match the new `<4hex>` suffix convention.
- [ ] Canonicalize every retained `record_path` to the project-root-relative form `docs/changes/<file>.md`.
- [ ] Resolve the current partial legacy row before enforcement starts:
  - repair it into a full canonical row backed by a readable detail record, or
  - replace it in the same change with an equivalent canonical record that preserves the historical intent
- [ ] Ensure the normalized ledger ends with a trailing newline so future append operations cannot merge two JSON objects onto one line.
- [ ] Add explicit managed-block markers to `plugins/progress-tracker/CHANGELOG.md` and preserve all pre-F19 release history outside that block.
- [ ] Freeze the relative placement of the managed block under `## [Unreleased]` against the current manual `Unreleased` content, so generated traceability entries do not reorder or overwrite hand-maintained notes.
- [ ] Reconcile F19’s historical module assumptions with the current facade map before seeding any guardrails:
  - review extracted owner modules in `progress-manager-module-map.md`
  - supplement that review with completed F26/F27 feature records because the module map lags the latest extraction rounds
  - review remaining facade-owned high-risk clusters that still live in `progress_manager.py`
- [ ] Document the v1 compatibility stance in the plan implementation notes:
  - no silent legacy-row skip logic
  - no destructive changelog history rewrite
  - no historical `change_id` rewrite just to satisfy new-row format policy

## Task 2: Ledger Contract and Validator

**Files:**
- Add `plugins/progress-tracker/hooks/scripts/validate_change_record.py`
- Add `plugins/progress-tracker/docs/changes/high_risk_scripts.txt`
- Add focused tests such as `plugins/progress-tracker/tests/test_validate_change_record.py`

- [ ] Write failing tests for:
  - invalid JSONL syntax
  - missing required fields
  - duplicate `change_id`
  - missing or unreadable `record_path`
  - `record_path` resolution is project-root-relative to `plugins/progress-tracker`
  - detail file lookup uses `record_path` directly and does not infer a filename from `change_id`
  - historical rows with non-hex-suffix `change_id` remain valid after normalization
  - newly added rows fail if they do not match `YYYYMMDD-<slug>-<4hex>`
  - missing `high_risk_scripts.txt`
  - validator internal error returning a distinct crash code
- [ ] Implement a validator that:
  - parses the full normalized ledger
  - resolves `record_path` relative to the target project root
  - scans staged high-risk files only
  - requires at least one newly staged canonical ledger entry plus readable detail record when high-risk files are staged
  - enforces `YYYYMMDD-<slug>-<4hex>` `change_id` format for newly added rows only
  - distinguishes contract failure from validator crash
- [ ] Seed `high_risk_scripts.txt` from current module ownership rather than historical monolith slices.
  - At minimum, review extracted owners for lock/state/git/worktree/evaluator/feature activation/backlog-intake mutation/next-feature/completion/workflow/reconcile/entropy behavior.
  - Also review `progress_manager.py` itself for any remaining facade-owned high-risk paths such as reconcile/workflow/install-hook routing that have not yet moved into a dedicated module.
  - For F19 v1, include `hooks/scripts/progress_manager.py` in the initial list instead of attempting partial file coverage; remove it only after those residual high-risk clusters are extracted into dedicated modules and the list can enroll those narrower owner files directly.
- [ ] Include F19’s own guardrail meta-files in the initial self-coverage set so dogfood verification exercises the enforcement path on the feature’s own artifacts.
  - At minimum, review `hooks/scripts/validate_change_record.py`, `hooks/scripts/render_changelog_from_index.py`, `hooks/pre-commit`, and `docs/changes/high_risk_scripts.txt`.
- [ ] Document list-maintenance policy for `high_risk_scripts.txt` so new high-risk modules must be explicitly enrolled rather than silently drifting out of coverage.

## Task 3: Changelog Renderer and Hook Enforcement

**Files:**
- Add `plugins/progress-tracker/hooks/scripts/render_changelog_from_index.py`
- Modify `plugins/progress-tracker/hooks/pre-commit`
- Add focused tests such as `plugins/progress-tracker/tests/test_render_changelog_from_index.py` and `plugins/progress-tracker/tests/test_pre_commit_change_record_guard.py`

- [ ] Write failing tests for stable render order, duplicate avoidance, legacy-section preservation, managed-marker placement under `## [Unreleased]`, and staged-file comparison behavior.
- [ ] Implement a renderer that:
  - reads the full normalized ledger
  - sorts deterministically by `date` then `change_id`
  - rewrites only the managed generated block inside `plugins/progress-tracker/CHANGELOG.md`
  - preserves the current relative ordering between manual `## [Unreleased]` notes and the marker-delimited generated block
  - leaves the frozen legacy sections byte-stable
- [ ] Extend `hooks/pre-commit` so high-risk staged changes:
  - run the validator first
  - regenerate `CHANGELOG.md`
  - compare against the staged version
  - auto-stage the regenerated changelog before failing or succeeding as designed
- [ ] Keep the tracked source hook and installed live hook flows explicit:
  - source edits happen in `plugins/progress-tracker/hooks/pre-commit`
  - live enforcement is activated only by running `python3 plugins/progress-tracker/hooks/scripts/progress_manager.py install-git-hooks`
- [ ] Extend or add tests around the hook-install copy path so the installed `.git/hooks/pre-commit` content is proven to carry the new F19 validation/render steps, not just the tracked source file.
- [ ] Defer live hook installation until the first canonical F19 row + detail record are already staged, so bootstrap does not deadlock itself.
- [ ] Keep existing doc-parity and PM-boundary checks intact.

## Task 4: Rollback SOP and Dogfood Record

**Files:**
- Add one canonical detail record under `plugins/progress-tracker/docs/changes/`
- Update rollback/process docs
- Mark `/Users/siunin/Projects/Claude-Plugins/walkthrough_git_worktree.md` as `legacy_record`

- [ ] Write the first canonical change-detail record using the new template sections:
  - issue
  - root cause
  - fixes
  - impact
  - verification commands
  - rollback steps
  - residual risk
- [ ] Document the three rollback routes:
  - A: archive restore + reconcile check
  - B: `git revert` + reconcile check + manual confirmation
  - C: reconcile still fails -> stop with fixed diagnostic commands
- [ ] Add commit lookup guidance that explicitly uses `--diff-filter=A` to avoid false matches on later edits.
- [ ] Prepare the first canonical dogfood row + detail record early enough that the first live-hook-tested commit can pass without any bootstrap exemption.
- [ ] Add a shared-hook cleanup note to the rollback/process docs for interrupted verification:
  - before the first live install, snapshot the current shared hook payloads, for example:
    - `cp "$(git rev-parse --git-path hooks)/pre-commit" "/tmp/f19-pre-commit.backup"` when the file exists
    - `cp "$(git rev-parse --git-path hooks)/post-merge" "/tmp/f19-post-merge.backup"` when the file exists
  - if F19 verification is abandoned before merge, restore the shared hooks by either:
    - copying the backups back into `$(git rev-parse --git-path hooks)`, or
    - switching to a main-branch worktree and rerunning `python3 plugins/progress-tracker/hooks/scripts/progress_manager.py install-git-hooks`
  - explicitly note that rerunning `install-git-hooks` from the F19 worktree does not restore the main payload; it reinstalls the F19 payload because the source files are resolved from that worktree checkout
  - if verification succeeds, document which branch/source becomes the new canonical installed hook payload

## Task 5: End-to-End Verification and Closeout Evidence

- [ ] Run focused tests for validator, renderer, and pre-commit integration.
- [ ] Run focused hook-install regression coverage because live hook installation still routes through the `progress_manager.py` facade:
  - `uv run pytest plugins/progress-tracker/tests/test_git_hooks_install.py -q`
- [ ] Reinstall the updated hooks into the active Git hooks directory:
  - `python3 plugins/progress-tracker/hooks/scripts/progress_manager.py install-git-hooks`
- [ ] Before the first live install, back up any existing shared hook payloads so restoration is possible without guessing prior contents.
- [ ] Capture the absolute installed hook paths returned by `install-git-hooks` and record whether they resolve into the repository’s shared hooks directory.
- [ ] Run the required progress-tracker checks:
  - `bash scripts/check_pm_boundary.sh`
  - `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check`
- [ ] Run the relevant regression slice, then full plugin tests if the focused slice is clean.
- [ ] Capture one real `git commit` execution in the isolated worktree using the installed hook copy, so evidence proves `.git/hooks/pre-commit` is the path being exercised rather than only direct script tests.
- [ ] After the real-commit verification, record the shared-hook postcondition:
  - whether the installed hook payload is intentionally left active for sibling worktrees
  - or whether it was restored from backup or refreshed from a main-branch worktree before leaving the F19 worktree
- [ ] Append the finished ledger record to `plugins/progress-tracker/docs/changes/index.jsonl` and confirm the managed `CHANGELOG.md` block matches regenerated output while legacy sections remain unchanged.
- [ ] Capture rollback proof and final verification commands in the dogfood record so `/prog-done` has auditable evidence.

## Acceptance Mapping

- Legacy ledger normalization and path canonicalization -> Task 1
- Fail-closed record validation -> Task 2
- Deterministic changelog generation, staged sync, legacy-history preservation, and marker protocol -> Task 3
- Commit lookup by original add commit only -> Task 4
- Archive/git-revert/C-route rollback SOP -> Task 4
- Live hook activation and real commit-path evidence -> Task 5
- Progress-tracker regression safety and boundary/docs checks -> Task 5

## Risks

- Existing legacy records may require more repair work than estimated before fail-closed enforcement can be safely enabled.
- The validator can over-match staged files if the high-risk list is too broad.
- The high-risk list can decay over time if new modules are not explicitly enrolled.
- The high-risk list can under-cover reality if it is seeded from pre-modularization assumptions and misses extracted owner modules or remaining facade-owned paths.
- Real-hook verification from an isolated worktree can leak a branch-specific hook payload into the repository’s shared hooks directory unless installation timing and cleanup are explicit.
- Auto-staging `CHANGELOG.md` can be confusing if staged-vs-working-tree comparisons are not explicit in hook output.
- Managed changelog block markers can drift if users edit them manually; tests and hook messages need to make that failure mode obvious.
- Full-ledger rendering is acceptable at the current ledger size, but implementation must record the observed runtime and note when future pagination/caching work would become necessary.
- `git revert` remains coarse after squash merges; the documented SOP must be precise about manual confirmation boundaries.
- Worktree enforcement plus route consistency can interrupt automation if implementation resumes from the wrong root.

## Open Decisions Before Execution

- `git commit --no-verify` bypasses all local pre-commit logic. v1 should document this explicitly as a non-goal of local enforcement and define whether urgent-fix operators need a recorded manual follow-up process.
- Confirm whether feature slot `F19` is intentionally being backfilled even though the repository already contains later shipped feature numbers such as F25 and F28.
- Confirm whether the stale `progress-manager-module-map.md` snapshot should be refreshed as part of F19 documentation touchpoints or merely treated as a historical aid supplemented by F26/F27 records.

## Recommended Complexity Routing

- Complexity score: `66`
- Bucket: `complex`
- Selected model: `opus`
- Workflow path: `full_design_plan_execute`
- Confidence: `medium`

Rationale: the feature spans pre-commit policy, generated docs, rollback recovery semantics, Git history lookup rules, and fail-closed testing. The change surface is cross-cutting and safety-sensitive even though it is not UI-heavy.
