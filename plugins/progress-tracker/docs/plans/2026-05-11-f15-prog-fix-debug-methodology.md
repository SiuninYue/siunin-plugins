# PT-F15: prog-fix skill 嵌入4阶段调试方法论

## 目标

改写 `skills/bug-fix/SKILL.md` 的 Scenario 3（修复已录入 Bug），将4阶段调试方法论内联到 skill 流程中，
使 AI 在新会话中无需额外上下文即可按正确顺序推进调试流程。

## 背景

现有 Scenario 3 流程：

```
用户选 Bug → 委托 systematic-debugging → TDD → git-auto → 记录修复
```

问题：`systematic-debugging` 是通用 skill，不包含结构化的前置引导。AI 在新会话中容易：
- 跳过证据收集直接跳到假设
- 不验证假设唯一性（可能修了表面的 bug 但忽略根因）
- 不检查回归（修 A 坏了 B）

## 4阶段调试方法论

用户（@siunin）提出的结构化调试流程：

```
Phase 1: 收集证据  →  Phase 2: 分析规律  →  Phase 3: 建立假设  →  Phase 4: 实施修复
                                                                     ↑
                                                               TDD 驱动
```

### Phase 1: 收集证据
需明确收集的项目（每项有输出物）：
- 复现路径：用户操作步骤、环境信息
- 错误日志：完整 stack trace、错误码
- 输入→输出对比：期望 vs 实际
- 影响范围：哪些功能/用户受影响

### Phase 2: 分析规律
- 稳定触发条件：每次必现 vs 概率性
- 边界条件：什么情况下正常、什么情况触发 bug
- 时间/环境特征：特定 OS/版本/时间窗口

### Phase 3: 建立假设
- 提出可能的根因假设
- **唯一性验证**：排除所有竞争假设后才确认当前假设是唯一成立原因
- 设计验证实验

### Phase 4: 实施修复（TDD 驱动）
- RED：写失败测试
- GREEN：最小修复
- REFACTOR：清理
- **回归检查**：确认问题 A 已消失 AND 功能 B 未受影响

## 接受标准

1. Scenario 3 新增 `证据收集` 步骤 — 含复现路径、错误日志、输入输出对比
2. Scenario 3 新增 `触发模式分析` 步骤 — 识别稳定触发条件和边界
3. 假设环节加入唯一性验证检查 — 排除竞争假设
4. TDD 后加显式回归检查项 — 问题 A 消失 AND 功能 B 不受影响
5. Scenario 1、Scenario 2 不受任何影响

## 实现方案

### 改动范围

单文件改动：`skills/bug-fix/SKILL.md`

在 Scenario 3 的 `systematic-debugging` 调用**前**插入：

```
Phase 1 + Phase 2 + Phase 3 的结构化引导步骤
```

在 TDD 完成**后**插入：

```
回归检查模板
```

### 不改的内容

- CLI 命令、progress_manager.py 逻辑
- systematic-debugging / TDD / git-auto 委托调用
- Scenario 1（列表查看 bug）和 Scenario 2（排期/优先级）

## 测试计划

1. 对比修改前后 Scenario 3 的步骤数量，确认 4 阶段均有对应步骤
2. 虚构 Bug 走读：完整模拟一次 Scenario 3，检查每阶段输出物
3. diff 验证：Scenario 1 和 Scenario 2 零变化

## 风险

- 改动仅限文本引导，不改变自动化行为——skill 效果依赖 AI 对新增引导的遵循程度
- 新增步骤可能让 skill 变长——需控制在 SOP 门禁 500 行以内

## 范围外

- 不改 systematic-debugging skill 本身
- 不加 CLI 命令
- 不改 progress.json 结构
