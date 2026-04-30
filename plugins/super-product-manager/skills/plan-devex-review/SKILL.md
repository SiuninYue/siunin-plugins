---
name: plan-devex-review
description: 开发者体验摩擦评审技能。三阶段摩擦检查 + TTHW 基准 + Journey Trace 9 阶段 + DX 第一原则，输出 0-10 评分和 P0/P1/P2 改进优先级。
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - 评审主题
  - DevEx 评分（0-10）
  - friction 点与改进建议
  - 可选 change categories（用于 lane 建议）
outputs:
  - docs/product-reviews/*-plan-devex-review.md
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references:
  - ./references/journey-trace.md
  - ./references/dx-first-principles.md
---
# plan-devex-review

## 延迟加载规则

- 默认只使用本文件内容
- 需要 Journey Trace 每阶段详细追问清单时，加载 `references/journey-trace.md`
- 需要 DX 第一原则完整描述 + 金标准对标时，加载 `references/dx-first-principles.md`
- 未加载附件时，使用本文件内联的摘要即可

## 核心说明

开发者体验摩擦评审技能。从 Design/Plan/Execute 三阶段系统审查开发流程摩擦点，结合 TTHW 基准和 9 阶段 Journey Trace，输出量化评分和优先级改进建议。

---

## TTHW 基准（Time-to-Hello-World）

衡量新开发者从零到第一个可运行结果的时间：

| 等级 | 时间 | 判定 |
|------|------|------|
| **Champion** | < 2 分钟 | 行业最佳（Stripe、Tailwind 水准） |
| **Competitive** | 2–5 分钟 | 竞争力水平 |
| **Needs Work** | 5–10 分钟 | 有明显摩擦，需改进 |
| **Red Flag** | > 10 分钟 | 严重阻塞新人上手 |

## DevEx 评审：三阶段摩擦检查

### Design 阶段摩擦

- 设计文档是否在进入开发前就位？（"边设计边写"是最高频的摩擦源）
- 技术选型是否已做出并记录 WHY？（ADR 缺失 = 开发中反复讨论）
- 架构约束（CONSTRAINT-*）是否已明确通知开发者？（隐含规则 = 返工陷阱）
- 接口契约（含类型定义和错误格式）是否已完成跨团队对齐？

### Plan 阶段摩擦

- 任务拆解粒度是否合理？（单任务 > 2 小时 → 拆；单任务 < 15 分钟 → 合）
- 依赖是否正确排序？（数据模型 → 业务逻辑 → 外部接口 → UI → 集成）
- Sprint contract 是否包含可测试的 done criteria 和 test plan？
- Plan 路径策略是否统一？（只存 `docs/plans/*.md`，不散落各处）

### Execute 阶段摩擦

- 开发环境启动是否 < 1 条命令？（多步手动配置 = 摩擦）
- Git 工作区策略是否清晰？（ALLOW_IN_PLACE / REQUIRE_WORKTREE 规则是否已自动化）
- 中断恢复是否可靠？（workflow_state + plan_path 是否可在新 session 零信息损耗恢复）
- 代码审查和验证门禁是否在流程中已就位？（而非事后补）

## 摩擦点分类与信号

| 摩擦类型 | 信号 | 严重度 |
|---------|------|--------|
| 环境搭建摩擦 | 新人 on-call 需半天以上才能本地跑起来 | 高 |
| 工作区管理摩擦 | 开发中频繁遇到 uncommitted changes 阻塞切换 | 中 |
| 上下文恢复摩擦 | session 断开后无法回到中断点，需重读代码 | 高 |
| 质量门禁缺失 | review/evaluator/ship-check 未在 PR 流程中自动化 | 中 |
| 事务安全摩擦 | progress.json 写入无锁保护，多 agent 可能竞争 | 低（内部工具可接受） |
| 任务粒度摩擦 | 任务过大不可交、过小无价值 | 中 |

## DevEx 评分 0-10

综合三阶段摩擦检查结果给出评分：

- **0–3（重度摩擦）**：多个高严重度 friction，开发体验显著拖慢团队速度
- **4–6（中度摩擦）**：存在若干改进项，团队可工作但不流畅
- **7–8（良好）**：大部分流程清晰，少数 edge case 有摩擦
- **9–10（优秀）**：三阶段流畅，中断可恢复，质量门禁自动化

## 改进优先级框架

- **P0（立即改进）**：阻塞性问题，不做则无法高效开展
- **P1（本迭代改进）**：明显摩擦点，改进后有显著提速效果
- **P2（纳入 backlog）**：锦上添花的改进，不影响当前节奏

## 变更类别触发的 Lane 建议（自动建议）

| 变更类别 | 自动建议 |
|---------|---------|
| devex, developer_experience, tooling, ci, build, test, workflow | devex lane 建议开启 |
| ui, ux, frontend, design, visual, interaction | design lane 建议开启 |

建议不硬阻断——仅标注建议，由团队决策。

---

## Journey Trace 9 阶段（摘要）

完整每阶段追问清单见 `references/journey-trace.md`（按需加载）。

| 阶段 | 定义 |
|------|------|
| 1. Discovery | 开发者第一次听说这个工具/API/框架 |
| 2. First Contact | 打开文档或 README 的第一屏 |
| 3. Setup | 安装、配置、环境准备 |
| 4. Hello World | 运行第一个可工作的示例 |
| 5. Core Task | 完成一个真实的、非玩具的任务 |
| 6. Error Recovery | 遇到第一个错误，尝试解决 |
| 7. Advanced Usage | 使用非主路径功能、扩展点、高级配置 |
| 8. Collaboration | 多人协作、权限管理、代码审查流程 |
| 9. Maintenance | 升级依赖、迁移、长期维护 |

## DX 第一原则（8 条摘要）

完整描述 + 金标准对标见 `references/dx-first-principles.md`（按需加载）。

1. **Zero friction onboarding**：新人应能在 5 分钟内完成 Hello World
2. **Progressive complexity**：简单任务简单做，复杂任务可做，不强迫初学者先学高级概念
3. **Errors are teachers**：错误信息应该告诉开发者哪里错了、为什么错、怎么修
4. **Predictability**：相似的操作有相似的结果，API 行为符合最小惊讶原则
5. **Fast feedback loops**：本地开发反馈应在 1 秒内，CI 应在 5 分钟内
6. **Escape hatches**：高层抽象必须提供低层逃生口，不锁死用户
7. **Docs as product**：文档不是附属品，是产品体验的一部分
8. **Version stability**：升级不应破坏已有代码，breaking changes 必须有迁移路径

---

## 防惰性机制

### 反谄媚规则

| 禁用表述 | 必需替代 |
|---------|---------|
| "开发体验不错" | "Setup 阶段 TTHW 实测 X 分钟，属于 Needs Work 区间，原因是…" |
| "文档比较清晰" | "Journey Trace 第 6 阶段（Error Recovery）缺少具体错误码说明，开发者遇到 X 错误时无从下手" |
| "流程比较顺畅" | "Execute 阶段：session 中断后恢复需要重新阅读 N 个文件，上下文恢复摩擦为高" |

---

## 子 Agent 审查指令

产出 artifact 并同步 PROG 后，使用 Agent 工具 spawn 一个独立审查 agent。

给它的 prompt：
> 读取 `<artifact_path>`，从 completeness/consistency/clarity/scope/feasibility 5 个维度审查，返回 JSON：
> `{"pass": bool, "issues": [{"dimension": "...", "severity": "blocking|advisory", "description": "..."}]}`

收到结果后评估：
- `pass: true` → 流程结束
- 仅有 `advisory` issues → 记录到 PROG update details，不修改 artifact，流程结束
- 有 `blocking` issues → 修改 artifact → 追加 `sync_planning_update(category="status")` update → 重新 spawn 审查（最多 2 次迭代）
- 2 次迭代耗尽仍有 blocking → 追加 `category=risk` update，向用户报告并建议人工介入
