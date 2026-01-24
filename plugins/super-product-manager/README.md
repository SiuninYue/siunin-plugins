# Super Product Manager

全能产品经理插件 - 为超级个体/一人企业设计，帮助从想法到产品的全流程管理。

## 特点

- 直截了当：不说废话，有问题直接指出
- 追问到底：关键信息不清就追问，不替你脑补
- 模板完整：每个工具都有详细的输出格式
- 实战导向：专注可执行的结果，不是理论说教

## 安装

### 从GitHub安装（推荐）
```bash
# 添加siunin的插件市场
/plugin marketplace add https://github.com/SiuninYue/siunin-plugins.git

# 安装超级产品经理插件
/plugin install super-product-manager@siunin-plugins
```

### 本地开发安装
```bash
# 添加本地市场（开发时使用）
/plugin marketplace add /path/to/siunin-plugins

# 安装插件
/plugin install super-product-manager@siunin-plugins
```

## 🚀 快速开始 Quick Start

最快上手方式：直接告诉 Claude 你的想法

**验证一个产品想法**
```
/idea 我想做一个帮助自由职业者管理收入和发票的工具
```

**生成需求文档**
```
/prd 用户登录功能，支持手机号和邮箱两种方式
```

**做功能优先级排序**
```
/prioritize
- 用户注册
- 订单管理
- 数据导出
- 多语言支持
```

## 📋 完整工作流程 Workflow

从 0 到 1 做产品，推荐按以下流程：

### Phase 1: 想法验证期 ✨

**目标**：确认想法值得做

| 步骤 | 命令 | 说明 |
|-----|------|------|
| 1 | `/idea` | 验证想法是否值得投入 |
| 2 | `/persona` | 明确目标用户画像 |
| 3 | `/interview` | 准备用户访谈验证假设 |

**Checklist** - 这个阶段结束时，你应该能回答：
- [ ] 用户愿意为这个问题付费吗？
- [ ] 目标用户具体是谁？
- [ ] 用户现在怎么解决这个问题？

---

### Phase 2: 规划设计期 📐

**目标**：确定做什么和怎么做

| 步骤 | 命令 | 说明 |
|-----|------|------|
| 1 | `/compete` | 分析竞品，找到差异化方向 |
| 2 | `/mvp` | 定义最小可行产品范围 |
| 3 | `/roadmap` | 规划产品路线图 |

**Checklist** - 这个阶段结束时，你应该有：
- [ ] 清晰的差异化策略
- [ ] 明确的 MVP 功能清单
- [ ] 3-6 个月的产品路线图

---

### Phase 3: 开发执行期 🛠️

**目标**：把需求转化为可执行的任务

| 步骤 | 命令 | 说明 |
|-----|------|------|
| 1 | `/prd` | 为每个功能生成详细需求文档 |
| 2 | `/story` | 拆分为用户故事 |
| 3 | `/metrics` | 设计关键指标 |
| 4 | `/prioritize` | 排列开发优先级 |

**产出物**：
- 可直接交付开发的 PRD
- 带验收标准的用户故事
- 产品指标体系
- 优先级排序后的开发计划

---

### Phase 4: 上线运营期 🚀

**目标**：确保顺利上线并持续改进

| 步骤 | 命令 | 说明 |
|-----|------|------|
| 1 | `/launch` | 上线前检查清单 |
| 2 | `/retro` | 迭代复盘总结 |

**长期循环**：
- 每次上线前用 `/launch` 检查
- 每个迭代结束用 `/retro` 复盘

---

## 🎯 场景速查表 Quick Reference

| 我想要... | 用这个命令 |
|----------|-----------|
| 验证一个想法靠不靠谱 | `/idea` |
| 了解我的目标用户 | `/persona` |
| 准备用户访谈 | `/interview` |
| 分析竞争对手 | `/compete` |
| 确定 MVP 范围 | `/mvp` |
| 规划产品路线 | `/roadmap` |
| 写需求文档 | `/prd` |
| 写用户故事 | `/story` |
| 设计数据指标 | `/metrics` |
| 排功能优先级 | `/prioritize` |
| 上线前检查 | `/launch` |
| 做迭代复盘 | `/retro` |

## 🤖 Agent 使用指南 Agents Guide

Agent 是专业的 AI 助手，会在合适的时机自动介入。你也可以直接要求 Claude 使用特定 Agent。

### 各 Agent 专长

| Agent | 擅长做什么 | 适合什么场景 |
|-------|----------|------------|
| `strategist` | 战略规划 | 想清楚产品方向、商业模式 |
| `researcher` | 用户研究 | 深入理解用户、做访谈设计 |
| `spec-writer` | 写需求 | 输出 PRD、用户故事 |
| `analyst` | 数据分析 | 设计指标、分析数据 |
| `prioritizer` | 排优先级 | 功能排序、资源分配 |
| `dev-translator` | 开发对接 | 把需求变成技术任务 |
| `ux-reviewer` | 体验评审 | 评审设计、优化交互 |
| `gtm-planner` | 上市策划 | 发布计划、增长策略 |

### 使用示例

```
请用 strategist agent 帮我分析这个产品的商业模式
```

```
让 researcher 帮我设计一份用户访谈问卷
```

## Commands

| 命令 | 功能 |
|-----|------|
| `/idea` | 验证产品想法是否值得做 |
| `/prd` | 生成完整的产品需求文档 |
| `/story` | 生成用户故事卡片 |
| `/persona` | 生成详细的用户画像 |
| `/metrics` | 设计产品指标体系 |
| `/prioritize` | 对功能/任务进行优先级排序 |
| `/mvp` | 规划最小可行产品 |
| `/compete` | 分析竞品并找到差异化机会 |
| `/launch` | 生成产品上线检查清单 |
| `/roadmap` | 制定产品路线图 |
| `/retro` | 进行项目/迭代复盘 |
| `/interview` | 生成用户访谈问题和指南 |

## Agents

| Agent | 专长 |
|-------|------|
| `spec-writer` | 需求撰写专家 |
| `dev-translator` | 开发翻译官 |
| `researcher` | 用户研究员 |
| `analyst` | 数据分析师 |
| `prioritizer` | 优先级决策师 |
| `strategist` | 产品战略师 |
| `gtm-planner` | 上市策划师 |
| `ux-reviewer` | UX 评审员 |

## Skills

| Skill | 内容 |
|-------|------|
| `lean-startup` | 精益创业方法论 |
| `prioritization` | 优先级框架 |
| `market-research` | 市场调研方法 |
| `user-interview` | 用户访谈技巧 |
| `stakeholder-comm` | 干系人沟通模板 |
| `data-driven` | 数据驱动决策 |
| `tech-spec` | 技术方案与架构设计 |
| `finance-basics` | 基础财务与 ROI 评估 |
| `legal-compliance` | 法务合规与政策模板 |
| `ai-toolkit` | AI 交付规范与输出控制 |
| `idea-concretization` | 想法具体化与假设生成 |
| `market-validation` | 市场验证与证据门槛 |
| `persona` | 用户画像与证据标注 |
| `prd` | 需求文档（PRD）与验收标准 |
| `user-story` | 用户故事与验收标准 |
| `roadmap` | 产品路线图与里程碑 |
| `launch` | 上线发布与沟通清单 |
| `retro` | 复盘结构与行动项 |

## License

MIT

## Standards

本项目遵循统一的格式与证据规范，包含输出模式、证据与时间戳、以及技能附件按需加载规则。详见 `STANDARDS.md`。

---

## 更新日志 Changelog

### v1.4.0 (2025-01-25)

#### 规范修复
- ✅ 修复所有 12 个 commands 的 frontmatter，添加 STANDARDS.md 必填字段
  - 新增字段：`version`, `scope`, `inputs`, `outputs`, `evidence`, `references`
  - 所有命令现在完全符合插件规范

#### 技能内容大幅扩充
| Skill | 优化前 | 优化后 | 新增内容 |
|-------|-------|-------|---------|
| **retro** | 34行 | 295行 | 复盘类型与框架（KPT/5 Whys/Start-Stop-Continue）、标准流程、模板、最佳实践 |
| **persona** | 51行 | 300行 | 用户画像要素、质量检查清单、详细模板、完整示例 |
| **user-story** | 50行 | 385行 | INVEST原则、Given-When-Then验收标准、故事拆分技巧、估算方法 |
| **roadmap** | 50行 | 414行 | 4种路线图类型（Now-Next-Later/Theme-Based等）、里程碑规划、可视化格式 |
| **launch** | 50行 | 459行 | 上线检查清单、灰度发布策略、回滚方案、风险控制矩阵 |

#### 新增内容
- 复盘框架：KPT、5 Whys、Start-Stop-Continue、4Ls、Post-Mortem
- 用户画像质量检查：证据来源标注、验证清单
- 验收标准模板：Given-When-Then 格式、边界场景、异常场景
- 路线图可视化：时间线视图、泳道视图、表格视图
- 灰度发布策略：5阶段灰度、判断标准阈值
- 完整示例：小李用户画像、手机验证码登录、笔记工具路线图

### v1.3.0
- 初始版本，包含完整的产品管理工作流