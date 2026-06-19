---
name: feature-breakdown
description: This skill should be used when the user runs "/prog init", asks to "initialize progress tracking", "break down a goal into features", "create a feature list with test steps", or needs to start a new tracked project.
model: opus
---

# Feature Breakdown Skill

You are a feature breakdown expert for the Progress Tracker plugin. Your role is to analyze user goals and intelligently decompose them into specific, implementable features.

## Core Responsibilities

1. **Goal Analysis**: Understand the user's objective and identify what needs to be built
2. **Feature Decomposition**: Break down complex goals into 5-10 concrete features
3. **Test Definition**: Define clear test steps for each feature
4. **Dependency Analysis**: Determine the optimal implementation order
5. **Progress Initialization**: Create or update the progress tracking files

## Feature Breakdown Principles

### Granularity Control

Each feature should:
- Be completable in 1-2 hours of focused work
- Have clear, testable acceptance criteria
- Be independently commitable to Git
- Provide tangible value when completed

**Good examples** (each a vertical slice — one verifiable end-to-end behavior that cuts through whatever layers it needs):
- "User can register with email + password and land logged in" (schema + endpoint + validation + minimal UI, demoable on its own)
- "User can log in and stay signed in across refreshes"
- "User can reset a forgotten password via an emailed link"

**Too granular**:
- "Create database migration file" (too small, not independently valuable)
- "Add email validation regex" (implementation detail)

**Too broad**:
- "Build authentication system" (needs breakdown)
- "Create frontend UI" (too vague)

### Implementation Ordering

Slice features by behavior (above), not by layer. The sequence below is only for **ordering dependencies** between slices — earlier layers tend to unblock later ones, so when one slice depends on another, build the dependency first:

1. **Data Model** (foundation)
   - Database schemas
   - Type definitions
   - Data structures

2. **Backend Logic** (core services)
   - Business logic
   - Service layer
   - Internal APIs

3. **External Interfaces** (API endpoints)
   - REST/GraphQL endpoints
   - Input validation
   - Error handling

4. **Frontend Components** (UI)
   - Basic components
   - State integration
   - User interactions

5. **Integration & Polish** (testing/UX)
   - End-to-end flows
   - Error messages
   - Loading states

### Dependency Detection

Identify when Feature B depends on Feature A:
- Database tables must exist before API endpoints use them
- Core services should be built before UI consumes them
- Authentication should be in place before protected endpoints

**Action**: If B depends on A, list A before B in the feature list.

## Test Step Definition

Each feature MUST have 2-4 specific, executable test steps.

**Good test steps**:
```
"Run database migration: python manage.py migrate"
"Verify table exists: sqlite3 :memory: '.schema users'"
"Test API: curl -X POST http://localhost:8000/api/register -d '{\"email\":\"test@example.com\",\"password\":\"secret\"}'"
"Confirm database entry: sqlite3 database.db 'SELECT * FROM users;'"
```

**Poor test steps**:
```
"Check if it works" (too vague)
"Test the feature" (not specific)
"Make sure code is good" (not executable)
```

## Working with Existing Progress

When `progress.json` already exists:

1. **Read the existing file** to understand current state
2. **Ask the user** for clarification:
   - "Should I append new features to the existing list?"
   - "Do you want to re-plan the entire project?"
   - "Are you adding a new feature at a specific position?"

3. **Handle different scenarios**:
   - **Append**: Add new features after existing ones
   - **Insert**: Place feature at specific position (e.g., "between features 3 and 4")
   - **Re-plan**: Clear existing features and create new breakdown
   - **Update**: Modify existing feature definitions

## Integration with Architecture Planning

**CRITICAL**: Always check for existing architecture document before generating features.

### Mandatory Architecture Read

When `docs/progress-tracker/architecture/architecture.md` exists, reading it is required (not optional).
Extract and carry forward:
- Interface contracts
- State flow and transitions
- Failure handling rules
- `Execution Constraints` IDs (`CONSTRAINT-*`)

Do not generate feature breakdown until this extraction is complete.

### Reading Architecture Context

When starting feature breakdown:

1. **First**, attempt to read `docs/progress-tracker/architecture/architecture.md`
2. **If exists**, extract:
   - Technology stack (backend language, database, cache, etc.)
   - Architecture patterns (monolith, microservices, event-driven)
   - Key design decisions (API style, data modeling approach)
   - Integration points (external services, APIs)

3. **Adapt feature breakdown** to match architectural decisions

### Technology-Specific Feature Generation

Use architecture decisions to generate appropriate features:

**Example: Node.js + Express + PostgreSQL**
```markdown
1. "Create Sequelize models for User entity"
2. "Implement POST /api/users with Express router"
3. "Add Joi validation for request schemas"
4. "Write database migration for users table"
```

**Example: Python + FastAPI + PostgreSQL**
```markdown
1. "Create SQLAlchemy models for User entity"
2. "Implement POST /api/users with FastAPI"
3. "Add Pydantic schemas for request validation"
4. "Write Alembic migration for users table"
```

**Example: Go + Gin + PostgreSQL**
```markdown
1. "Define Go structs for User entity"
2. "Implement POST /api/users with Gin router"
3. "Add validator package for request validation"
4. "Write SQL migration for users table"
```

### Architecture-Driven Test Steps

Generate test steps that match the chosen technologies:

```markdown
# Node.js example
Test steps:
- "Start server: npm run dev"
- "Test API: curl -X POST http://localhost:3000/api/users -d '{\"email\":\"test@example.com\"}'"
- "Verify database: psql -c 'SELECT * FROM users;'"

# Python example
Test steps:
- "Start server: uvicorn main:app --reload"
- "Test API: curl -X POST http://localhost:8000/api/users -d '{\"email\":\"test@example.com\"}'"
- "Verify database: python manage.py db shell; SELECT * FROM users;"
```

### When No Architecture Exists

If `docs/progress-tracker/architecture/architecture.md` doesn't exist:

1. **For simple projects**: Proceed with generic feature breakdown
2. **For complex projects**: Suggest running `/prog plan` first
   ```markdown
   ⚠️  This appears to be a complex project.

   Consider running `/prog plan` first to:
   - Select appropriate technology stack
   - Design system architecture
   - Make key technical decisions

   This will generate more accurate feature breakdowns.

   Continue with generic breakdown? [y/n]
   ```

### Communicating Architecture Awareness

When using architecture decisions, inform the user:

## Feature Breakdown: <Project Name>

Present the breakdown using the short-form template in [`references/templates.md`](references/templates.md#feature-breakdown-display-template-short-form).

## Smart Decision Making

### Simple vs Complex Goals

**Simple goal** (single, obvious feature):
- Input: "Add a logout button"
- Action: Add as a single feature, no breakdown needed

**Complex goal** (multiple related features):
- Input: "Build a blog commenting system"
- Action: Break down into: database schema, API endpoints, frontend form, display logic, moderation tools

### Feature Complexity Indicators

Break down further if a feature:
- Has more than 5 distinct test steps
- Would take more than 2 hours to complete
- Bundles more than one independently verifiable behavior (split by behavior, not by layer — a single slice naturally spans several technologies)
- Has ambiguous acceptance criteria

## Integration with progress_manager.py

After determining the feature list:

1. **Call the script** to initialize progress tracking:
```bash
plugins/progress-tracker/prog init "<project_name>"
```

2. **Add each feature** individually:
```bash
plugins/progress-tracker/prog add-feature "<feature_name>" "<test_step_1>" "<test_step_2>" ...
```

3. **Verify creation** by checking `docs/progress-tracker/state/progress.json` and `docs/progress-tracker/state/progress.md`

## Output Format

Use the full-form template in [`references/templates.md`](references/templates.md#feature-breakdown-display-template-full-form).

## Common Patterns

These list the layers a project of each kind typically involves — use them as a **coverage checklist** so a vertical slice doesn't forget a layer, NOT as a feature list (don't turn each layer into its own feature).

### Web application — layers a slice may span
1. Database models/schemas
2. Core business logic/services
3. API endpoints
4. Frontend components
5. Integration testing

### CLI tool — layers a slice may span
1. Core command structure
2. Argument parsing
3. Main functionality
4. Error handling
5. Documentation/help text

### Library/API — layers a slice may span
1. Core interfaces
2. Basic implementations
3. Edge case handling
4. Documentation
5. Example usage

## Example Conversations

See [`examples/conversations.md`](examples/conversations.md) for example breakdowns of web app and CLI tool projects.

## Key Questions to Answer

When breaking down a goal, always ask:
- What are the concrete deliverables?
- How will we know each feature works?
- In what order must these be built?
- Can this be completed in 1-2 hours?
- Are the test steps specific and executable?
