---
name: finance-basics
description: 产品财务分析指南。用于 ROI 计算、成本估算、商业模型财务分析、投资回报分析。当需要评估产品财务可行性、计算投资回报时使用。
model: haiku
version: "1.0.0"
scope: skill
inputs:
  - 用户问题或场景
  - 约束与目标（如有）
outputs:
  - 方法与模板
  - 注意事项与检查项
evidence: optional
references:
  - ./references/business-model.md
  - ./references/cost-estimation.md
  - ./references/investment-analysis.md
  - ./references/roi-analysis.md
---
# 产品财务分析

## 延迟加载规则

- 默认只使用本文件内容
- 只有在用户明确要求细节或需要模板时，才加载 references 中的附件
- 未加载附件时，先给摘要与下一步

## 核心原则

**产品决策的本质是资源分配决策**。不懂财务的产品经理，做的决策都是「我觉得」。

## 关键财务指标

### 收入类指标

| 指标 | 公式 | 用途 |
|------|------|------|
| **MRR** | 月度经常性收入 | SaaS 核心指标 |
| **ARR** | MRR × 12 | 年度收入预测 |
| **ARPU** | 总收入 ÷ 用户数 | 用户价值评估 |
| **ARPPU** | 总收入 ÷ 付费用户数 | 付费用户价值 |

### 成本类指标

| 指标 | 公式 | 健康值 |
|------|------|--------|
| **CAC** | 获客成本 ÷ 新客数 | 越低越好 |
| **LTV** | 用户生命周期价值 | LTV/CAC > 3 |
| **毛利率** | (收入-成本) ÷ 收入 | SaaS > 70% |

### 效率类指标

| 指标 | 公式 | 说明 |
|------|------|------|
| **ROI** | (收益-成本) ÷ 成本 × 100% | 投资回报率 |
| **回本周期** | CAC ÷ (ARPU × 毛利率) | 越短越好 |
| **NRR** | 净收入留存率 | SaaS 目标 > 100% |

## 可用分析框架

- **ROI 分析**：详见 [roi-analysis.md](roi-analysis.md)
- **成本估算**：详见 [cost-estimation.md](cost-estimation.md)
- **商业模型**：详见 [business-model.md](business-model.md)
- **投资分析**：详见 [investment-analysis.md](investment-analysis.md)

## 使用建议

| 场景 | 推荐框架 |
|------|---------|
| 新功能是否值得做 | ROI 分析 |
| 项目预算规划 | 成本估算 |
| 变现模式设计 | 商业模型 |
| 融资/汇报 | 投资分析 |

## 快速决策公式

### 功能值不值得做？

```
预期收益 = 影响用户数 × 转化提升 × ARPU × 12个月
预期成本 = 开发人天 × 日均成本 + 运营成本
ROI = (预期收益 - 预期成本) ÷ 预期成本

ROI > 100% → 值得做
ROI 50-100% → 看优先级
ROI < 50% → 不做
```

### 定价怎么定？

```
成本定价：成本 × (1 + 目标毛利率)
价值定价：用户愿付价格 × 0.8（留有余地）
竞品定价：竞品价格 × 差异化系数

最终定价 = max(成本定价, min(价值定价, 竞品定价))
```
