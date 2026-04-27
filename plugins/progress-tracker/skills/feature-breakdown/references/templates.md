# Feature Breakdown Templates

## Feature Breakdown Display Template (Short Form)

Used after initial breakdown generation (SKILL.md lines 223–237):

```markdown
## Feature Breakdown: <Project Name>

Based on your architecture (Node.js + Express + PostgreSQL):
✓ Using Sequelize for database models
✓ Using Express Router for API endpoints
✓ Using Joi for validation

I've broken this down into N features:
...
```

Each feature must include explicit architecture alignment:
- `Architecture constraints`: list of referenced `CONSTRAINT-*` IDs from `docs/progress-tracker/architecture/architecture.md`
- `Contract touchpoints`: interface/state/failure sections this feature implements

## Feature Breakdown Display Template (Full Form)

Used for output format reference (SKILL.md lines 279–320):

```markdown
## Feature Breakdown: <Project Name>

I've broken this down into N features:

1. **<Feature 1 Name>**
   - Architecture constraints: <CONSTRAINT-...>
   - Contract touchpoints: <interface/state/failure>
   - Test steps:
     - <step 1>
     - <step 2>

2. **<Feature 2 Name>**
   - Architecture constraints: <CONSTRAINT-...>
   - Contract touchpoints: <interface/state/failure>
   - Test steps:
     - <step 1>
     - <step 2>

...

Initialized progress tracking.
```

**At the end, ALWAYS output the Context Handoff Block:**

```markdown
---
**Paste into a new session to start first feature:**

/progress-tracker:prog-next

Project: <project_name> | 0/<total_features> done
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-selects and starts first pending feature.
---
```

Get the `ProjectRoot` by running:
```bash
pwd -P
```
