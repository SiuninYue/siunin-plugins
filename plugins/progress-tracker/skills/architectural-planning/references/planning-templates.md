# Architectural Planning Templates

## Phase 2: Technology Selection — Decision Template

For each technical decision, present:

```markdown
## 📦 Decision: <Component Name>

**Options**:

1. **[Option A]** - ⭐ Recommended
   - Pros: <advantage 1>, <advantage 2>
   - Cons: <disadvantage 1>
   - Best for: <use case>

2. **[Option B]**
   - Pros: <advantage 1>, <advantage 2>
   - Cons: <disadvantage 1>
   - Best for: <use case>

3. **[Option C]**
   - Pros: <advantage 1>, <advantage 2>
   - Cons: <disadvantage 1>
   - Best for: <use case>

**Context**: <specific project context>
**Recommendation**: [Option A] because <reasoning>

Choose [A/B/C] or suggest alternative:
```

## Phase 3: Architecture Design Templates

### System Architecture

```markdown
## 🏗️  System Architecture

### High-Level Structure

```
[Client Layer] → [API Gateway] → [Service Layer] → [Data Layer]
                      ↓                ↓
                 [Auth Service]  [Message Queue]
```

### Component Breakdown

**API Gateway**
- Responsibility: Routing, rate limiting, authentication
- Technology: <selected technology>
- Scaling: <horizontal/vertical>

**Service Layer**
- <Service 1>: <responsibility>
- <Service 2>: <responsibility>
- <Service 3>: <responsibility>

**Data Layer**
- <Database 1>: <data type>
- <Cache>: <usage pattern>
- <Message Queue>: <async processing>
```

### Data Model

```markdown
## 📊 Data Model

### Entities

**<Entity 1>**
- Fields: <key fields>
- Relationships: <relations to other entities>
- Volume: <estimated records>

**<Entity 2>**
- Fields: <key fields>
- Relationships: <relations to other entities>
- Volume: <estimated records>
```

### API Design (if applicable)

```markdown
## 🔌 API Design

### REST Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST   | /api/users | Create user | Required |
| GET    | /api/users/:id | Get user | Required |

### Data Flow

1. Client → Request → API Gateway
2. API Gateway → Validate Auth
3. API Gateway → Route to Service
4. Service → Business Logic
5. Service → Database/Cache
6. Response ← Service ← API Gateway ← Client
```

## Phase 4: Architecture Document Template

```markdown
# Architecture: <Project Name>

**Created**: <timestamp>
**Last Updated**: <timestamp>

## Technology Stack

| Component | Technology | Version | Justification |
|-----------|-----------|---------|---------------|
| Backend   | <choice>  | <ver>   | <reason>      |
| Database  | <choice>  | <ver>   | <reason>      |
| Cache     | <choice>  | <ver>   | <reason>      |

## Key Architectural Decisions

### ADR-001: <Decision Title>

**Status**: Accepted / Proposed / Deprecated

**Context**: <problem or situation>

**Decision**: <choice made>

**Consequences**:
- Positive: <benefit 1>, <benefit 2>
- Negative: <drawback 1>
- Risks: <risk 1>

**Alternatives Considered**:
1. <Alternative 1> - Rejected because <reason>
2. <Alternative 2> - Rejected because <reason>

## System Architecture

<architecture diagram or description>

## Data Model

<data model description>

## Integration Points

<external systems and APIs>

## Deployment Strategy

<deployment approach>

## Next Steps

1. Review architecture with team
2. Run `/prog init` to generate feature breakdown based on these decisions
3. Begin implementation with `/prog next`
```
