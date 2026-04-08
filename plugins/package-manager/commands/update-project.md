---
description: 更新当前项目依赖（自动检测项目类型并使用对应包管理器）
version: "1.0.0"
scope: command
inputs:
  - None (auto-detects project type)
outputs:
  - Project dependencies updated
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "package-manager:package-manager"
  - args: "执行当前项目依赖更新，自动检测项目类型并使用对应包管理器 $ARGUMENTS"

WAIT for the skill to complete.
</CRITICAL>
