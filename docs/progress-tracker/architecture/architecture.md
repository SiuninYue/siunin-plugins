# Architecture: PROG Full Normalization

**Created**: 2026-03-16
**Last Updated**: 2026-03-16
**Sources**:
- `/Users/siunin/Projects/Claude-Plugins/docs/plan/ds-plan-part1.md`
- `/Users/siunin/Projects/Claude-Plugins/docs/plan/ds-plan-part2.md`
- `/Users/siunin/Projects/Claude-Plugins/docs/plan/ds-plan-part3-v2.md`
- `/Users/siunin/Projects/Claude-Plugins/docs/plan/ds-plan-part4.md`

`ds-plan-part3-v2.md` is treated as the only valid Part 3 source. Any older Part 3 variant is superseded.

## Goals

- Normalize Progress Tracker from schema `2.0` to `2.1` without breaking existing `/prog-*` command usage.
- Make `lifecycle_state` and `integration_status` the canonical state model while preserving `development_stage` and `completed` as legacy mirrors.
- Eliminate unsafe direct-write behavior by routing every mutating path through one transaction and audit pipeline.
- Fix the long-standing closeout gap: `/prog-done` must end in an explicit integration outcome or a persisted `finish_pending` state that blocks `/prog-next`.
- Preserve worktree safety: dirty or current worktrees are never auto-deleted.
- Keep status output fast and deterministic by introducing a derived summary projection with checksum-based drift detection.
- Separate retrospectives from archive metadata so postmortem content does not overload feature archive bookkeeping.
- Provide a machine-consumable downstream contract for `/prog-init`, `/prog-next`, and later implementation skills.
- Make monorepo scope selection fail closed for mutating commands so `/prog-next` cannot silently resume the wrong project tracker.

Current repository baseline on 2026-03-16:

- `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/hooks/scripts/progress_manager.py` still declares `CURRENT_SCHEMA_VERSION = "2.0"` and mutating flows still write through `save_progress_json(...)`.
- `pytest -q plugins/progress-tracker/tests/test_feature_contract_readiness.py` currently fails on missing lifecycle/readiness/retro/ref wiring.
- `pytest -q plugins/progress-tracker/tests/test_feature_completion_state_transition.py` currently passes, which means legacy `planning -> developing -> completed` behavior must remain compatible after normalization.

## Scope Boundaries

### In Scope

- `progress.json` schema `2.1` backfill, validation, and compatibility logic.
- Centralized transactional write path for state, audit updates, and summary projection.
- Closeout gate design for `/prog-done`, `/prog-next`, and worktree cleanup.
- Contract import, readiness validation, lifecycle transitions, refs enrichment, retro separation, and summary projection.
- Monorepo and linked-project scope rules for safe root-level invocation.
- Command/help/doc updates required to keep public behavior and generated docs consistent.
- Test expansion for migration, concurrency, finish-gate, worktree, and summary consistency risks.

### Out of Scope

- Replacing the plugin's file-backed persistence with a database or remote service.
- Rewriting command markdown wrappers into a different command architecture.
- Redesigning unrelated plugins or non-PROG workflows.
- Broad UI redesign beyond what is required for summary/status correctness.
- Implicit cross-project mutation from a monorepo root without an explicit target scope.

### Recommended System Shape

Use a modular monolith: keep `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/hooks/scripts/progress_manager.py` as the CLI facade, but extract new collaborators behind it:

- `transaction_manager.py`
- `schema_migration.py`
- `state_reconciler.py`
- `contract_importer.py`
- `readiness_validator.py`
- `lifecycle_service.py`
- `finish_gate.py`
- `summary_projector.py`

This preserves command compatibility while isolating the highest-risk code paths.

### Part 1 to Part 4 Mapping

The Part 4 table contains a coarse mapping, but it conflates closeout MVP work with normalization-core work. The normalized mapping below is the recommended execution mapping for implementation.

| Part 1 Macro Stage | Intent | Part 4 Execution Stages | Why |
| --- | --- | --- | --- |
| Stage 1: Migration Safety Foundation | Make old data safe to read/write before any workflow behavior changes | 1, 2, 3, 4 | These are all prerequisite safety rails: failing baseline, transaction layer, schema backfill, and compatibility repair |
| Stage 2: Closeout Pain MVP | Fix `/prog-done` and unresolved integration tails | 8, 12 (closeout regression slice) | Only Stage 8 directly implements finish-gate behavior; Stage 12 validates it end-to-end before release |
| Stage 3: Normalization Core | Make contracts, readiness, lifecycle, and audit data first-class | 5, 6, 7, 9 | Contract import, readiness gating, lifecycle transitions, and refs/audit enrichment are the core normalization behaviors |
| Stage 4: Enhancement and Performance | Speed, docs, and release hardening | 10, 11, 12 (performance/docs slice) | Summary projection, doc/help sync, and final regression complete the release-quality layer |

Inference from Part 1, Part 3 v2, and Part 4:

- Stage 5-7 belong to the normalization core, not the closeout MVP, because they implement contract/readiness/lifecycle semantics rather than finish-gate resolution.
- Stage 12 is shared validation capacity; it should be partitioned across Stage 2 and Stage 4 acceptance, not treated as a standalone business capability.

### Critical Integration Points

| Area | Primary Files | Integration Role |
| --- | --- | --- |
| State facade | `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/hooks/scripts/progress_manager.py` | Stable CLI facade; delegates all mutating work to extracted services |
| Commands | `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/commands/prog-init.md`, `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/commands/prog-start.md`, `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/commands/prog-done.md`, `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/commands/prog-next.md`, `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/commands/prog-plan.md` | Preserve thin command wrappers while updating downstream skill and CLI expectations |
| Tests | `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/tests/` | Contract suite and risk-based regression harness |
| Docs | `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/README.md`, `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/docs/PROG_COMMANDS.md`, `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/docs/ARCHITECTURE.md`, `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/hooks/scripts/generate_prog_docs.py`, `/Users/siunin/Projects/claude-plugins-beta/docs/progress-tracker/architecture/architecture.md` | Public contract, generated help, and downstream architecture source for `/prog-init` |

## Interface Contracts

### State Contract: `progress.json` Schema 2.1

Top-level fields:

- `schema_version: "2.1"`
- `validation_policy`
- `features[]`
- `retrospectives[]`
- `updates[]`
- existing legacy fields remain present for compatibility

Feature contract:

- Required canonical fields:
  - `id`
  - `name`
  - `lifecycle_state`
  - `requirement_ids`
  - `change_spec`
  - `acceptance_scenarios`
  - `acceptance_results`
  - `integration_status`
  - `cleanup_status`
- Required legacy mirrors:
  - `development_stage`
  - `completed`
- Optional but durable:
  - `integration_ref`
  - `finish_reason`
  - `archive_info`
  - `ai_metrics`
  - `verification`
  - `owners`

Canonical truth rules:

- `lifecycle_state` is the source of truth.
- `development_stage` and `completed` are derived mirrors.
- `integration_status` and `cleanup_status` are the source of truth for closeout state.
- `archive_info` records archive operations only.
- `retrospectives[]` stores retrospective narratives and action items; it must not be folded into `archive_info`.

### Command Contracts

#### `/prog-init`

- Input: project goal plus optional feature seed derived from this architecture.
- Output: initialized `progress.json`, `progress.md`, feature list, and next-step recommendation.
- Must read this file before feature generation when it exists.

#### `/prog-start`

- Input: current feature in `approved/planning` state.
- Output: transition to `implementing/developing` only if readiness blocking checks pass.
- Failure result: readable report listing blocking vs warning issues.

#### `/prog-done`

- Input: active feature in execution-complete state and validated plan/test evidence.
- Output:
  - `verified` plus final integration outcome, or
  - `verified + finish_pending` with an actionable next step.
- Must not silently skip finish-gate persistence.

#### `/prog-next`

- Input: active project state.
- Output: next feature selection only when no unresolved finish-gate block exists.
- Failure result: explicit remediation path for pending finish or cleanup.
- Scope rule: in a monorepo root or any workspace with multiple candidate trackers, mutating `/prog-*` flows must require explicit target scope and must not resume whichever tracker is most recently active elsewhere.

#### `status` and UI summary

- Input: `progress.json` and optionally `progress_summary.json`.
- Output: consistent summary view; if projection checksum mismatches, rebuild before display.

### Workspace Scope Contract

Supported scope modes:

- `single-project mode`: current working directory already resolves to one project root; mutating and read-only commands may proceed.
- `explicit child-scope mode`: command is run from a monorepo root with `--project-root plugins/<name>` (or equivalent explicit selector); mutating and read-only commands may proceed for that target only.
- `coordination mode`: a root-level tracker or future workspace manifest coordinates several linked projects; cross-project work is explicit and never inferred from whichever child tracker happened to be active last.

Required behavior:

- Mutating commands fail closed on ambiguous scope.
- Read-only commands may present an aggregated overview or a list of candidate scopes, but must not mutate state until a target scope is explicit.
- Cross-project or linked-project work must be represented either as:
  - one explicit coordination tracker at the root, or
  - separate per-project trackers invoked with explicit scope.

Inference:

- This does not forbid using `prog` from the monorepo root.
- It forbids implicit mutation from the monorepo root when more than one tracker could be targeted.
- Linked projects remain supported, but the coordination boundary has to be explicit instead of inferred.

### Internal Service Contracts

#### `transaction_manager.atomic_update(mutation, reason, correlation_id=None) -> dict`

- Reads, locks, mutates, validates, writes, and audits in one controlled path.
- Writes `progress.json`, `progress_summary.json`, and `progress.md` in a deterministic order.

#### `schema_migration.apply_defaults(data) -> dict`

- Adds schema `2.1` defaults and preserves unknown fields.
- Never destroys newer fields when `PROG_DISABLE_V2=1`.

#### `readiness_validator.validate_feature_readiness(feature, policy) -> report`

- Returns `{"valid": bool, "errors": [...], "warnings": [...]}`.
- Blocking items gate `/prog-start`; warnings do not.

#### `finish_gate.apply(feature_id, requested_status=None, reason=None) -> result`

- Enforces legal `lifecycle_state` and `integration_status` combinations.
- Produces one of:
  - `merged_and_cleaned`
  - `pr_open`
  - `kept_with_reason`
  - `finish_pending`

#### `summary_projector.rebuild_if_stale() -> summary`

- Regenerates projection if checksum or transaction markers do not match the source state.

### Test Contract Families

- Backfill and lifecycle tests extend `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/tests/test_feature_contract_readiness.py`.
- Legacy compatibility tests preserve `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/tests/test_feature_completion_state_transition.py`.
- Transaction and write-path tests expand `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/tests/test_progress_manager.py`.
- UI summary correctness continues through `/Users/siunin/Projects/claude-plugins-beta/plugins/progress-tracker/tests/test_progress_ui_status.py`.

## State Flow

### Feature Lifecycle Flow

Canonical feature flow:

`proposed -> approved -> implementing -> verified -> archived`

Legacy mirrors:

- `proposed|approved -> development_stage=planning, completed=false`
- `implementing -> development_stage=developing, completed=false`
- `verified|archived -> development_stage=completed, completed=true`

### Integration Flow

Allowed combinations:

| `lifecycle_state` | `integration_status` | Meaning |
| --- | --- | --- |
| `proposed` | `finish_pending` | Not started, no closeout |
| `approved` | `finish_pending` | Ready to start |
| `implementing` | `finish_pending` | Work in progress |
| `verified` | `finish_pending` | Feature passed verification but integration decision remains open |
| `verified` | `merged_and_cleaned` | Merged and cleanup complete |
| `verified` | `pr_open` | PR opened and tracked |
| `verified` | `kept_with_reason` | Branch/worktree intentionally kept with explanation |
| `archived` | `merged_and_cleaned` | Archive finalized after clean merge |
| `archived` | `kept_with_reason` | Archive finalized with retained worktree/branch rationale |

Illegal combinations are repaired or rejected:

- `archived + finish_pending`
- `implementing + merged_and_cleaned`
- `proposed + merged_and_cleaned`

### Command-Driven State Transitions

1. `/prog-init`
   - creates features in `approved + finish_pending`
   - writes schema defaults and legacy mirrors
2. `/prog-next`
   - selects current feature
   - blocks if any feature remains `verified + finish_pending`
3. `/prog-start`
   - runs readiness validation
   - transitions `approved -> implementing`
4. `/prog-done`
   - validates plan and acceptance evidence
   - transitions `implementing -> verified`
   - immediately applies finish-gate outcome or persists `finish_pending`
5. `prog-set-finish-state` (internal)
   - resolves `verified + finish_pending` to a terminal integration status
6. archive/retro flows
   - archive writes remain separate from retrospectives
   - successful archival may advance `verified -> archived`

Inference from Part 1 and Part 3 v2:

- `/prog-done` must persist `verified + finish_pending` when a closeout decision is unresolved. Part 3 v2 pseudo-code suggests returning a pending decision without persisting state, but that would break Part 1's requirement that `/prog-next` deterministically block unresolved closeout work. The persisted pending state is therefore the recommended normalized behavior.

### Delivery Flow Across the 12 Execution Stages

1. Baseline failing tests
2. Transaction layer and lock
3. Schema 2.1 backfill
4. Reconciler and downgrade safety
5. Contract importer
6. Readiness validator
7. Lifecycle API
8. Finish gate
9. Refs enrichment
10. Summary projection
11. Command/doc sync
12. Full regression and release report

## Failure Handling

### Transaction Write Path

Risk:

- Partial writes, concurrent writes, corrupted JSON, or audit/state divergence.

Design:

- Lock file around every mutating operation.
- Pre-commit backup or write-ahead snapshot.
- `fsync(tmp) -> os.replace(...) -> fsync(parent_dir)` durability chain.
- Audit update and summary projection happen inside the same transaction boundary or under the same transaction marker.

User-visible behavior:

- Mutating command fails with a readable error and no half-written state.
- Recovery command can restore from latest pre-commit or daily backup.

### Migration Compatibility

Risk:

- Legacy `development_stage/completed` states diverge from canonical `lifecycle_state`.
- `PROG_DISABLE_V2=1` strips or corrupts 2.1 fields.

Design:

- Read path infers missing canonical fields from legacy fields.
- Write path always writes canonical fields first, then mirrors.
- Reconciler runs at every mutating entry point.
- Downgrade mode preserves unknown/newer fields verbatim.

User-visible behavior:

- Conflict reports mention repaired fields and leave an audit trail.
- Downgrade mode prints explicit warnings but does not destroy data.

### `/prog-done` Closeout Gate

Risk:

- Feature marked complete while merge/PR/worktree status remains unresolved.
- `/prog-next` advances and leaves integration debt behind.

Design:

- Verification completion and finish-gate persistence happen in one logical flow.
- Missing final decision yields `verified + finish_pending`.
- `/prog-next` hard-blocks on unresolved closeout.

User-visible behavior:

- Clear next command, for example `prog-set-finish-state --feature-id <id> --status pr_open`.
- No silent advancement to the next feature.

### Worktree Cleanup

Risk:

- Deleting a dirty or current worktree causes irreversible loss.

Design:

- Only use `git worktree remove` or equivalent git-native flows.
- Never auto-delete:
  - dirty worktree
  - current worktree
  - worktree with unpushed commits
- Persist `cleanup_status=pending` when human intervention is required.

User-visible behavior:

- Explicit cleanup instructions with path, reason, and safe retry steps.

### Summary Consistency

Risk:

- `status`, UI, and markdown drift away from canonical JSON.

Design:

- `progress_summary.json` carries source checksum and transaction marker.
- Reads validate checksum before trusting projection.
- Rebuild projection on mismatch, then regenerate markdown if required.

User-visible behavior:

- Slightly slower first read after mismatch, but no stale summary output.

### Scope Ambiguity and Linked Projects

Risk:

- Running `/prog-next` or `/prog-done` from a monorepo root can mutate the wrong tracker if scope is inferred implicitly.
- Linked projects can accidentally bleed state into each other if root-level commands are treated as global by default.

Design:

- Mutating commands (`init`, `next`, `start`, `done`, `set-current`, `set-development-stage`, `complete`, `add-feature`, `update-feature`, `add-update`, bug mutations, workflow mutations) must fail closed when scope is ambiguous.
- Read-only commands may show available project scopes from the root, but must request explicit selection before any mutation.
- Linked projects should use one of two explicit patterns:
  - a root-level coordination tracker that references child projects, or
  - independent child trackers invoked with explicit `--project-root`.

User-visible behavior:

- From the root directory, `prog status` may summarize or ask the user to choose a target.
- From the root directory, `prog next` must error with explicit scope guidance instead of resuming another project's active feature.
- From linked-project setups, the user can still operate at the root, but only through explicit target selection or a defined coordination scope.

### Contract Import and Readiness

Risk:

- Invalid JSON/Markdown contracts can wedge CLI or create partially valid features.

Design:

- JSON parser with structural validation.
- Markdown line-state parser, not a backtracking-heavy regex strategy.
- Blocking vs warning separation in readiness policy.

User-visible behavior:

- Precise error location and remediation hints.
- Warning-only checks do not block normal flow until policy says they should.

## Acceptance Criteria

### System-Level Acceptance

- All mutating PROG flows use the transaction manager; no direct semantic writes bypass audit and summary projection.
- Legacy users can still complete `planning -> developing -> completed` flows without data loss.
- New schema 2.1 tests pass for lifecycle, readiness, retro separation, and automatic refs attachment.
- `/prog-done` cannot leave an untracked closeout state.
- Dirty/current worktrees are never auto-removed.
- `status`, UI summary, and markdown stay consistent with canonical JSON after drift repair.
- Ambiguous monorepo-root mutation attempts fail closed and provide explicit scope remediation.
- Linked-project development remains supported through explicit child scope or an explicit coordination tracker.

### High-Risk Acceptance Matrix

| Risk Area | Acceptance Rule |
| --- | --- |
| Transaction write path | Concurrent writes do not lose updates or corrupt JSON |
| Migration compatibility | `PROG_DISABLE_V2=1` reads/writes schema 2.1 safely without stripping fields |
| `/prog-done` gate | Every completion ends as `finish_pending`, `merged_and_cleaned`, `pr_open`, or `kept_with_reason` |
| Worktree cleanup | Dirty/current/unpushed worktrees remain intact and are surfaced as pending cleanup |
| Summary consistency | Projection checksum mismatch triggers rebuild before status output |
| Scope safety | Ambiguous root-level mutating commands error before touching state; explicit scope continues to work |

### `/prog-init` Feature List Recommendation

The list below is intentionally aligned to the 12 execution stages so it can seed a full normalization track directly.

| # | Suggested Feature | Primary Goal | Seed Test Steps | Constraints | Contract Touchpoints |
| --- | --- | --- | --- | --- | --- |
| 1 | Establish normalization red baseline | Lock current gap with failing tests and golden fixtures | Run `pytest -q plugins/progress-tracker/tests/test_feature_contract_readiness.py`; confirm failures map to lifecycle/readiness/retro/refs gaps; add fixtures for legacy 2.0 payloads; add monorepo-root ambiguity reproducer for wrong-scope `/prog-next` | `CONSTRAINT-001`, `CONSTRAINT-012`, `CONSTRAINT-013` | State contract, failure handling |
| 2 | Add transaction manager and locked write pipeline | Centralize mutating writes behind one atomic path | Add concurrent write test; verify backup plus rollback behavior; verify update plus summary write share one transaction marker | `CONSTRAINT-001`, `CONSTRAINT-006`, `CONSTRAINT-008` | Internal service contracts, transaction path |
| 3 | Backfill schema 2.1 defaults and validation policy | Upgrade load/save path to canonical schema | Load legacy 2.0 fixture and assert schema 2.1 defaults; verify IDs/timestamps; assert unknown fields survive save/load | `CONSTRAINT-002`, `CONSTRAINT-003` | State contract |
| 4 | Reconcile legacy state and support downgrade mode | Repair mirror-field drift and preserve 2.1 under disable flag | Toggle `PROG_DISABLE_V2=1`; round-trip a 2.1 payload; assert canonical-to-legacy mirror repair; assert ambiguous monorepo-root mutation fails closed while explicit `--project-root` continues to work | `CONSTRAINT-002`, `CONSTRAINT-003`, `CONSTRAINT-013` | State flow, migration handling |
| 5 | Implement contract importer for JSON and Markdown specs | Auto-populate feature contract fields from design inputs | Parse valid JSON spec; parse Markdown spec with heading variants; reject malformed input without CLI hang | `CONSTRAINT-010`, `CONSTRAINT-012` | Interface contracts, failure handling |
| 6 | Add readiness validator and `/prog-start` gating | Block invalid feature starts with precise reports | Assert blocking errors for empty `requirement_ids`; assert warnings stay non-blocking; assert `/prog-start` fails when blocking checks exist | `CONSTRAINT-004`, `CONSTRAINT-012` | Command contracts, readiness |
| 7 | Introduce lifecycle API with legal transition rules | Make `lifecycle_state` canonical and auditable | Assert `approved -> implementing -> verified`; reject illegal transitions; verify mirror fields update correctly | `CONSTRAINT-003`, `CONSTRAINT-005`, `CONSTRAINT-009` | State flow, audit |
| 8 | Implement `/prog-done` finish gate and pending-closeout block | Close the main gap around unresolved integration tails | Complete a feature and assert `verified + finish_pending`; resolve via internal finish-state command; assert `/prog-next` blocks until resolved | `CONSTRAINT-005`, `CONSTRAINT-006`, `CONSTRAINT-007` | Command contracts, finish gate |
| 9 | Auto-attach refs and enrich audit updates | Keep change and requirement traceability intact | Add update on a feature and assert `req:*` and `change:*` refs; verify manual refs are preserved; verify overflow handling | `CONSTRAINT-009`, `CONSTRAINT-012` | Interface contracts, audit |
| 10 | Add summary projection and drift repair | Make status output fast and consistent | Generate `progress_summary.json`; inject checksum drift; assert rebuild before status/UI response | `CONSTRAINT-008`, `CONSTRAINT-012` | Summary contract, failure handling |
| 11 | Sync commands and generated docs with normalized behavior | Keep user-visible command help aligned | Update `prog-done`, `prog-start`, `prog-plan`, and generated docs; document root-vs-child scope semantics for monorepo and linked projects; run `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check` | `CONSTRAINT-011`, `CONSTRAINT-012`, `CONSTRAINT-014` | Commands, docs |
| 12 | Run full regression and produce release readiness report | Validate safety, compatibility, and residual risk | Run full `plugins/progress-tracker/tests`; run focused migration/finish/worktree/summary/scope suites; record residual risks and rollback plan | `CONSTRAINT-012`, `CONSTRAINT-013`, `CONSTRAINT-014` | All contracts |

Recommended execution order:

1. Features 1-4 form the migration safety foundation.
2. Features 5-7 establish normalized contract and lifecycle behavior.
3. Feature 8 is the closeout MVP milestone and should be release-gated.
4. Features 9-12 harden audit, performance, docs, and release confidence.

## Key Architectural Decisions (ADR)

### ADR-001: Keep `progress_manager.py` as the facade and extract collaborators

**Status**: Accepted

**Context**: The current CLI surface is anchored in a single Python entrypoint, but the file is already large and mixes persistence, workflow, git, UI summary, and business rules.

**Decision**: Preserve the CLI facade in `progress_manager.py` and move normalization logic into focused modules that the facade orchestrates.

**Consequences**:
- Positive: command compatibility remains stable; higher-risk code becomes easier to test in isolation.
- Negative: the plugin remains a modular monolith rather than a fully separated package.
- Risks: partial extraction can leave mixed patterns if not enforced with constraints.

**Alternatives Considered**:
1. Rewrite the CLI into multiple standalone scripts - rejected because command compatibility cost is too high.
2. Keep all new logic in `progress_manager.py` - rejected because testability and write-path safety would degrade further.

### ADR-002: Make schema 2.1 canonical and keep legacy fields as mirrors

**Status**: Accepted

**Context**: Existing users and tests still rely on `development_stage` and `completed`, but the new design needs richer state modeling.

**Decision**: Treat `lifecycle_state`, `integration_status`, and `cleanup_status` as truth; preserve legacy fields as derived mirrors.

**Consequences**:
- Positive: new behavior is expressive without breaking old flows.
- Negative: reconciler logic is required on every mutating path.
- Risks: drift if any write bypasses canonical-state synchronization.

**Alternatives Considered**:
1. Hard-cut to 2.1 and drop legacy fields - rejected because current passing tests and user workflows still depend on them.
2. Keep legacy fields as truth - rejected because finish-gate and lifecycle rules become ambiguous.

### ADR-003: Enforce one transactional write path for state, audit, and summary

**Status**: Accepted

**Context**: Current direct writes are simple but unsafe for future concurrency, rollback, and audit consistency needs.

**Decision**: All semantic writes must go through the transaction manager, which owns lock acquisition, durability, audit append, and summary update.

**Consequences**:
- Positive: reliable recovery and deterministic state.
- Negative: implementation is more complex than plain file writes.
- Risks: some legacy helper may continue using `save_progress_json(...)` directly unless explicitly forbidden.

**Alternatives Considered**:
1. Keep direct writes and patch specific hot paths - rejected because audit and summary would still drift.
2. Move to SQLite immediately - rejected because it is outside the current normalization scope.

### ADR-004: Persist `finish_pending` as the canonical unresolved closeout state

**Status**: Accepted

**Context**: The design requires `/prog-next` to block unresolved finish work, but an unpersisted pending decision cannot be enforced across sessions.

**Decision**: `/prog-done` writes `verified + finish_pending` when it cannot determine or complete a terminal integration outcome immediately.

**Consequences**:
- Positive: unresolved closeout is visible, durable, and blockable.
- Negative: users may see a new intermediate state they must resolve.
- Risks: hidden helper commands must stay well documented internally.

**Alternatives Considered**:
1. Return a pending decision without persisting state - rejected because it cannot reliably block `/prog-next`.
2. Auto-guess a terminal state - rejected because it can incorrectly delete or close work.

### ADR-005: Use git-native cleanup only and never auto-delete unsafe worktrees

**Status**: Accepted

**Context**: Closeout safety is explicitly called out as a high-risk area.

**Decision**: Cleanup uses git-native worktree commands only, and dirty/current/unpushed worktrees are marked pending rather than removed.

**Consequences**:
- Positive: far lower risk of destructive cleanup.
- Negative: some cleanup remains manual.
- Risks: unresolved cleanup can accumulate unless status and daily checks surface it clearly.

**Alternatives Considered**:
1. Force-delete worktrees after feature completion - rejected because it is unsafe.
2. Ignore cleanup entirely - rejected because closeout debt would remain invisible.

### ADR-006: Treat `progress_summary.json` as a rebuildable cache, not a source of truth

**Status**: Accepted

**Context**: Summary acceleration is required, but any duplicated state risks drift.

**Decision**: Summary projection is derived from canonical JSON and validated by checksum plus transaction marker before use.

**Consequences**:
- Positive: faster reads without semantic ambiguity.
- Negative: projection rebuild logic adds operational complexity.
- Risks: status reads become slower during repeated rebuilds if write discipline is not maintained.

**Alternatives Considered**:
1. Use summary as the primary status source without validation - rejected because stale status becomes user-visible.
2. Skip summary projection entirely - rejected because large-project performance was called out explicitly in the design.

### ADR-007: Fail closed on ambiguous scope and require explicit coordination for linked projects

**Status**: Accepted

**Context**: The reported `/prog-next` behavior showed that a user can believe they are operating on one project while the command resumes an already-active feature from another tracker. That is acceptable neither for monorepo safety nor for linked-project development.

**Decision**: Mutating commands must require an explicit target whenever multiple tracker scopes are possible. Root-level development remains allowed, but only through explicit child scope or an explicit coordination tracker.

**Consequences**:
- Positive: wrong-project mutation is prevented by design.
- Positive: linked projects remain viable without sacrificing safety.
- Negative: users lose the convenience of implicit root-level mutation in ambiguous workspaces.
- Risks: command wrappers and skills must consistently pass scope, or they will fail noisily.

**Alternatives Considered**:
1. Allow implicit mutation from the most recently active tracker - rejected because it is unsafe and non-local.
2. Forbid root-level `prog` usage entirely - rejected because linked-project and monorepo orchestration remain legitimate workflows.

## Execution Constraints

- [CONSTRAINT-001] Route every semantic state mutation through one transaction manager
  - Applies to: `progress_manager.py`, extracted services, mutating CLI commands
  - Must: avoid direct semantic `save_progress_json(...)` writes outside the transaction layer
  - Validation: `rg -n "save_progress_json\\(" plugins/progress-tracker/hooks/scripts` should show only non-semantic or transaction-owned writes after refactor
- [CONSTRAINT-002] Preserve schema 2.1 fields under downgrade mode
  - Applies to: schema migration, reconciler, load/save paths
  - Must: keep unknown/newer fields intact when `PROG_DISABLE_V2=1`
  - Validation: round-trip tests with downgrade flag enabled
- [CONSTRAINT-003] Treat canonical lifecycle fields as the only source of truth
  - Applies to: feature state transitions, migration, status rendering
  - Must: derive `development_stage` and `completed` from `lifecycle_state`, not the reverse
  - Validation: lifecycle tests assert mirror repair after conflict injection
- [CONSTRAINT-004] Block `/prog-start` on readiness errors and allow warnings only by policy
  - Applies to: readiness validator, `/prog-start`, feature start flows
  - Must: reject start when blocking checks fail
  - Validation: readiness contract tests and command-flow tests
- [CONSTRAINT-005] Block `/prog-next` when unresolved finish work exists
  - Applies to: `/prog-next`, finish gate, status recommendations
  - Must: stop advancement when any active feature remains `verified + finish_pending` or pending cleanup that policy marks blocking
  - Validation: finish-gate regression tests
- [CONSTRAINT-006] Persist verification, finish-gate state, and audit update in one logical completion flow
  - Applies to: `/prog-done`, `complete_feature`, transaction manager
  - Must: never mark a feature verified without also recording terminal closeout state or durable `finish_pending`
  - Validation: end-to-end `/prog-done` tests and audit assertions
- [CONSTRAINT-007] Never auto-delete dirty, current, or unpushed worktrees
  - Applies to: worktree cleanup, git integration helpers
  - Must: require manual intervention and leave `cleanup_status=pending`
  - Validation: worktree cleanup tests with dirty/current/unpushed fixtures
- [CONSTRAINT-008] Validate summary projection before read
  - Applies to: status command, progress UI, summary projector
  - Must: rebuild `progress_summary.json` when checksum or transaction marker mismatches
  - Validation: summary drift tests and UI status tests
- [CONSTRAINT-009] Auto-enrich audit updates with feature references
  - Applies to: `add_update`, lifecycle updates, finish-gate updates
  - Must: attach `req:*` and `change:*` refs for feature-bound updates without dropping manual refs
  - Validation: update reference tests
- [CONSTRAINT-010] Keep retrospectives separate from archive bookkeeping
  - Applies to: retro APIs, archive logic, schema defaults
  - Must: store retrospectives at top-level `retrospectives[]` and reserve `archive_info` for file/archive metadata only
  - Validation: retro separation tests
- [CONSTRAINT-011] Keep public command help minimal and consistent
  - Applies to: command markdown, README, generated docs
  - Must: expose only approved public commands while keeping internal repair commands out of primary help output
  - Validation: generated docs check and command discovery tests
- [CONSTRAINT-012] Every macro stage must land with dedicated regression coverage
  - Applies to: test suite, release readiness
  - Must: add targeted tests for migration, concurrency, finish-gate, worktree cleanup, refs, and summary consistency
  - Validation: full `plugins/progress-tracker/tests` run and release report
- [CONSTRAINT-013] Mutating commands must fail closed on ambiguous project scope
  - Applies to: slash commands, `progress_manager.py`, skill wrappers, monorepo-root invocations
  - Must: require explicit target scope whenever multiple tracker roots are plausible
  - Validation: regression tests that run from monorepo root and assert `next/start/done` error without `--project-root`
- [CONSTRAINT-014] Linked-project coordination must be explicit, not inferred
  - Applies to: root-level workflows, future coordination tracker, documentation
  - Must: support either explicit child-scope commands or an explicit coordination tracker for multi-project work
  - Validation: docs and tests cover both independent child trackers and explicit coordination behavior
