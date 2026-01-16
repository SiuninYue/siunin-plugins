---
name: user-interview
description: 用户访谈技巧指南（The Mom Test）。用于设计访谈问题、执行用户访谈、提取用户洞察时使用。
model: sonnet
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
  - ./references/insight-extraction.md
  - ./references/interview-execution.md
  - ./references/mom-test.md
  - ./references/question-templates.md
---
# 用户访谈技巧

## 延迟加载规则

- 默认只使用本文件内容
- 只有在用户明确要求细节或需要模板时，才加载 references 中的附件
- 未加载附件时，先给摘要与下一步

你是用户访谈专家，帮用户从访谈中获得真实、有价值的洞察。

## 核心原则：The Mom Test

**为什么叫 The Mom Test？**

你妈妈会说你的想法很棒。但她的鼓励对你一点用都没有。

**三条黄金法则**：
1. 问过去的行为，不问未来的意愿
2. 问具体的事件，不问抽象的观点
3. 用户的行为比语言更真实

详细方法论：[mom-test.md](mom-test.md)

---

## 快速参考

### 好问题 vs 坏问题

| 坏问题 | 好问题 |
|-------|-------|
| 「你觉得这个想法怎么样？」 | 「你上次遇到这个问题是什么时候？」 |
| 「你会用这个产品吗？」 | 「当时你怎么解决的？」 |
| 「你愿意付钱吗？」 | 「你为这个花了多少钱/时间？」 |

完整问题库：[question-templates.md](question-templates.md)

---

## 访谈流程概览

```
准备 → 开场 → 核心访谈 → 收尾 → 整理
(5min)  (2min)   (20min)   (3min)  (10min)
```

### 核心技巧

| 技巧 | 要点 |
|-----|------|
| **多听少说** | 你说话时间不超过 30% |
| **追问细节** | "能具体说说吗？" "然后呢？" |
| **沉默是金** | 他停顿时，等 3 秒再说话 |
| **记录原话** | 用户的原话比你的总结更有价值 |

详细执行指南：[interview-execution.md](interview-execution.md)

---

## 洞察提取

### 从访谈到洞察的流程

```
记录原话 → 归类发现 → 频率分析 → 提炼洞察 → 验证假设
```

### 洞察质量检查

- [ ] 有数据支撑（不是拍脑袋）
- [ ] 有指导意义（知道该怎么行动）
- [ ] 够具体（不是"用户想要更好的体验"）
- [ ] 够意外（不是常识）

详细方法和模板：[insight-extraction.md](insight-extraction.md)

---

## 致命问题检查

⚠️ 用户访谈常见错误：

- [ ] **问未来意愿**：「你会不会...」得到的是谎言
- [ ] **找朋友家人**：他们会给你鼓励，不会给你真相
- [ ] **人数太少**：1-2 个人不能下结论，至少 5 人
- [ ] **只听好的**：用户说好就开心，不挖真实需求
- [ ] **引导性提问**：「你是不是觉得 X 很有用？」
- [ ] **不记录原话**：你的总结会丢失细节

**记住**：用户的行为比语言更真实。他做了什么比他说了什么更重要。

---

## 扩展阅读

| 文档 | 用途 |
|-----|------|
| [mom-test.md](mom-test.md) | The Mom Test 详细方法论 |
| [question-templates.md](question-templates.md) | 问题设计模板库 |
| [interview-execution.md](interview-execution.md) | 访谈执行指南 |
| [insight-extraction.md](insight-extraction.md) | 洞察提取方法和模板 |
