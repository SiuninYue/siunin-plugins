# SPM x PROG Beta Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a beta-grade integration where SPM meeting workflows sync structured updates and role assignments into PROG.

**Architecture:** Keep command files thin, centralize state mutation in `progress_manager.py`, and route all cross-plugin writes through a dedicated SPM bridge script. Use strict schema validation with backward-compatible defaults for existing `progress.json`.

**Tech Stack:** Markdown command contracts, Python 3 scripts (`progress_manager.py`, bridge helper), pytest contract/unit/integration tests, generated command docs.

---

### Task 1: Add Failing Tests for PROG Update Schema and CLI

**Files:**
- Modify: `plugins/progress-tracker/tests/test_progress_manager.py`

**Step 1: Write failing tests for schema defaults**

```python
def test_progress_json_backfills_updates_and_owners_defaults(...):
    ...
```

**Step 2: Write failing tests for new CLI subcommands**

```python
def test_add_update_command_writes_update_item(...):
    ...
def test_set_feature_owner_updates_role_owner(...):
    ...
```

**Step 3: Run target tests and verify failure**

Run:
```bash
pytest -q plugins/progress-tracker/tests/test_progress_manager.py -k "update or owner or backfill"
```

Expected: FAIL (missing handlers/fields).

**Step 4: Commit test-only checkpoint**

```bash
git add plugins/progress-tracker/tests/test_progress_manager.py
git commit -m "test(progress-tracker): add failing tests for updates and owners schema"
```

### Task 2: Implement `progress_manager.py` Updates and Owner Commands

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

**Step 1: Add schema backfill helpers**

Implement helpers to ensure:
1. Top-level `updates` exists and is list.
2. Each feature has `owners` with keys `architecture|coding|testing`.

**Step 2: Add CLI handlers**

Implement:
1. `add-update`
2. `list-updates`
3. `set-feature-owner`

**Step 3: Add enum validation**

Reject invalid `category` and `role` with clear error messages.

**Step 4: Run focused tests**

```bash
pytest -q plugins/progress-tracker/tests/test_progress_manager.py -k "update or owner or backfill"
```

Expected: PASS.

**Step 5: Commit implementation**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py
git commit -m "feat(progress-tracker): support updates stream and feature owners"
```

### Task 3: Add `/prog-update` Command + Skill Contracts

**Files:**
- Create: `plugins/progress-tracker/commands/prog-update.md`
- Create: `plugins/progress-tracker/skills/progress-update/SKILL.md`
- Modify: `plugins/progress-tracker/tests/test_command_discovery_contract.py`
- Modify: `plugins/progress-tracker/tests/test_prog_sync_contract.py` (if command catalog assertions require updates)

**Step 1: Add failing contract tests for `prog-update` discovery**

Add assertions that command file exists and is namespaced correctly.

**Step 2: Run contract tests to confirm failure**

```bash
pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py
```

Expected: FAIL before command file exists.

**Step 3: Implement command + skill files**

1. Command frontmatter with hyphenated naming.
2. Skill defines input mapping to `prog add-update`.

**Step 4: Re-run contract tests**

```bash
pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py plugins/progress-tracker/tests/test_prog_sync_contract.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add plugins/progress-tracker/commands/prog-update.md plugins/progress-tracker/skills/progress-update/SKILL.md plugins/progress-tracker/tests/test_command_discovery_contract.py plugins/progress-tracker/tests/test_prog_sync_contract.py
git commit -m "feat(progress-tracker): add prog-update command and contracts"
```

### Task 4: Surface Updates and Owners in Status/Markdown Output

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Modify: `plugins/progress-tracker/tests/test_ui_display_logic.py`
- Modify: `plugins/progress-tracker/tests/test_workflow_state.py` (if status text snapshots are validated)

**Step 1: Add failing display tests**

Cover:
1. `/prog` status includes latest updates summary.
2. generated `progress.md` includes owners and recent updates section.

**Step 2: Run target tests and confirm failure**

```bash
pytest -q plugins/progress-tracker/tests/test_ui_display_logic.py -k "update or owner"
```

**Step 3: Implement minimal rendering changes**

1. Add compact latest N updates in status output.
2. Add owners lines under feature entries in markdown output.

**Step 4: Re-run tests**

```bash
pytest -q plugins/progress-tracker/tests/test_ui_display_logic.py plugins/progress-tracker/tests/test_progress_manager.py -k "update or owner or status"
```

**Step 5: Commit**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py plugins/progress-tracker/tests/test_ui_display_logic.py plugins/progress-tracker/tests/test_workflow_state.py
git commit -m "feat(progress-tracker): show updates and role owners in status output"
```

### Task 5: Add SPM Meeting Command Contracts

**Files:**
- Create: `plugins/super-product-manager/commands/meeting.md`
- Create: `plugins/super-product-manager/commands/roundtable.md`
- Create: `plugins/super-product-manager/commands/assign.md`
- Create: `plugins/super-product-manager/commands/followup.md`
- Modify: `plugins/super-product-manager/tests/...` (create if missing)

**Step 1: Add failing tests for command existence/frontmatter**

Create contract tests asserting:
1. command file exists,
2. scope is `command`,
3. arguments map to meeting/assignment semantics.

**Step 2: Run SPM contract tests and verify failure**

```bash
pytest -q plugins/super-product-manager/tests -k "meeting or roundtable or assign or followup"
```

**Step 3: Create command files with thin routing contracts**

Commands only orchestrate:
1. artifact writing,
2. bridge invocation,
3. sync result messaging.

**Step 4: Re-run SPM tests**

```bash
pytest -q plugins/super-product-manager/tests
```

**Step 5: Commit**

```bash
git add plugins/super-product-manager/commands/*.md plugins/super-product-manager/tests
git commit -m "feat(spm): add meeting workflow command set"
```

### Task 6: Implement SPM Bridge Script (`prog_bridge.py`)

**Files:**
- Create: `plugins/super-product-manager/scripts/prog_bridge.py`
- Modify: `plugins/super-product-manager/tests/...` (bridge unit tests)

**Step 1: Add failing bridge tests**

Cover:
1. success path (`prog` exit 0),
2. missing prog context (graceful degradation),
3. non-zero exit (capture stderr and write sync error record).

**Step 2: Implement minimal bridge**

1. Build safe argv list for `prog` calls (no shell string concatenation).
2. Return structured result object (`ok`, `error`, `command`, `stderr`).

**Step 3: Re-run bridge tests**

```bash
pytest -q plugins/super-product-manager/tests -k "bridge or prog_sync"
```

**Step 4: Commit**

```bash
git add plugins/super-product-manager/scripts/prog_bridge.py plugins/super-product-manager/tests
git commit -m "feat(spm): add prog bridge for meeting/update synchronization"
```

### Task 7: Add Integration Tests for SPM -> PROG Sync

**Files:**
- Create: `tests/test_spm_prog_beta_integration.py`

**Step 1: Write failing E2E tests**

Scenarios:
1. `meeting` creates artifacts + PROG `meeting` update.
2. `assign` sets feature owner + writes assignment update.
3. `followup` sync failure does not block artifact output.

**Step 2: Run integration test and verify failure**

```bash
pytest -q tests/test_spm_prog_beta_integration.py
```

**Step 3: Implement missing glue code in command/bridge/prog layers**

Only minimal changes needed to satisfy test behavior.

**Step 4: Re-run integration and impacted suites**

```bash
pytest -q tests/test_spm_prog_beta_integration.py plugins/progress-tracker/tests plugins/super-product-manager/tests
```

**Step 5: Commit**

```bash
git add tests/test_spm_prog_beta_integration.py plugins/progress-tracker plugins/super-product-manager
git commit -m "test(integration): verify spm to prog beta workflow sync"
```

### Task 8: Resolve Marketplace Version Drift

**Files:**
- Modify: `.claude-plugin/marketplace.json`

**Step 1: Add failing assertion test for version consistency**

Create/update a root-level test that compares:
1. marketplace plugin version
2. each plugin manifest version

**Step 2: Run test and verify failure on current drift**

```bash
pytest -q tests -k "marketplace and version"
```

**Step 3: Update marketplace versions**

Set:
1. `progress-tracker` -> `1.6.12` (or new beta version once decided)
2. `note-organizer` -> `1.3.0` (or new beta version once decided)

**Step 4: Re-run version tests**

```bash
pytest -q tests -k "marketplace and version"
```

**Step 5: Commit**

```bash
git add .claude-plugin/marketplace.json tests
git commit -m "chore(release): align marketplace versions with plugin manifests"
```

### Task 9: Documentation and Release Notes

**Files:**
- Modify: `plugins/progress-tracker/README.md`
- Modify: `plugins/progress-tracker/CHANGELOG.md`
- Modify: `plugins/super-product-manager/README.md`
- Modify: `plugins/super-product-manager/CHANGELOG.md`
- Create: `docs/SPM_PROG_INTEGRATION.md`

**Step 1: Add docs tests/checks first**

1. Update any doc-generation checks.
2. Add assertions for new command presence in generated sections.

**Step 2: Run doc validation commands**

```bash
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
python3 plugins/progress-tracker/hooks/scripts/quick_validate.py
```

Expected: FAIL before docs are updated.

**Step 3: Update docs and changelogs**

1. Document new command workflows.
2. Add integration guide and failure recovery instructions.

**Step 4: Re-run doc checks**

```bash
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --write
python3 plugins/progress-tracker/hooks/scripts/quick_validate.py
```

**Step 5: Commit**

```bash
git add plugins/progress-tracker/README.md plugins/progress-tracker/CHANGELOG.md plugins/super-product-manager/README.md plugins/super-product-manager/CHANGELOG.md docs/SPM_PROG_INTEGRATION.md
git commit -m "docs: add spm-prog beta integration guide and release notes"
```

### Task 10: Final Beta Verification Gate

**Files:**
- No new files (verification only)

**Step 1: Run full regression**

```bash
pytest -q plugins/progress-tracker/tests
pytest -q plugins/super-product-manager/tests
pytest -q plugins/note-organizer/tests
pytest -q tests/test_spm_prog_beta_integration.py
```

**Step 2: Run release checklist commands**

```bash
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
python3 plugins/progress-tracker/hooks/scripts/quick_validate.py
git diff --check
```

**Step 3: Prepare release commit/tag draft**

```bash
git log --oneline --max-count=20
```

Expected: clear sequence of task commits ready for squashing/release.

**Step 4: Commit final release prep**

```bash
git add -A
git commit -m "chore(beta): finalize spm-prog integration beta readiness"
```

## Acceptance Mapping

1. Beta DoD-1/2 -> Tasks 1-7  
2. Beta DoD-3 -> Task 4 + Task 7  
3. Beta DoD-4 -> Tasks 9-10  
4. Beta DoD-5 -> Task 8

## Risks & Mitigations

1. Schema migration regressions  
Mitigation: Task 1/2 backfill tests first, then implementation.

2. Cross-plugin coupling through direct file writes  
Mitigation: bridge only calls `prog` CLI; never writes PROG state directly.

3. Command drift with docs  
Mitigation: enforce generator/check commands in Task 9 and Task 10.
