#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_SKILL_DIR="${PLUGIN_ROOT}/skills/codex-plugin-sync"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
DEST_SKILL_DIR="${CODEX_HOME}/skills/codex-plugin-sync"

if [[ ! -d "${SOURCE_SKILL_DIR}" ]]; then
  echo "Source skill directory not found: ${SOURCE_SKILL_DIR}" >&2
  exit 1
fi

mkdir -p "${CODEX_HOME}/skills"
mkdir -p "${DEST_SKILL_DIR}"

rsync -a --delete "${SOURCE_SKILL_DIR}/" "${DEST_SKILL_DIR}/"

echo "Published codex-plugin-sync skill to: ${DEST_SKILL_DIR}"
echo "Restart Codex session/app to ensure fresh skill discovery if needed."
