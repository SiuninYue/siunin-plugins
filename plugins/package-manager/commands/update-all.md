---
description: 一键更新所有包管理器（mise, brew, rustup, Claude Code latest 通道, 全局包, 项目依赖）
version: "1.0.0"
scope: command
inputs:
  - Optional: --skip-brew, --skip-mise, --skip-rust, --skip-project
outputs:
  - All package managers updated
  - Claude Code updated via latest channel
  - Cleanup performed
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "package-manager:package-manager"
  - args: "执行一键更新所有包管理器，包括 mise, brew, rustup, Claude Code latest 通道更新，以及全局包和项目依赖更新 $ARGUMENTS"

WAIT for the skill to complete.
</CRITICAL>
