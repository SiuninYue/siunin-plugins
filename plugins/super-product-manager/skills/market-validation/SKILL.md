---
name: market-validation
description: 市场验证技能。用于将已具体化的想法转化为可执行验证实验与证据门槛。
model: sonnet
version: "1.3.0"
scope: skill
inputs:
  - 已具体化的想法（用户/问题/价值/假设）
  - 资源与约束
outputs:
  - 验证计划与证据标准
  - 风险与决策阈值
  - 详细实验设计框架
evidence: required
references:
  - ./references/ideation.md
  - ./references/app.md
  - ./references/consumer.md
  - ./references/saas.md
  - ./references/service.md
  - ./references/platform.md
  - ./references/hardware.md
  - ./references/content.md
  - ./references/education.md
  - ./references/game.md
  - ./references/social.md
  - ./references/tool.md
---
# market-validation

## 延迟加载规则

- 默认只使用本文件内容
- 只有在用户明确要求细节或需要模板时，才加载 references 中的附件
- 未加载附件时，先给摘要与下一步

## 核心说明

市场验证技能。用于将已具体化的想法转化为可执行验证实验与证据门槛。

## 输出结构（概览）

- 验证目标与假设
- 实验设计与样本
- 成功/失败阈值
- 证据与时间戳
- 下一步决策
- 详细实验设计框架（5个验证维度）

## 想法类型与按需加载规则

先识别想法类型，并按规则加载对应附件：

- 创意生成验证 → `ideation.md`
- 应用类（App/Web）→ `app.md`
- 消费品/食品 → `consumer.md`
- SaaS/B2B → `saas.md`
- 服务/咨询 → `service.md`
- 平台/双边 → `platform.md`
- 硬件/IoT → `hardware.md`
- 内容/媒体 → `content.md`
- 教育/培训 → `education.md`
- 游戏/娱乐 → `game.md`
- 社交产品 → `social.md`
- 工具类产品 → `tool.md`

仅加载匹配类型的附件；不加载其他类型，避免无关信息与 token 浪费。

## 实验设计框架（通用结构）

每个类型的验证模板包含完整的5个维度实验设计框架：

1. **核心价值验证**：验证产品/服务解决核心问题的能力
2. **用户需求验证**：验证目标用户的真实需求和痛点
3. **商业可行性验证**：验证商业模式、定价和盈利能力
4. **技术/运营可行性**：验证技术实现或服务交付的可行性
5. **市场/竞争验证**：验证市场机会和竞争优势
