---
name: plan-design-review
description: 设计质量评审技能。四维加权评分 + 6 套设计框架，输出结构化评分、问题与 Lane 建议。
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - 评审主题
  - 设计评分（0-10）
  - 优点/问题/建议
  - 可选 change categories（用于 lane 建议）
outputs:
  - docs/product-reviews/*-plan-design-review.md
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references:
  - ./references/design-frameworks.md
---
# plan-design-review

## 延迟加载规则

- 默认只使用本文件内容
- 只有在用户明确要求特定设计框架细节时，才加载 `references/design-frameworks.md`
- 未加载附件时，使用本文件内联的框架摘要即可

## 核心说明

设计质量评审技能。用四维加权评分量化复杂度，结合 6 套设计框架深度审查，输出评分、问题与 Lane 建议（自动建议，不硬阻断）。

---

## 设计质量四维评分

借鉴 complexity scoring 的加权评分体系，对设计方案从四个维度打分（每维 0-10，再加权汇总到 0-10 总分）：

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| 设计决策深度 (D) | ×4 | 无设计决策(0) / 小范围模式选择(3) / 模块级设计(6) / 系统级架构设计(10) |
| 交互模式熟悉度 (P) | ×3 | 复用已有模式(2) / 相似领域实践(5) / 新但业界标准(8) / 全新交互范式(10) |
| 集成复杂度 (I) | ×2 | 纯独立模块(2) / 1-2 个外部系统(5) / 3-5 个系统联动(8) / 跨服务跨端(10) |
| 组件/页面影响面 (F) | ×1 | 1-2 个组件(2) / 3-5 个(5) / 6-10 个(8) / 10+ 个组件或页面(10) |

总分 = (D×4 + P×3 + I×2 + F×1) / 100 × 10

## 设计等级判定

| 总分 | 等级 | 建议 |
|------|------|------|
| 0–3.7 | 简单 | 轻量评审，重点确认交互一致性 |
| 3.8–6.2 | 标准 | 完整评审，关注组件复用和边界契约 |
| 6.3–10 | 复杂 | 深度评审，强烈建议配合 design lane + devex lane |

## 架构设计验证清单

- **界面契约**：组件间输入输出类型是否明确定义？（props、events、slots）
- **状态流转**：显式标注状态转换路径和空/加载/错误态是否完整？
- **失败处理**：异常路径的用户可见行为是什么？（不写"静默失败"）
- **可测试性**：每个交互流程是否有可执行的验收测试路径？
- **执行约束**：设计方案是否给前端实现留下了明确边界？模糊地带是否显式标注假设？

缺少以上任何一项，设计评审不能给满分。

## 变更类别触发的 Lane 建议（自动建议）

| 变更类别 | 自动建议 |
|---------|---------|
| ui, ux, frontend, design, visual, interaction | design lane 建议开启 |
| devex, developer_experience, tooling, ci, build, test, workflow | devex lane 建议开启 |

建议不硬阻断——仅标注建议，由团队决策。

## 递进原则

1. **设计决策应记录 WHY**：不只写选了哪个方案，写选择理由和放弃的替代方案。
2. **从简开始**：先定核心交互，再补边缘场景。
3. **灵活演进**：设计应随理解深入而演进，不追求一次性完美。

---

## 6 套设计框架摘要

以下为每套框架的触发条件与核心主张。完整内容见 `references/design-frameworks.md`（按需加载）。

### 1. Dieter Rams 10 原则
**触发**：评审产品功能的必要性和简洁度时。
核心主张：好的设计是尽可能少的设计（as little design as possible）。功能必须服务于目的，装饰即罪恶。

### 2. Don Norman 3 层设计
**触发**：评审用户情感体验、使用流畅度时。
- **visceral（本能）**：第一眼好看吗？
- **behavioral（行为）**：用起来顺手吗？功能可发现？
- **reflective（反思）**：用完有满足感吗？有身份认同？

### 3. Nielsen 10 启发式
**触发**：评审 UI/UX 可用性时的通用检查清单。
10 条：系统状态可见 / 贴近现实 / 用户可控 / 一致性 / 防错 / 识别优于回忆 / 灵活高效 / 简洁美学 / 帮助识别错误 / 帮助文档。

### 4. Steve Krug 可用性法则
**触发**：评审信息架构、导航、首屏理解成本时。
核心主张：Don't Make Me Think——每一步都应该是显而易见的，不需要思考。消除噪音，突出主路径。

### 5. Gestalt 原则
**触发**：评审视觉组织、信息层级、布局结构时。
核心原则：接近（proximity）/ 相似（similarity）/ 连续（continuity）/ 封闭（closure）/ 主体/背景（figure/ground）。

### 6. AI Slop 黑名单（11 项）
**触发**：评审任何 AI 生成或 AI 辅助的 UI/文案时。
11 项禁区：过度星号列表 / 空洞的"当然！" / 无意义的"作为一个…" / 重复确认用户观点 / 过长的免责声明 / 假装不确定 / 机械式总结 / 无处不在的 emoji / 多余的"首先让我…" / 虚假的热情 / 模板化结尾语。

---

## 防惰性机制

### 反谄媚规则

| 禁用表述 | 必需替代 |
|---------|---------|
| "设计很清晰" | "以下三个交互路径边界不明确：…" |
| "用户体验不错" | "Nielsen 启发式第 N 条未达标：…，建议改为…" |
| "符合设计规范" | "与 Gestalt 接近原则冲突：X 和 Y 视觉上被归为同组但功能无关" |

### 0-10 循环评分

每个维度评分后必须：
1. **rate**：给出分数
2. **explain gap to 10**：解释为什么不是满分，具体差距在哪
3. **fix**：提出具体改进建议
4. **re-rate**：改进后预期能到几分

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
