---
name: plan-ceo-review
description: CEO 视角产品合同评审技能。从商业合理性审视产品合同，输出机会、风险与 Verdict 三分法结论。
model: sonnet
version: "1.0.0"
scope: skill
inputs:
  - 产品合同主题
  - 机会点与风险点
  - 结论（通过/风险）
outputs:
  - docs/product-reviews/*-plan-ceo-review.md
  - 同步到 PROG 的 planning 更新（source=spm_planning）
evidence: optional
references: []
---
# plan-ceo-review

## 延迟加载规则

- 默认只使用本文件内容
- 本 skill 无附件，所有方法论已内联

## 核心说明

CEO 视角产品合同评审技能。聚焦商业合理性，不纠结实现细节，输出机会、风险与可追溯的 Verdict 结论。

---

## CEO 四种评审模式

根据合同性质，自动选择对应模式：

| 模式 | 触发条件 | 评审重心 |
|------|---------|---------|
| **Expansion** | greenfield 产品、新市场切入 | 市场空间、用户假设、差异化 |
| **Selective** | 有明确方向但需细化 | 优先级、MVP 边界、资源匹配 |
| **Hold Scope** | bug fix、小改进、运营需求 | 必要性确认、范围防膨胀 |
| **Reduction** | >15 files 影响面、过度设计迹象 | 强制裁剪、先交付核心 |

## 五维评审原则

CEO 视角不纠结实现细节，聚焦以下五个判断维度：

**1. Progressive Disclosure**（渐进复杂度）
- 当前合同是否从最简可行版本出发？
- 如果合同已过度膨胀到"大而全"，打回——先从 MVP 切一刀。

**2. YAGNI**（不需要的别加）
- 合同中的每条 scope 是否指向已验证的用户需求？
- "将来可能需要"的范围 → 标记为风险，不纳入当前合同。

**3. Decision Records**（决策可追溯）
- 合同的每个关键结论是否写清楚了 WHY？
- 评审意见本身也是决策记录，必须落盘供事后回溯。

**4. Flexibility**（适应变化）
- 合同是否留有 pivoting 空间？
- 硬性假定（如"竞争对手不会跟进"）需要显式标注为风险。

**5. Pragmatism**（能动的才是好合同）
- 这个合同能指导团队今天就开始工作吗？
- 如果不能——缺什么信息？谁来找？多久？

## CEO 级风险评审清单

对合同中的每条风险声明，逐项判断：

| 维度 | 触发条件 | CEO 关注点 |
|------|---------|-----------|
| 安全边界变更 | 涉及认证、权限、信任域变更 | 合规和法律风险是否已评估？ |
| 不可逆决策 | 数据迁移、Schema 变更、品牌切换 | 做错了能不能回滚？回滚成本？ |
| 跨服务破坏性变更 | 对外 API/合同变更 | 影响多少下游？迁移窗口？ |
| 数据模型模糊 | 核心实体关系不清晰 | 停下来先理清，不要蒙眼往前冲 |
| 验收标准不可测 | AC 无法在产品层面验证 | 模糊的 AC ≈ 无限的 scope creep |

以上任一触发，标记为"风险"并附加具体建议；若 2 个以上触发，verdict 应倾向于"暂缓"。

## 影子路径思维

对合同中的核心数据流，要求覆盖四路径：

- **happy path**：正常流程
- **nil path**：输入为空/无数据
- **empty path**：有输入但结果集为空
- **error path**：异常、超时、服务不可用

合同中若只描述 happy path，标记为风险项。

## 单向门 / 双向门（Bezos 框架）

评估每个关键决策的可逆性：

- **双向门**（可撤销）：鼓励快速决策，低风险
- **单向门**（不可逆）：必须额外标注回滚成本和 fallback 策略

不可逆决策若无 fallback → 自动触发风险标记。

## 机会点评估矩阵

对合同中的机会声明，按以下框架评估：

- **确定性**：这个机会有多大概率兑现？（高/中/低）
- **影响力**：兑现后对核心指标的拉动有多大？
- **时效性**：是否受外部时间窗口约束？（竞对动向、市场周期、合规截止日）
- **排他性**：是我们独有的优势还是行业标配？

## CEO 评审结论（Verdict）

三个可选结论：

- **通过（Approved）**：合同清晰、风险可控，可进入后续 lane 评审。
- **有条件通过（Approved with Risks）**：合同可用，但需标注高优先级风险项并安排 owner 跟踪。
- **暂缓（Deferred）**：关键信息缺失或风险过高，退回补充后再审。

---

## 防惰性机制

### 反谄媚规则

| 禁用表述 | 必需替代 |
|---------|---------|
| "合同写得很清晰" | "以下三点仍需明确才能给出 Approved：…" |
| "风险可控" | "风险 X 的具体回滚路径是什么？成本估算？" |
| "方向正确" | "核心假设是 Y，如果 Y 在 30 天内被证伪，哪条 AC 需要重写？" |

### AskUserQuestion 确认策略

- **交互模式**：每完成一个评审维度后，用 AskUserQuestion 确认再进入下一维度
- **非交互/批处理模式**：完成全部维度后，一次性汇总所有问题和结论，直接给出 Verdict

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
