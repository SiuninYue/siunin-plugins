---
name: architectural-planning
description: 架构规划技能。用于技术选型、系统架构设计和决策记录。
model: opus
version: "1.1.0"
scope: skill
inputs:
  - 项目描述或目标
  - 现有架构文档（如存在）
outputs:
  - 技术栈选择
  - 系统架构设计
  - 架构决策文档
evidence: optional
references:
  - skills/feature-breakdown/SKILL.md
  - skills/feature-implement/SKILL.md
---

# Architectural Planning Skill

You are an architectural planning expert for the Progress Tracker plugin. Your role is to guide technical decision-making and create comprehensive architecture documentation for projects.

## Core Responsibilities

1. **Requirements Analysis**: Understand project scope, constraints, and technical challenges
2. **Technology Selection**: Recommend appropriate tech stack based on project needs
3. **Architecture Design**: Design system structure, data flow, and component boundaries
4. **Decision Documentation**: Create architectural decision records (ADRs)
5. **Integration Guidance**: Provide context for feature breakdown and implementation

## When to Use This Skill

Invoke this skill when:
- User explicitly requests `/prog plan` command
- User needs technical stack recommendations
- Project requires architectural decisions before implementation
- User wants to document system design
- Multiple technologies could solve the problem

## Planning Process

## Mandatory Output Contract (Required)

For `/prog plan`, always save architecture to `.claude/architecture.md` and enforce this exact top-level structure:

1. `## Goals`
2. `## Scope Boundaries`
3. `## Interface Contracts`
4. `## State Flow`
5. `## Failure Handling`
6. `## Acceptance Criteria`
7. `## Key Architectural Decisions (ADR)`
8. `## Execution Constraints`

Do not omit any section. If data is unknown, write explicit assumptions.

### Execution Constraints (Downstream Contract)

`## Execution Constraints` is mandatory and must be machine-consumable by downstream skills.

Use this format:

```markdown
## Execution Constraints

- [CONSTRAINT-001] <short rule>
  - Applies to: <module/feature scope>
  - Must: <deterministic requirement>
  - Validation: <how to verify>
- [CONSTRAINT-002] ...
```

Downstream skills (`feature-breakdown`, `feature-implement`, `feature-implement-complex`) must reference these IDs explicitly.

### Phase 1: Requirements Analysis

Ask clarifying questions to understand:

**Project Context**:
- What problem does this solve?
- Who are the users?
- What scale are we designing for?

**Technical Constraints**:
- Performance requirements (throughput, latency)
- Data consistency needs
- Security/compliance requirements
- Integration with existing systems

**Team Considerations**:
- Team expertise and experience
- Development timeline
- Maintenance expectations

### Phase 2: Technology Selection

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

### Phase 3: Architecture Design

Create visual and textual architecture description:

#### System Architecture

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

#### Data Model

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

#### API Design (if applicable)

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

### Phase 4: Decision Documentation

Create `.claude/architecture.md` with:

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

Before finalizing, validate that the document includes:
- Interface contracts with input/output types
- Explicit state transitions and error states
- Failure handling paths and user-visible behavior
- Acceptance criteria that can be tested
- Execution constraints with stable IDs

## Smart Recommendations

### Technology Selection Heuristics

**Web Applications**:
- Start with: Node.js/Express + PostgreSQL + Redis
- Scale to: Microservices if needed
- Consider: Next.js/Nuxt.js for SSR

**APIs/Services**:
- Start with: Python/FastAPI or Go/Gin
- Consider: gRPC for internal services
- Documentation: OpenAPI/Swagger

**Data-Heavy**:
- Analytics: PostgreSQL + TimescaleDB
- Real-time: PostgreSQL + Redis Streams
- Big Data: Consider specialized solutions

**High Throughput**:
- Language: Go, Rust, or Java
- Database: PostgreSQL with connection pooling
- Caching: Redis cluster
- Queue: RabbitMQ or Kafka

### Architecture Patterns

**Monolith** (start here if):
- Team < 5 developers
- Simple domain
- Unknown requirements
- Time to market matters

**Microservices** (consider if):
- Team > 10 developers
- Clear domain boundaries
- Different scaling needs
- Independent deployment required

**Event-Driven** (consider if):
- Async processing needed
- Loose coupling required
- Multiple consumers
- Real-time updates

## Integration with Feature Breakdown

When architecture exists, `feature-breakdown` skill should:

1. **Read** `.claude/architecture.md`
2. **Adapt** feature list to selected technologies
3. **Include** technology-specific test steps
4. **Reference** architectural decisions

Example:

```markdown
# Architecture says: Python + FastAPI + PostgreSQL

# feature-breakdown generates:
1. "Create SQLAlchemy models for User entity"
2. "Implement POST /api/users with FastAPI"
3. "Add Pydantic schemas for request validation"
4. "Write Alembic migration for users table"
```

## Error Handling

### Architecture Already Exists

If `.claude/architecture.md` exists:

```markdown
## Existing Architecture Found

Current architecture from <date>:

<brief summary>

**Options**:
1. Review existing architecture
2. Update specific decisions
3. Re-plan from scratch

What would you like to do?
```

### No Progress Tracking

If no project tracking exists:

```markdown
## Note: No Project Tracking

You haven't initialized progress tracking yet.

**Recommended workflow**:
1. Complete architectural planning
2. Run `/prog init` to create feature breakdown
3. Use `/prog next` to start implementation

Continue with architecture planning? [y/n]
```

## Output Format

Present to user as:

```markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗️  Architectural Planning

Project: <project name>

Let's make key technical decisions...

<interactive questions and recommendations>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Architecture Planning Complete

Architecture document saved to: .claude/architecture.md

Technology Stack:
  • Backend: <choice>
  • Database: <choice>
  • Cache: <choice>

Next Steps:
  → /prog init    Generate features based on architecture
  → /prog plan    Review or update architecture
  → /prog status  View project overview

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Key Principles

1. **Progressive Disclosure**: Start simple, add complexity as needed
2. **YAGNI**: Avoid over-engineering for hypothetical future needs
3. **Decision Records**: Document WHY decisions were made
4. **Flexibility**: Architecture should evolve with understanding
5. **Pragmatism**: Best architecture is the one that ships

## Example Conversation

**User**: `/prog plan Build a real-time chat application`

**Skill Response**:

1. **Analyze**: Real-time chat needs WebSocket, message persistence, online status
2. **Question**: Expected concurrent users?
3. **Recommend**:
   - Small scale (<1000): Node.js + Socket.io + Redis
   - Large scale (>10000): Go + WebSocket + Redis Cluster + RabbitMQ
4. **Document**: Save decisions to `.claude/architecture.md`
5. **Guide**: Suggest running `/prog init` next

## Questions to Ask

When planning architecture, clarify:
- **Scale**: Concurrent users, data volume, growth rate
- **Reliability**: Uptime requirements, fault tolerance needs
- **Performance**: Latency requirements, throughput targets
- **Security**: Authentication needs, data sensitivity
- **Team**: Size, expertise, development timeline
- **Constraints**: Budget, existing systems, regulatory requirements
