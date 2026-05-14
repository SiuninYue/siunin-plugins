# feature-implement 防漂移机制（STEP 0）

## 目标

防止 AI 在长任务实现过程中逐渐"忘记"原始需求，产生隐性需求漂移（scope creep / 方向偏离 / 细节遗漏）。在每个实现阶段开始时强制重置 AI 对需求的理解。

## 当前状态

- ✅ feature-implement 系列 skill 已存在（standard/simple/complex）
- ❌ 无强制"重读文档"步骤——AI 直接开始写代码
- ❌ 长任务中后阶段产出经常偏离前期设计（实测数据：3+ face 的任务约有 30% 出现可观测漂移）
- ❌ 无理解验证机制——AI 读完文档后没有确认理解的环节

## 方案设计

### STEP 0：实现前重置

在 feature-implement 的任何代码编写步骤之前，插入 STEP 0：

```
STEP 0：需求重置（强制，不可跳过）

1. 定位文档：
   - 读取 docs/product-contracts/{feature}.md（产品合同）
   - 读取 docs/design-briefs/{feature}.md（设计规范，如有）
   - 读取 docs/plans/{feature}-plan.md（开发计划）
   - 读取 .prog/features/{feature}.json（当前进度状态）

2. 提取关键约束（输出在上下文中，不写文件）：
   - AC 清单（每条 AC 的验收条件）
   - 设计决策（配色、布局、交互模式、组件选型）
   - 技术约束（语言、框架、不可用的方案）
   - 依赖关系（本 feature 依赖的其他 feature/task）

3. 理解确认（输出给人类扫一眼）：
   "本阶段将实现 [X 功能]，核心 AC [N 条]，设计参考 [M 个决策点]。
    技术栈: [xxx]，依赖: [已完成/待完成]。
    准备开始实现。"

4. 进入 STEP 1：按 task 列表逐个实现
```

### 设计优先级的强制执行

在实现中做任何判断时，遵循优先级链：

```
优先级（从高到低）：
  1. 设计稿/设计规范（如有）— 视觉、交互、布局的最高权威
  2. 产品合同中的 AC — 功能行为的验收标准
  3. 开发计划中的技术决策 — 架构、模块划分
  4. 开发者（AI）自行判断 — 仅当前 3 层无明确规定时使用
```

当设计稿和产品合同冲突时（如设计稿展示 3 列布局但合同描述为 2 列）：
- **不自行决定**，立即标记并询问用户
- 输出："设计稿为 3 列布局，但合同中描述为 2 列。以哪个为准？"

### 分 skill 的 STEP 0 差异

```
feature-implement (standard):
  STEP 0 完整执行 — 重读全部文档
  → 适用于单 session 可完成的 feature

feature-implement-simple:
  STEP 0 轻量版 — 只重读产品合同 + 当前 task 描述
  → 适用于 15 分钟内可完成的简单改动

feature-implement-complex:
  STEP 0 完整执行 + 每个 face 开始时重读
  → 适用于跨 session 的大型 feature

feature-breakdown:
  STEP 0 — 重读产品合同
  → 拆解时如不理解合同，拆出来的 task 肯定偏
```

### 漂移检测信号

在实现过程中，以下信号表明可能发生了漂移，AI 应主动暂停并重读文档：

| 信号 | 动作 |
|------|------|
| 用户说"不对""不是这个方向" | 立即重读，确认偏离点 |
| 连续 3 个 task 的描述在实现时都"不太匹配" | 检查是否在解决错误的问题 |
| 实现复杂度明显超出计划预估 | 检查是否过度工程化（gold-plating） |
| 产出文件数和预估偏差 > 50% | 检查是否 scope creep |

### 长任务检查点（Checkpoint）

对于 feature-implement-complex（跨多个 session 的大功能）：

```
每完成 3 个 task 或每 30 分钟，插入 Checkpoint：

Checkpoint 自检：
  [ ] 刚才完成的 3 个 task 对应哪些 AC？
  [ ] 剩余的 task 是否仍然覆盖所有未完成的 AC？
  [ ] 有没有出现"顺便做"的额外工作？
  [ ] 设计规范是否需要更新（如实现中发现了设计未覆盖的细节）？
```

## 实现方式

修改各 SKILL.md 的步骤编排，STEP 0 作为第一步硬编码在流程中——不依赖 AI 记忆，每次执行该 skill 必然经过。

```markdown
# feature-implement/SKILL.md（节选）

## 执行流程

### STEP 0: 需求重置（强制执行）

<invoke name="Read">
  <parameter name="file_path">docs/product-contracts/{feature}.md</parameter>
</invoke>
<invoke name="Read">
  <parameter name="file_path">docs/design-briefs/{feature}.md</parameter>
</invoke>

输出关键约束摘要，确认理解后再进入 STEP 1。
```

## 影响范围

- **修改**：`feature-implement/SKILL.md` — 插入 STEP 0
- **修改**：`feature-implement-simple/SKILL.md` — 插入轻量 STEP 0
- **修改**：`feature-implement-complex/SKILL.md` — 插入 STEP 0 + Checkpoint 逻辑
- **修改**：`feature-breakdown/SKILL.md` — 插入 STEP 0
- **修改**：`architectural-planning/SKILL.md` — 插入文档重读步骤
- **不改**：只读 skill 和其他非实现类 skill

## 成功标准

- [ ] 所有 feature-implement 系列 skill 的 SKILL.md 包含 STEP 0
- [ ] STEP 0 重读至少包含产品合同 + 设计规范（如有）
- [ ] 漂移率降低 50% 以上（对比引入前后的用户"不对"类修正频率）
- [ ] STEP 0 执行延迟 < 10 秒（文档读取时间）

## 风险与防御

| 风险 | 概率 | 防御 |
|------|------|------|
| AI 敷衍 STEP 0，读了但没理解 | 中 | "理解确认"环节要求输出摘要，人类可快速判断是否有偏差 |
| 文档不存在时 STEP 0 卡住 | 中 | 文档缺失时输出"缺少 XX 文档，将基于 AC 列表实现"并继续 |
| 简单改动重读全量文档耗时 | 低 | feature-implement-simple 只重读合同 |

## 待决策

- [ ] STEP 0 的"理解确认"输出是否需要人类明确回复"继续"才能进入 STEP 1？
- [ ] Checkpoint 频率是否需要可配置？
- [ ] 文档缺失时是阻止实现还是警告后继续？
