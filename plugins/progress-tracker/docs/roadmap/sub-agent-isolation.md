# Sub Agent 隔离原则落地

## 目标

将"Sub Agent 隔离"从哲学原则落实为每个 sub-agent 调用的工程技术约束——确保每个 task 在干净的环境中执行，错误假设在 task 边界被截断。Learnings 是唯一合法的跨 task 知识传递通道。

## 当前状态

- ✅ ROADMAP 哲学原则 #7 已定义 Sub Agent 隔离
- ✅ SPM 有 8 个 sub-agent，PROG 有多个 task 级 agent 调用
- ❌ 无技术层面的隔离强制执行——全靠 prompt 中的文字说明
- ❌ sub-agent 调用时可能携带超出必要范围的上下文
- ❌ 没有"禁止传递清单"的明确定义

## 方案设计

### 隔离的三层含义

```
层 1：上下文隔离
  sub-agent 不继承主 agent 的对话历史、之前的错误、临时的判断
  只接收：当前 task 的输入数据 + 相关文档 + 相关 Learnings

层 2：状态隔离
  sub-agent 不共享内存、不修改全局状态、不假设其他 task 的执行结果
  输入和输出是唯一的交互界面

层 3：错误隔离
  sub-agent 的错误不自动影响其他 task
  错误在该 task 内处理（重试/降级/上报），不传播
```

### 禁止传递清单

每次 spawn sub-agent 时，**绝对不能**传入的内容：

| 禁止传入 | 原因 | 替代方案 |
|---------|------|---------|
| 主对话的完整历史 | 包含未验证的中间结论和错误路径 | 只传入当前 task 的上下文摘要 |
| 之前 task 的中间输出 | 错误假设通过"参考上一个 task 的做法"传播 | Learnings 中经确认的经验 |
| 主 agent 对需求的"理解" | 理解可能有偏差，不应固化 | 原始产品合同文档 |
| 临时的"我们假设 X" | 假设在传递中变成事实 | 如假设未验证，task 输入中标注为 UNCONFIRMED |
| 用户的非正式偏好表达 | "我觉得可以这样..."未成文 | 等待正式写入文档或 Learnings |
| 之前 task 的错误日志 | 修复上下文不应带到新功能 | bug-fix 的结论写入 Learnings，不直接传给新 task |

### 允许传入清单（白名单）

| 允许传入 | 条件 |
|---------|------|
| 当前 task 描述（来自 feature-breakdown） | 必须 |
| 产品合同文档（AI-Ready 格式） | 必须 |
| 设计规范文档 | 如有 |
| 开发计划文档 | 必须 |
| 经确认的 Learnings（confidence ≥ 7, confirmed=true） | 匹配 task tags |
| 技术栈约束（语言、框架、禁用方案） | 静态配置 |

### 实施方式

#### 方式 A：Prompt 模板约束（Phase 1，低成本）

在每次 Agent tool call 时，使用标准化的 task prompt 模板：

```
## Task Context（仅此范围内的信息可用于执行）

### 当前任务
{task_description}

### 相关文档（只读）
{product_contract_path}
{design_brief_path}
{dev_plan_path}

### 相关经验（经确认的 Learnings）
{matching_learnings}

### 技术约束
{tech_constraints}

---

## 隔离规则（不可违反）
1. 只使用上述 Task Context 中的信息做判断
2. 不要推断或假设 Context 之外的信息
3. 遇到 Context 无法回答的问题 → 标记为 NEEDS_CLARIFICATION，不要猜测
4. 产出结果只包含：代码变更 + 决策记录 + 新发现的问题
```

#### 方式 B：Hook 校验（Phase 2，高保障）

在 Agent tool call 前，hook 检查传入的 prompt：

```
PreToolUse hook（拦截 Agent 调用）
  → 检查 prompt 中是否包含隔离模板的必需 section
  → 检查是否包含了"禁止传递清单"中的内容（关键词匹配）
  → 不通过 → 阻止调用，要求修复 prompt
```

Phase 1 用方式 A（prompt 模板），Phase 2 如发现隔离违规频繁则加入方式 B。

### 各 sub-agent 的隔离适配

#### SPM sub-agents（8 个）

当前这些 agent 的 prompt 通常是"读这个合同，输出评审"。需要改为：
- 输入：合同文本（而非"我理解的合同内容"）
- 禁止：之前 plan review 的结论（避免设计评审被 CEO 评审的偏见影响）
- Plan Review 管道中的顺序评审（CEO→Design→CTO→DevEx），每个评审使用全新实例，只共享原始合同

#### PROG task agents

- `feature-implement`: 每次调用传当前 task + 文档 + Learnings，不传其他 task 的实现细节
- `bug-fix`: 传 bug 描述 + 相关代码 + 相关 Learnings，不传之前 bug 的修复过程
- `code-review`: 传 diff + AC，不传开发者的"设计意图解释"

## 与 Learnings 系统的协作

这是最关键的设计点——隔离和知识传递如何共存：

```
          Task A                    Task B
        ┌─────────┐              ┌─────────┐
        │ 执行     │              │ 执行     │
        │ 发现 X  │              │ 需要 X  │
        └────┬────┘              └────▲────┘
             │                        │
        prog-done               prog-init/
             │                 feature-breakdown
             ▼                        │
        ┌─────────┐                   │
        │ Learnings│ ←── 经人类确认 ──┘
        │ 沉淀 X   │    （唯一通道）
        └─────────┘

Task A 发现的 X ──（不直接传）──✗──→ Task B
Task A 发现的 X → 确认 → Learnings → Task B 启动时注入 ✓
```

规则："一个 task 的直接经验不能成为另一个 task 的输入，除非经过 Learnings 系统的确认和沉淀。"

## 实现步骤

```
Phase 1 — Prompt 模板标准化
  [ ] 编写"隔离 task prompt 模板"
  [ ] SPM 8 个 sub-agent 的 prompt 改为模板格式
  [ ] PROG feature-implement/bug-fix/code-review 改为模板格式
  [ ] 模板中必须包含"隔离规则"section

Phase 2 — 禁止传递清单落地
  [ ] 在 spawn sub-agent 的代码/SKILL 中集成清单检查
  [ ] 输出对比：修改前 vs 修改后的 prompt 长度和内容差异

Phase 3 — Hook 校验（可选，如 Phase 1 效果不够）
  [ ] PreToolUse hook 检查 Agent 调用的 prompt 结构
  [ ] 违规时输出警告（不阻止，Phase 3 阶段只记录不拦截）
```

## 影响范围

- **修改**：SPM 全部 8 个 sub-agent 的 prompt/SKILL
- **修改**：PROG `feature-implement` 系列、`bug-fix`、`code-review` 的 task prompt
- **修改**：`architectural-planning` 的子分析调用
- **新增**：隔离 task prompt 模板（可复用的 prompt 片段）
- **不改**：主 skill 的执行逻辑（隔离只影响子调用，不影响主流程）

## 成功标准

- [ ] 所有 sub-agent 调用使用统一的隔离 prompt 模板
- [ ] "禁止传递清单"中的 6 类内容在 sub-agent prompt 中出现率降为 0
- [ ] 跨 task 错误传播导致的问题减少 50% 以上
- [ ] sub-agent 输出中 NEEDS_CLARIFICATION 标记数量合理增加（说明不再瞎猜）

## 风险与防御

| 风险 | 概率 | 防御 |
|------|------|------|
| 过度隔离导致 sub-agent 缺少必要上下文 | 中 | 白名单机制确保文档和 Learnings 正常传入 |
| prompt 模板过长增加 token 消耗 | 中 | 模板本身 ~200 tokens；禁止传历史带来的节省更大 |
| 开发效率短期下降（sub-agent 需要更多轮澄清） | 中 | 可接受——短期效率换长期质量 |

## 待决策

- [ ] "禁止传递清单"是否需要允许用户自定义补充？
- [ ] 不同复杂度的 task 是否需要不同隔离级别（strict/standard/relaxed）？
- [ ] 隔离违规是否需要上报到 Evolution Runner（作为"系统应该改进"的信号）？
