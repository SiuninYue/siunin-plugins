---
description: Launch Progress UI web server and open browser
version: "1.0.0"
scope: command
inputs:
  - User request to open progress UI
outputs:
  - Server started on available port
  - Browser opened to UI
  - Server status displayed
evidence: optional
references: []
model: haiku
---

<CRITICAL>
DO NOT just describe or mention the skill. You MUST invoke it using the Skill tool.

NOW invoke the skill:

Use the Skill tool with these exact parameters:
  - skill: "progress-tracker:ui-launcher"
  - args: ""

WAIT for the skill to complete.
</CRITICAL>
