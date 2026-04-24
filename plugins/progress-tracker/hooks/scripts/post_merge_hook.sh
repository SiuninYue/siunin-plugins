#!/usr/bin/env bash
# post-merge Git hook: auto-reconcile progress.json after merge
# Install via: prog install-git-hooks
# 覆盖所有受影响 plugin（包括 standalone root），不仅限于 plugins/progress-tracker。

set -euo pipefail

CHANGED=$(git diff ORIG_HEAD --name-only 2>/dev/null \
  | grep -E "audit\.log|progress\.json" || true)

if [ -z "$CHANGED" ]; then
  exit 0
fi

echo "[post-merge] Progress state files changed. Running reconcile-state..."

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROG="$REPO_ROOT/plugins/progress-tracker/prog"

if [ ! -x "$PROG" ]; then
  echo "[post-merge] WARN: prog not found at $PROG, skipping"
  exit 0
fi

# 1. 提取所有受影响的 plugin 目录（plugins/<name>）并逐个 reconcile
PLUGINS=$(echo "$CHANGED" | grep -oE "^plugins/[^/]+" | sort -u || true)

for PLUGIN_PATH in $PLUGINS; do
  PLUGIN_ROOT="$REPO_ROOT/$PLUGIN_PATH"
  echo "[post-merge] Reconciling $PLUGIN_PATH..."
  # 使用绝对路径 PLUGIN_ROOT，不依赖 cwd（hook 执行目录可能不是 repo root）
  "$PROG" --project-root "$PLUGIN_ROOT" \
    reconcile-state --auto-commit || {
    echo "[post-merge] WARN: reconcile-state for $PLUGIN_PATH exited $?. Review manually."
    # 不阻断 merge，继续处理其他 plugin
  }
done

# 2. 处理 standalone root tracker（非 plugins/ 子目录）
STANDALONE=$(echo "$CHANGED" | grep -E "^docs/progress-tracker" || true)
if [ -n "$STANDALONE" ]; then
  echo "[post-merge] Reconciling standalone root tracker..."
  "$PROG" --project-root "$REPO_ROOT" \
    reconcile-state --auto-commit || {
    echo "[post-merge] WARN: reconcile-state for root exited $?. Review manually."
  }
fi