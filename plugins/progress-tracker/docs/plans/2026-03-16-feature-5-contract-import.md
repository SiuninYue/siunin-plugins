# Feature 5 Plan: Contract Import and Markdown FSM Parser

**Feature ID:** 5
**Name:** 合约自动导入与 Markdown FSM 解析器
**Complexity:** 24 (Standard)
**Workflow:** plan_execute

## Overview

Implement automatic contract import from JSON and Markdown files with a strict FSM parser to avoid pathological backtracking and CLI hangs on malicious input.

## Tasks

### 1. Create contract_importer.py module
- Implement `ContractImporter` class for file resolution and import coordination
- Implement `MarkdownFSMParser` class with strict state transitions
- Add error types: `ContractImportError` with specific subtypes

### 2. Implement FSM Markdown Parser
- State-based parsing with zero regex (avoid backtracking)
- Safety boundaries: 64KB file size, 1024 line length, heading depth 1-3
- Section whitelist enforcement
- Parse budget: max_steps=20000, max_seconds=0.2

### 3. Add thin wrapper in progress_manager.py
- `import_contract_for_feature(feature_id)` function
- Integrate into `add_feature()` and `update_feature()` flows
- Contract auto-detection from `docs/progress-tracker/contracts/`

### 4. Security and Validation
- JSON/MD conflict detection (fail fast, no implicit priority)
- Contract payload normalization
- REQ-ID deduplication and validation
- Scenario prefix auto-correction

### 5. Testing
- Unit tests for FSM parser edge cases
- Integration tests for add/update feature flows
- Security boundary tests (oversized files, deep headings, budget exceeded)
- Source context in error messages

## Implementation Status: COMPLETE

### Completed Optimizations (Post-Review)
1. **Code Deduplication**: Extracted `parse_requirement_id()` shared method
2. **Performance**: `_compact_lines()` using index slicing instead of list copies
3. **Error Context**: Added `source` field to parser, errors show `source:line: message`
4. **Test Coverage**: Added time budget test and error context test

## Acceptance Mapping

- `pytest -k "requirement_ids or change_spec or acceptance_scenarios"` → 1 passed
- `pytest -k "markdown or contract or parser or fsm"` → 9 passed
- `python3 -m py_compile progress_manager.py contract_importer.py` → passed
- DoD: JSON/Markdown contract import works, FSM parser avoids pathological backtracking

## Risks

- None identified; all safety boundaries validated

## Files Modified

- `hooks/scripts/contract_importer.py` (new, ~470 lines)
- `hooks/scripts/progress_manager.py` (thin wrapper integration)
- `docs/progress-tracker/contracts/README.md` (format documentation)
- `tests/test_progress_manager.py` (9 new tests)
- `tests/test_feature_contract_readiness.py` (keyword filter test)
