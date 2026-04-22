# Architecture: Progress Tracker SOP Compliance Optimization (WF + Token + Bug)

**Created**: 2026-04-23
**Last Updated**: 2026-04-23
**Planning Source**: `/Users/siunin/.claude/plans/prancy-wandering-wren.md`

## Goals

- Establish a stable primary workflow for Progress Tracker: `/prog plan -> /prog init -> /prog next -> /prog done -> /prog sync`.
- Reduce routing ambiguity by standardizing skill `description` fields to trigger-oriented phrasing.
- Reduce default token usage by applying progressive disclosure to oversized `SKILL.md` files.
- Remove high-risk metadata and standards drift that causes repeated rollback loops.
- Define machine-verifiable quality gates so execution can be batched and audited.

Assumptions:
- This planning scope targets the `progress-tracker` plugin first, then applies to sibling plugins (`super-product-manager`, `package-manager`, `note-organizer`) through follow-up execution batches.
- Current repository baseline counts in the source draft are treated as authoritative starting metrics for execution planning.

## Scope Boundaries

In scope:
- Skill frontmatter and description normalization for routable command/skill invocation.
- Plugin metadata completion in `.claude-plugin/plugin.json` (`homepage`, `repository`).
- Progressive disclosure refactor for oversized skill documents.
- Validation and drift-prevention gates for docs and sync paths.
- Workflow definition and command-role boundary hardening.

Out of scope:
- Re-architecting runtime business logic inside `progress_manager.py` unrelated to SOP compliance and workflow consistency.
- Migrating from file-based plugin/docs storage to external services.
- UI redesign work outside command/help clarity and generated documentation consistency.

Boundary rule:
- Architecture file is the master contract and must not be archived/mutated as part of feature closeout flows.

## Interface Contracts

### Contract A: Skill Metadata Contract

Input type:
- `skills/*/SKILL.md` with YAML frontmatter.

Output type:
- SOP-compliant frontmatter with routable description.

Required output fields:
- `name: string`
- `description: string` (must include trigger phrase such as `This skill should be used when ...` or `Use when ...`)

Recommended output fields:
- `model: string`
- `version: string`
- `references: string[]`

Prohibited output fields:
- `scope`, `inputs`, `outputs`, `evidence`

### Contract B: Plugin Metadata Contract

Input type:
- `.claude-plugin/plugin.json`

Output type:
- Plugin metadata object with traceability fields.

Required fields:
- `homepage: string`
- `repository: string`

### Contract C: Command Help Single-Source Contract

Input type:
- `docs/PROG_COMMANDS.md`

Output type:
- Generated parity in:
  - `README.md`
  - `readme-zh.md`
  - `docs/PROG_HELP.md`

Validation interface:
- `python3 hooks/scripts/generate_prog_docs.py --check` exits `0` on parity, non-zero on drift.

### Contract D: Architecture Handoff Contract

Input type:
- `/prog plan <goal>`

Output type:
- `docs/progress-tracker/architecture/architecture.md` containing:
  - Goals
  - Scope Boundaries
  - Interface Contracts
  - State Flow
  - Failure Handling
  - Acceptance Criteria
  - Key Architectural Decisions (ADR)
  - Execution Constraints

Downstream read contract:
- `/prog init` and feature planning/execution skills must read this architecture file when present.
- Downstream artifacts must reference at least one `CONSTRAINT-*` ID per implemented feature.

## State Flow

### Workflow State Machine (Command Level)

1. `planned`
   - Trigger: `/prog plan`
   - Exit to: `initialized`
2. `initialized`
   - Trigger: `/prog init`
   - Exit to: `executing`
3. `executing`
   - Trigger: `/prog next`
   - Exit to: `completed`
4. `completed`
   - Trigger: `/prog done`
   - Exit to: `synced`
5. `synced`
   - Trigger: `/prog sync`
   - Terminal for current execution batch.

### Compliance State Machine (SOP Migration Level)

1. `baseline_scanned`
   - Existing counts and hotspots captured.
2. `normalized`
   - Frontmatter/description/metadata corrected in target scope.
3. `validated`
   - Required checks pass (docs parity, metadata gates, sync dry-run).
4. `released`
   - Changes merged and documented.

Error states:
- `blocked_standard_conflict`: standards source contradicts SOP contract.
- `blocked_metadata_gap`: required metadata fields missing.
- `blocked_docs_drift`: generated doc outputs are stale.
- `blocked_sync`: sync dry-run reports blocking errors.

Transition rule:
- Any error state returns flow to `normalized` after correction; no direct transition to `released` is permitted from an error state.

## Failure Handling

| Failure mode | Detection | System response | User-visible behavior |
|---|---|---|---|
| SOP rule conflict (e.g., standards demand prohibited fields) | Contract lint or review checklist mismatch | Block merge and require standards source-of-truth reconciliation | Explicit blocker message with conflicting field names |
| Non-routable skill description | Routing phrase scan fails | Mark skill as non-compliant; do not accept execution batch | Report exact file list and missing trigger phrases |
| Missing `homepage/repository` in plugin metadata | JSON schema check or targeted scan | Block release until fields are added | Report plugin file path and missing keys |
| Missing `model` in required skill set | Frontmatter scan | Mark as P0 metadata defect and halt batch | Report exact skills requiring `model` |
| Generated docs drift | `generate_prog_docs.py --check` non-zero | Fail validation gate | Show command to regenerate docs and rerun check |
| Sync compatibility failure | `codex-plugin-sync --dry-run` shows blocking errors | Stop release and create remediation task | Present dry-run failure summary and impacted plugin scope |

Failure policy:
- Fail closed for release gates.
- Keep architecture document stable during execution; remediation is applied to implementation artifacts, not planning contract.

## Acceptance Criteria

1. Non-standard frontmatter prohibited-field hits (`scope`, `inputs`, `outputs`, `evidence`) are reduced to `0` in target execution scope.
2. Non-routable skill descriptions are reduced to `0` in target execution scope.
3. `.claude-plugin/plugin.json` files missing `homepage` or `repository` are reduced to `0`.
4. Skills that require explicit model selection (starting with `package-manager` scope in the source draft) have missing `model` count reduced to `0`.
5. Progressive disclosure rollout is applied to identified oversized skills with target `SKILL.md` main-file size `<= 150` lines where feasible.
6. `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check` passes.
7. `python3 plugins/progress-tracker/hooks/scripts/quick_validate.py` passes (or passes with documented waived checks approved in execution notes).
8. `codex-plugin-sync --dry-run` has no blocking errors.

Acceptance evidence requirements:
- Each criterion must have command output or diff-based proof attached in execution notes.
- Each delivered feature/PR must cite related `CONSTRAINT-*` IDs.

## Key Architectural Decisions (ADR)

### ADR-001: Keep a Modular Monolith and File-Based Control Plane

Status: Accepted

Context:
- Optimization target is consistency, routing quality, and token efficiency across skills and docs, not a storage or service rewrite.

Decision:
- Keep existing plugin/file structure and implement compliance through metadata normalization, docs generation gates, and workflow constraints.

Consequences:
- Positive: low migration risk, fast adoption, direct compatibility with current commands.
- Negative: contract enforcement remains dependent on disciplined validation tooling.
- Risks: inconsistent manual edits can reintroduce drift without strict gates.

Alternatives considered:
1. Full service-based metadata registry - rejected due to unnecessary complexity for current problem.
2. Per-plugin independent standards without central contract - rejected because it preserves drift risk.

### ADR-002: Enforce Trigger-Oriented Skill Descriptions as Routing API

Status: Accepted

Context:
- Description ambiguity causes incorrect skill selection and unnecessary token spend.

Decision:
- Treat frontmatter `description` as a routing contract with required trigger phrases.

Consequences:
- Positive: higher route determinism and lower misfire rate.
- Negative: additional maintenance burden when introducing new skills.
- Risks: over-constrained phrasing may miss nuanced user intent if not reviewed periodically.

Alternatives considered:
1. Leave free-form descriptions - rejected due to high routing variance.
2. Add only informal examples without hard rule - rejected because it is not machine-verifiable.

### ADR-003: Progressive Disclosure as Default Token Strategy

Status: Accepted

Context:
- Multiple oversized skill files inflate default context payload and slow execution.

Decision:
- Keep core routing and constraints in main `SKILL.md`; move examples/templates/long references to `references/` and load on demand.

Consequences:
- Positive: reduced default token consumption and clearer skill entrypoints.
- Negative: slight increase in navigation complexity for deep-reference usage.
- Risks: accidental loss of critical details if extraction boundaries are poorly chosen.

Alternatives considered:
1. Keep all details inline - rejected due to token inefficiency.
2. Split into many small skills immediately - rejected due to route fragmentation risk.

### ADR-004: Fail-Closed Release Gates for SOP Compliance

Status: Accepted

Context:
- Historical pattern shows compliance regressions when checks are advisory only.

Decision:
- Release progression is blocked when validation gates fail (frontmatter, metadata, docs parity, sync dry-run).

Consequences:
- Positive: prevents hidden drift and regression loops.
- Negative: may slow short-term delivery cadence.
- Risks: false positives can create temporary friction without well-maintained checks.

Alternatives considered:
1. Warning-only gates - rejected because they do not prevent repeated regressions.
2. Manual reviewer discretion without machine checks - rejected as non-scalable and non-deterministic.

## Execution Constraints

- [CONSTRAINT-001] Enforce SOP-compliant skill frontmatter shape
  - Applies to: `plugins/*/skills/*/SKILL.md`
  - Must: include `name` and routable `description`; must not include `scope/inputs/outputs/evidence`
  - Validation: frontmatter scan returns zero prohibited-field hits and zero missing-required hits

- [CONSTRAINT-002] Enforce routable description phrasing
  - Applies to: all skill frontmatter `description`
  - Must: use trigger-oriented phrasing (`This skill should be used when ...` or `Use when ...`)
  - Validation: description pattern scan reports zero non-compliant files

- [CONSTRAINT-003] Complete plugin traceability metadata
  - Applies to: `plugins/*/.claude-plugin/plugin.json`
  - Must: include both `homepage` and `repository`
  - Validation: JSON key audit reports zero missing keys

- [CONSTRAINT-004] Require explicit model declaration where model routing is mandatory
  - Applies to: required skill scopes (starting with `package-manager` items identified in baseline)
  - Must: include `model` in frontmatter for all required files
  - Validation: targeted frontmatter scan reports zero missing `model`

- [CONSTRAINT-005] Keep architecture as immutable planning authority during execution
  - Applies to: `docs/progress-tracker/architecture/architecture.md`
  - Must: no `/prog done` or feature-closeout flow mutates/archives this file
  - Validation: closeout flow checklist and diff review show no architecture mutation

- [CONSTRAINT-006] Apply progressive disclosure budget to oversized skills
  - Applies to: oversized `SKILL.md` files in execution batch
  - Must: main `SKILL.md` stays at or below 150 lines where feasible; long examples/templates move to `references/`
  - Validation: line-count audit and reference-path integrity checks pass

- [CONSTRAINT-007] Preserve docs single-source parity
  - Applies to: `docs/PROG_COMMANDS.md`, `README.md`, `readme-zh.md`, `docs/PROG_HELP.md`
  - Must: generated docs remain synchronized with source-of-truth document
  - Validation: `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check` exits `0`

- [CONSTRAINT-008] Keep command responsibility boundaries strict
  - Applies to: `/prog plan`, `/prog init`, `/prog next`, `/prog done`, `/prog sync`
  - Must: each command only handles its defined lifecycle responsibility; no cross-responsibility side effects
  - Validation: command contract tests and wrapper docs review pass

- [CONSTRAINT-009] Release gates fail closed
  - Applies to: execution batch completion and merge readiness
  - Must: unresolved compliance errors block release
  - Validation: gate report includes pass/fail status for all acceptance criteria and no unresolved blockers

- [CONSTRAINT-010] Preserve codex-plugin-sync compatibility
  - Applies to: wrapper/codex-plugin dual-mode migration path
  - Must: optimized metadata/docs remain compatible with sync workflow
  - Validation: `codex-plugin-sync --dry-run` completes without blocking errors
