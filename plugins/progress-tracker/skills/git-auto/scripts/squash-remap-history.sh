#!/usr/bin/env bash
# squash-remap-history.sh
#
# Optional utility: update stale commit hash references in tracking files
# after a historical squash (e.g., manual `git rebase -i --autosquash`).
#
# Usage:
#   ./squash-remap-history.sh <old_hash> <new_hash> [--dry-run]
#
# What it does:
#   1. Replaces <old_hash> with <new_hash> in:
#      - docs/progress-tracker/state/progress.json
#      - docs/progress-tracker/state/sprint_ledger.jsonl
#      - docs/progress-tracker/state/project_memory.json
#   2. Reports each substitution made.
#   3. Does NOT rewrite git history — only updates tracker metadata.
#
# IMPORTANT: Run this only after completing a manual historical squash.
# Normal feature/task closeout via prog-done handles hash tracking automatically.

set -euo pipefail

OLD_HASH="${1:-}"
NEW_HASH="${2:-}"
DRY_RUN="${3:-}"

if [[ -z "$OLD_HASH" || -z "$NEW_HASH" ]]; then
    echo "Usage: $0 <old_hash> <new_hash> [--dry-run]" >&2
    exit 1
fi

if ! [[ "$OLD_HASH" =~ ^[0-9a-fA-F]{7,64}$ ]]; then
    echo "Error: old_hash must be a hexadecimal string (7-64 chars)" >&2
    exit 1
fi
if ! [[ "$NEW_HASH" =~ ^[0-9a-fA-F]{7,64}$ ]]; then
    echo "Error: new_hash must be a hexadecimal string (7-64 chars)" >&2
    exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
TRACKER_DIR="$REPO_ROOT/plugins/progress-tracker/docs/progress-tracker/state"

FILES=(
    "$TRACKER_DIR/progress.json"
    "$TRACKER_DIR/sprint_ledger.jsonl"
    "$TRACKER_DIR/project_memory.json"
)

COUNT=0
for FILE in "${FILES[@]}"; do
    [[ -f "$FILE" ]] || continue
    MATCHES=$(grep -c "$OLD_HASH" "$FILE" 2>/dev/null || echo 0)
    if [[ "$MATCHES" -gt 0 ]]; then
        echo "Found $MATCHES reference(s) in $(basename "$FILE")"
        if [[ "$DRY_RUN" != "--dry-run" ]]; then
            sed -i '' "s/$OLD_HASH/$NEW_HASH/g" "$FILE"
            echo "  -> Updated: $OLD_HASH → $NEW_HASH"
        else
            echo "  -> [dry-run] would replace $OLD_HASH → $NEW_HASH"
        fi
        COUNT=$((COUNT + MATCHES))
    fi
done

if [[ "$COUNT" -eq 0 ]]; then
    echo "No references to $OLD_HASH found in tracking files."
else
    echo "Total: $COUNT reference(s) processed."
fi
