#!/bin/bash
# Wrapper script for progress-tracker hooks
# Locates and runs progress_manager.py from the plugin root
#
# Usage: hooks/run-hook.sh <command> [args...]
#
# This script handles the case where CLAUDE_PLUGIN_ROOT is not set by
# using the relative location of this script to find the plugin root.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If CLAUDE_PLUGIN_ROOT is set and valid, use it
if [ -n "$CLAUDE_PLUGIN_ROOT" ] && [ -d "$CLAUDE_PLUGIN_ROOT" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    # Fallback: use relative path from this script's location
    # This script is at: <plugin_root>/hooks/run-hook.sh
    # So plugin root is one level up
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

MANAGER_SCRIPT="$PLUGIN_ROOT/hooks/scripts/progress_manager.py"

# Check if the script exists
if [ ! -f "$MANAGER_SCRIPT" ]; then
    echo "Error: progress_manager.py not found at $MANAGER_SCRIPT" >&2
    echo "PLUGIN_ROOT: $PLUGIN_ROOT" >&2
    echo "CLAUDE_PLUGIN_ROOT: ${CLAUDE_PLUGIN_ROOT:-not set}" >&2
    exit 1
fi

# Run the manager script with all arguments
python3 "$MANAGER_SCRIPT" "$@"
