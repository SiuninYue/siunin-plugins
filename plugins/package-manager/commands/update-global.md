---
description: 更新全局工具（mise, brew, rustup, Claude Code latest 通道, 全局包）
version: "1.0.0"
scope: command
inputs:
  - Optional: --skip-brew, --skip-mise, --skip-rust
outputs:
  - All global tools updated
  - Claude Code updated via latest channel
  - Global packages updated
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "package-manager:package-manager"
  - args: "执行全局工具更新，包括 mise, brew, rustup, Claude Code latest 通道更新，以及全局包更新 $ARGUMENTS"

WAIT for the skill to complete.
</CRITICAL>
