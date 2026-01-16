# Repository Standards

This document defines shared conventions for commands, agents, and skills in this plugin.

## Front Matter Schema

All markdown files under `commands/`, `agents/`, and `skills/*/SKILL.md` must include these keys.

Required keys:
- `version`: semantic version string
- `scope`: one of `command`, `agent`, `skill`
- `inputs`: short list of required inputs
- `outputs`: short list of expected outputs
- `evidence`: `required`, `conditional`, or `optional`
- `references`: list of attachments that are loaded only when needed

## Evidence & Timestamp

Outputs that involve external facts or user research must include:
- Data source type (e.g. interview, analytics, public source)
- Timestamp (date/time of data)
- Evidence strength (strong/medium/weak)

## Output Modes

Every command supports two modes:
- **简版**: only decision + key reasons + next actions
- **完整版**: full template output

Default is **完整版** unless the user explicitly asks for a short version.

## Skill Attachments (Delayed Load)

Skill attachments live in the same folder as `SKILL.md`.
Rules:
- Do not load attachments by default
- Only load when the user asks for details or the command explicitly needs it
- All attachments must be listed in `references`

## Changes & Compatibility

If output templates change materially, update `README.md` with a short note.
