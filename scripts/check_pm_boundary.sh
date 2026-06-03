#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

PM_FILE="${REPO_ROOT}/plugins/progress-tracker/hooks/scripts/progress_manager.py"
SCRIPTS_DIR="${REPO_ROOT}/plugins/progress-tracker/hooks/scripts"
BOUNDARY_DOC="${REPO_ROOT}/plugins/progress-tracker/docs/progress-tracker/architecture/module-boundaries.md"

AGENTS_FILE="${REPO_ROOT}/AGENTS.md"
CLAUDE_FILE="${REPO_ROOT}/CLAUDE.md"
GEMINI_FILE="${REPO_ROOT}/GEMINI.md"
ALLOWLIST="${REPO_ROOT}/scripts/.pm_boundary_allowlist"

MAX_PM_LINES="${MAX_PM_LINES:-10000}"

say() {
  echo "[pm-boundary] $*"
}

fail() {
  say "ERROR: $*"
  exit 1
}

require_file() {
  local file="$1"
  if [ ! -f "$file" ]; then
    fail "required file not found: $file"
  fi
}

require_file "$PM_FILE"
require_file "$BOUNDARY_DOC"
require_file "$AGENTS_FILE"
require_file "$CLAUDE_FILE"
require_file "$GEMINI_FILE"

if ! cmp -s "$AGENTS_FILE" "$CLAUDE_FILE"; then
  fail "AGENTS.md and CLAUDE.md are out of sync"
fi
if ! cmp -s "$AGENTS_FILE" "$GEMINI_FILE"; then
  fail "AGENTS.md and GEMINI.md are out of sync"
fi
say "Rule file consistency OK"

pm_lines="$(wc -l < "$PM_FILE" | tr -d '[:space:]')"
if [ "$pm_lines" -gt "$MAX_PM_LINES" ]; then
  fail "progress_manager.py line budget exceeded: ${pm_lines} > ${MAX_PM_LINES}"
fi
say "progress_manager.py line budget OK (${pm_lines}/${MAX_PM_LINES})"

reverse_imports="$(rg -n \
  --glob '*.py' \
  --glob '!progress_manager.py' \
  '(^[[:space:]]*import[[:space:]]+progress_manager\b)|(^[[:space:]]*from[[:space:]]+progress_manager[[:space:]]+import\b)' \
  "$SCRIPTS_DIR" || true)"

# Filter out allowlisted violations
if [ -f "$ALLOWLIST" ]; then
  # Build a grep pattern from allowlist entries (skip comment lines, strip line numbers, strip paths)
  allowlist_pattern=$(grep -v '^#' "$ALLOWLIST" | grep -v '^[[:space:]]*$' | sed -E 's|:[0-9]+||' | sed 's|.*/||' | sort -u | paste -sd'|' -)
  if [ -n "$allowlist_pattern" ]; then
    reverse_imports=$(echo "$reverse_imports" | grep -v -E "($allowlist_pattern)" || true)
  fi
fi

if [ -n "$reverse_imports" ]; then
  echo "$reverse_imports"
  fail "submodules must not import progress_manager"
fi
say "No reverse imports to progress_manager detected"

say "All checks passed"
