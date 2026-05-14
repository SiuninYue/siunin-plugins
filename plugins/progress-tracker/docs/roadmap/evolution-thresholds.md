# 进化系统：三级触发阈值 + Evolution Runner

## 目标

将 Feedback Observer 和 Learnings 系统积累的反馈/教训，按阈值自动触发进化动作——升级为规则、优化 skill、或提议新建 skill。实现系统自我优化，越用越聪明。

## 当前状态

- ✅ Learnings 数据模型已设计（ROADMAP M3）
- ❌ Learnings 只是被动积累，无主动进化触发机制
- ❌ 反馈数据（Feedback Observer）尚未开始收集
- ❌ 无 Evolution Runner 实现
- ❌ 无 Evolution Log 追溯机制

## 方案设计

### 三级阈值定义

```
阈值 1：反馈累积 → 规则升级
  触发条件：同一 signal type + 同一 skill 的反馈 ≥3 次（confirmed=true）
  动作：生成"将该经验升级为 {skill} 正式规则"提案
  示例：feature-implement 中 3 次"并发模型错了" → 在 feature-implement SKILL.md
         中增加"涉及并发时必须优先考虑 actor model"规则

阈值 2：评分趋势 → Skill 优化
  触发条件：某个 skill 的 review 评分（plan-review 的 0-10 分）连续 3 次 < 6 分
  动作：生成"建议重新审查并优化 {skill} 方法论"提案
  示例：plan-design-review 连续 3 次评分 < 6 → 触发方法论重构讨论

阈值 3：未覆盖模式 → 新建 Skill
  触发条件：同一类操作/需求 ≥3 次未被任何现有 skill 覆盖
  动作：生成"建议创建新 skill: {name}"提案
  示例：用户 3 次手动做"数据迁移脚本" → 生成"创建 data-migration skill"提案
```

### 阈值参数（可配置）

```yaml
# .prog/feedback/CONFIG.yml
thresholds:
  rule_upgrade:
    min_occurrences: 3        # 最少出现次数
    require_confirmed: true   # 是否需要人类确认过的反馈
    lookback_days: 90         # 回溯天数
  skill_optimize:
    min_low_scores: 3         # 连续低评分次数
    low_score_threshold: 6    # 低于此分视为"低评分"
    lookback_reviews: 10      # 回溯最近 N 次 review
  new_skill_propose:
    min_occurrences: 3        # 最少出现次数
    lookback_days: 60         # 回溯天数
    min_distinct_sessions: 2  # 最少不同 session 中出现
```

### Evolution Runner 设计

**触发时机**（优先级从高到低）：
1. Session 启动时（每次新对话开始时扫描一次）
2. prog-done 执行后（feature 完成是一个自然的总结点）
3. 手动触发：`prog evolution --scan`

**扫描逻辑**：

```
Evolution Runner 启动
  │
  ├── 1. 加载 CONFIG.yml 阈值配置
  │
  ├── 2. 扫描 .prog/feedback/{project}.jsonl
  │      - 过滤 confirmed=true 的条目
  │      - 按 (signal_type, skill) 分组计数
  │      - 标记达到阈值 1 的分组
  │
  ├── 3. 扫描 review 评分历史
  │      - 来源：plan-ceo-review / plan-design-review / plan-eng-review / plan-devex-review
  │      - 读取最近 10 次评分
  │      - 检测连续低评分模式
  │      - 标记达到阈值 2 的 skill
  │
  ├── 4. 扫描未被覆盖的重复操作
  │      - 来源：prog-note 中 category=handoff 或 summary 包含"手动"/"人肉"的条目
  │      - 按操作类型分组计数
  │      - 标记达到阈值 3 的模式
  │
  └── 5. 生成 Evolution Report
         - 列出所有触发阈值的发现
         - 每条发现 = 触发条件 + 证据链 + 建议动作
         - 标记为 DRAFT，等待人类确认
```

### Evolution Report 格式

```markdown
# Evolution Report — 2026-05-12

## 阈值 1 触发：规则升级建议 (1 条)

### EVO-001: feature-implement 并发模型选择
- **触发条件**：3 次被修正"并发模型不对"
- **证据**：
  - FB-012 (2026-04-20): "不对，用 actor model，别用 mutex"
  - FB-028 (2026-05-02): "并发又错了，数据流场景选 actor"
  - FB-042 (2026-05-10): "重做，并发模型应该是 actor"
- **建议动作**：在 `feature-implement/SKILL.md` 增加规则——
  "涉及多实体并发数据流时，默认使用 actor model，仅简单互斥场景用 mutex"
- **状态**: DRAFT ⏳ 等待确认

## 阈值 2 触发：Skill 优化建议 (0 条)
无。

## 阈值 3 触发：新建 Skill 建议 (0 条)
无。

---
上次扫描: 2026-05-12 09:03 UTC
下次扫描: 下次 session 启动时
```

### 人类确认 UX

```
Evolution Runner 输出报告后：

  AskUserQuestion:
  "Evolution Runner 发现 1 条规则升级建议，要查看吗？"
    → [查看详情] [全部批准] [全部忽略] [下次再说]

  查看详情后逐条：
  "EVO-001: 将 actor model 规则加入 feature-implement。批准？"
    → [批准] → 自动写入 SKILL.md + 记录 Evolution Log
    → [拒绝] → 记录拒绝原因，该信号 180 天内不再触发
    → [修改] → 用户编辑建议文本后批准
```

关键约束：**所有进化动作必须人类确认后执行**，与哲学原则 #2 "从不 auto-apply" 一致。

### Evolution Log 格式

```jsonl
{"id":"EVO-001","timestamp":"2026-05-12T09:05:00Z","action":"rule_upgrade",
 "signal_type":"wrong_concurrency_model","target_skill":"feature-implement",
 "evidence":["FB-012","FB-028","FB-042"],
 "rule_added":"涉及多实体并发数据流时，默认使用 actor model",
 "decision":"approved","decided_by":"siunin"}
```

可追溯问题："这条规则是 2026-05-12 因为 3 次并发模型被修正而加入的"。

## 与 Sub Agent 隔离的关系

这是 ROADMAP 中最容易混淆的一对概念，明确区分：

| | Sub Agent 隔离 | Learnings / 进化系统 |
|---|---|---|
| **防什么** | task 执行中的**错误假设**跨任务传播 | **正确经验**丢失 |
| **传递方向** | 禁止 task→task 隐式传递 | 允许 Learnings→新 task 显式注入 |
| **经过人类** | 不需要（隔离是自动的） | 必须（进化必须人类确认） |
| **机制** | 全新实例，不共享上下文 | 经确认的规则/教训写入 skill，下个 task 加载 |

两者互补：隔离保证 task 环境干净，进化保证跨 task 经验不丢失。**Learnings 是唯一合法的跨 task 知识传递通道。**

## 实现步骤

```
Phase 1 — 数据基础（依赖 Feedback Observer 先上线）
  [ ] Feedback Observer 积累 ≥50 条 confirmed 反馈
  [ ] Learnings 系统开始写入 .prog/learnings/

Phase 2 — Evolution Runner MVP
  [ ] 实现 Evolution Runner 扫描脚本
  [ ] 阈值 1（规则升级）优先实现
  [ ] Evolution Report 生成 + AskUserQuestion 确认流
  [ ] Evolution Log 写入

Phase 3 — 完整三级阈值
  [ ] 阈值 2（skill 优化）接入 review 评分数据
  [ ] 阈值 3（新建 skill）接入 prog-note 操作记录
  [ ] CONFIG.yml 支持用户自定义阈值参数

Phase 4 — 自动化增强
  [ ] prog-done 后自动触发扫描
  [ ] 月度 Evolution Summary 自动生成
```

## 影响范围

- **新增**：`plugins/progress-tracker/scripts/evolution_runner.py`
- **新增**：`.prog/feedback/CONFIG.yml`
- **新增**：`.prog/feedback/evolution_log.jsonl`
- **修改**：`prog-done/SKILL.md` — 步骤中增加"触发 Evolution Runner"
- **修改**：session-start hook — 增加 Evolution Runner 调用
- **修改**：`prog` CLI — 新增 `prog evolution --scan` 子命令
- **不改**：Learnings 数据模型（消费方，不修改）

## 成功标准

- [ ] Evolution Runner 能正确识别 ≥3 次的同类反馈（单元测试覆盖率 > 80%）
- [ ] 进化提案生成后成功通过 AskUserQuestion 确认
- [ ] 确认后的规则变更可追溯（Evolution Log 记录完整）
- [ ] 误报建议（即不该触发但触发了的）< 20%
- [ ] 扫描耗时 < 2 秒（数据量 < 1000 条时）

## 风险与防御

| 风险 | 概率 | 防御 |
|------|------|------|
| 阈值太敏感，频繁打扰用户 | 中 | 阈值可配置；"下次再说"选项延迟 7 天 |
| 数据量少时阈值无意义 | 高（前期） | Phase 1 先积累数据，不急于做判断 |
| 进化规则与其他 skill 规则冲突 | 低 | 写入前 Grep 检查目标 skill 是否有冲突规则，有则标注 |
| Evolution Runner 扫描耗时过长 | 低 | 增量扫描（只扫描上次扫描后的新数据） |

## 待决策

- [ ] 阈值 2 的评分数据来源——review 的 Verdict（Approved/Risks/Deferred）还是 0-10 评分？
- [ ] 拒绝过的建议是否永久排除？还是设冷却期（如 180 天）？
- [ ] Evolution Report 是否需要支持 Markdown 落盘（方便 git 追踪历史）？
