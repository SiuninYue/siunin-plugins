# Boundary Checker Fix: `\b` Regex Bug + Allowlist Mechanism

**Change ID:** 20260603-boundary-fix-r0-c4f2
**Date:** 2026-06-03
**Component:** `scripts/check_pm_boundary.sh`

---

## Problem

`scripts/check_pm_boundary.sh` was supposed to detect when submodules reverse-import `progress_manager.py`, but it silently missed all local/function-scope imports. The checker could be fooled simply by placing an import inside a function body rather than at module top-level.

The result: 4 submodule files (`wf_auto_driver.py`, `sprint_ledger.py`, `lifecycle_state_machine.py`, `progress_ui_server.py`) contained reverse imports that had accumulated undetected since the F18 modularization work.

---

## Root Cause

In Bash single-quoted strings, `\\b` passes the two literal characters `\b` to ripgrep. Ripgrep interprets `\b` (backslash + b) **outside** a character class as "escaped lowercase b" — i.e., a literal `b`. It does **not** interpret it as a word boundary assertion (which in rg's PCRE2 engine would be written as `\b` inside a double-quoted shell string, or `\b` unescaped).

The broken pattern in single quotes:
```
'...(import[[:space:]]+progress_manager\\b)...'
```
rg receives: `import[[:space:]]+progress_manager\b`

rg's PCRE2 sees `\b` as a literal `b`, so the pattern effectively becomes `...progress_managerb` which never matches any real Python import. The checker appeared to pass because it found zero matches — but zero matches because the pattern was wrong, not because the code was clean.

The fix is to drop one backslash level so rg receives the true word-boundary sequence `\b`:
```
'...(import[[:space:]]+progress_manager\b)...'
```

---

## Fix

### 1. Regex correction (`scripts/check_pm_boundary.sh`)

Changed both `\\b` occurrences in the rg pattern to `\b`:

```bash
# Before (broken)
'(^[[:space:]]*import[[:space:]]+progress_manager\\b)|(^[[:space:]]*from[[:space:]]+progress_manager[[:space:]]+import\\b)'

# After (fixed)
'(^[[:space:]]*import[[:space:]]+progress_manager\b)|(^[[:space:]]*from[[:space:]]+progress_manager[[:space:]]+import\b)'
```

### 2. Allowlist mechanism (`scripts/check_pm_boundary.sh`)

Added support for `scripts/.pm_boundary_allowlist`. When the file exists, the checker builds a grep exclusion pattern from its non-comment lines and filters matching violations before failing. This allows known, tracked violations to be suppressed while new violations are still caught.

### 3. Allowlist file (`scripts/.pm_boundary_allowlist`)

Created with entries covering the 4 files that contain known violations, all scheduled for cleanup in the Final round of the facade refactor. Entries may include line numbers for human traceability, but the checker normalizes them to file names before filtering so harmless line drift does not break CI.

| File | Lines | Reason |
|---|---|---|
| `wf_auto_driver.py` | 81, 96 | local imports of `get_progress_dir()` |
| `sprint_ledger.py` | 40, 95, 236 | local imports of state helpers |
| `lifecycle_state_machine.py` | 432 | local import of doc-gen functions |
| `progress_ui_server.py` | 39, 40 | module-level try/except import |

---

## Impact

- **Checker coverage:** Now detects local/function-scope imports in addition to module-level imports.
- **No Python files modified:** Zero changes to any `.py` file.
- **Known violations suppressed:** The allowlisted files are acknowledged technical debt, not new regressions.
- **New violations blocked:** Any new reverse import in any non-allowlisted file will fail CI.

---

## Validation

```bash
# Main check passes
bash scripts/check_pm_boundary.sh
# Expected: [pm-boundary] All checks passed

# Verify it catches NEW violations (not in allowlist)
echo "def foo():
    import progress_manager
    return progress_manager.something()" > plugins/progress-tracker/hooks/scripts/_test_violation.py
bash scripts/check_pm_boundary.sh 2>&1 || echo "CORRECTLY CAUGHT VIOLATION"
rm plugins/progress-tracker/hooks/scripts/_test_violation.py

# Docs check
python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```

---

## Rollback Steps

1. Revert `scripts/check_pm_boundary.sh` to commit prior to this change.
2. Optionally delete `scripts/.pm_boundary_allowlist`.
3. After rollback, violations in the 4 known files will be silently missed again.

---

## Residual Risk

- The 4 allowlisted files remain architectural violations until the Final round cleanup.
- New reverse imports in allowlisted files are suppressed by design until those files are removed from the allowlist. This trades stricter line-level enforcement for CI stability during unrelated edits. Mitigation: keep the allowlist small, file-scoped, and tied to the Final round cleanup.
- If someone adds a reverse import to a non-allowlisted file at a very high indentation (e.g., inside a nested function), the `^[[:space:]]*` prefix ensures it is still caught.
