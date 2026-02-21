---
name: prog-sync
description: This skill should be used when the user asks to "/prog sync", "sync project memory", "sync capabilities", or requests incremental capability backfill from git history.
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - User request to sync project capability memory
outputs:
  - Candidate capabilities list
  - User-confirmed accepted/rejected candidates
  - Updated project memory sync report
evidence: optional
references: []
---

# Prog Sync Skill

Synchronize capability memory from incremental Git history and persist accepted items through `project_memory.py`.

## Core Responsibilities

1. Read current project memory and `last_synced_commit`.
2. Collect incremental commits and summarize them for capability extraction.
3. Use Claude reasoning to generate candidate capability JSON.
4. Ask for batch confirmation with index syntax (`1,3,5-7`).
5. Persist accepted and rejected candidates using `project_memory.py`.
6. Report inserted/deduped/rejected counts.

## Data Layer Command

Use this script for all persistence:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py
```

## Main Flow

### Step 1: Load Current Memory

Read current memory:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py read
```

Extract:
- `last_synced_commit`
- existing `capabilities` for context

### Step 2: Collect Incremental Commits

Derive commit range:
- If `last_synced_commit` exists: commits in `last_synced_commit..HEAD`
- Else: use recent project history (oldest available to HEAD)

Collect concise commit summaries (`hash + subject + touched files`) for Claude reasoning.

### Step 3: Generate Candidates (Claude Reasoning)

Produce JSON array only. Each candidate must include:
- `title`
- `summary`
- `tags`
- `source_commit`
- `confidence`

If parsing fails or candidates are empty:
- report no candidates
- stop without writing

### Step 4: Show Numbered Candidate List

Display all candidates with:
- index
- title
- confidence
- source commit

Ask user for accepted indexes:
- supports `1,3,5-7`
- empty input means reject all

### Step 5: Parse Selection

Parse selection with:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py parse-selection --selection "<selection>" --total <N>
```

On invalid selection:
- show parser error
- ask once again for corrected input

### Step 6: Persist Accepted / Rejected

Build `accepted_candidates` and `rejected_candidates` by parsed indexes.

Batch write accepted:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py batch-upsert \
  --payload-json '<accepted_json_array>' \
  --sync-meta-json '<sync_meta_json>'
```

`sync_meta_json` should include:
- `sync_id`
- `commit_range`
- `last_synced_commit` (new HEAD hash)
- `rejected_count`

Persist rejected fingerprints:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_memory.py register-rejections \
  --payload-json '<rejected_json_array>' \
  --sync-id '<sync_id>'
```

### Step 7: Final Report

Always report:
1. commit range used
2. total candidates
3. accepted count
4. inserted vs deduped count
5. rejected count
6. new `last_synced_commit`

## Behavior Guarantees

- No semantic algorithm code in data layer.
- Writes are idempotent by fingerprint.
- Sync history and rejected list are retention-limited by script.
- Failure in writing should be reported with actionable error details.
