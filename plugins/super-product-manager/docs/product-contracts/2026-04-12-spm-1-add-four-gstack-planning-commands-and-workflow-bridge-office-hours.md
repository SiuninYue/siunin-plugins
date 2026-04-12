# Office Hours: SPM-1 add four gstack planning commands and workflow bridge

- Date: 2026-04-12
- Mode: planner-only (no technical implementation path)

## Goals
- Expose four planning commands in gstack workflow
- Bridge planning outputs into PROG updates with spm_planning source

## Scope
- Planner command contracts for office-hours and CEO review
- Workflow bridge integration between SPM and PROG
- No ack-planning-risk bypass in normal path

## Acceptance Criteria
- validate-planning reports required refs present
- next-feature can proceed without ack flag
- updates include source=spm_planning with planning refs

## Risks
- Inconsistent ref tokens break planning gate
- Command output may miss doc refs
