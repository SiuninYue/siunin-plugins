# Feedback Observer + Detect Feedback Signal

## 目标

在每次对话中静默捕获用户对 AI 输出的修正/不满意信号，自动记录为结构化反馈条目，作为 M3 进化系统的原材料。

与 feedback-triage（M2）分工：feedback-triage 处理**外部用户反馈**，Feedback Observer 捕获**内部对话修正信号**。

## 当前状态

- ❌ 无自动检测用户修正信号的机制
- ❌ 用户说"不对""重做"后，没有任何结构化记录
- ❌ 反馈全靠人类主动调用 prog-note，遗漏率极高
- ✅ PROG session-start hook 基础设施已存在，可复用

## 方案设计

### 信号检测规则

采用**关键词 + 上下文**双层匹配，按置信度分级：

```
置信度 HIGH（几乎确定是修正）：
  - "不对" "不是这样" "错了" "搞错了" "完全错了"
  - "重做" "重新做" "重新来" "推翻重来"
  - "别" + 动词（"别用这个方案""别这样写"）

置信度 MEDIUM（可能是修正，需结合上下文）：
  - "换一种" "换个方案" "换掉"
  - "不要" + 名词/动词（"不要这个""不要用 mock"）
  - "改成" "改为" "应该是"（表明之前理解有偏差）

置信度 LOW（仅记录，不触发提醒）：
  - "再想想" "再考虑一下"
  - "有没有更好的" "能不能优化"
  - 连续 2 次以上的追问同一问题
```

### 执行流程

```
用户消息到达
  │
  ▼
关键词匹配（本地规则，毫秒级）
  │
  ├── 无匹配 → 不记录
  │
  └── 有匹配 → 静默写入 .prog/feedback/{project}.jsonl
       │
       ├── HIGH → 标记 priority: immediate，下次 prog-note 时主动提醒确认
       ├── MEDIUM → 标记 priority: normal，周扫描时汇总
       └── LOW → 标记 priority: low，月扫描时统计
```

### 误报防御

| 场景 | 防御策略 |
|------|---------|
| 用户说"不对，我的意思不是..."（正常澄清，非 AI 犯错） | 检测到"不对"但下文是补充说明 → 降级为 LOW |
| 用户复述 AI 输出中的"不是" | 需用户消息整体语义判断，不能单靠关键词 |
| 用户在讨论中引用别人的话 | 引号内的文本排除匹配 |
| 同一条反馈 1 分钟内被多次检测 | 去重：同一 session 内相同信号 5 分钟内只记一次 |

### 数据格式

```jsonl
{"id":"FB-042","session":"2026-05-12-a3f2","timestamp":"2026-05-12T14:23:01Z",
 "signal":"不对","confidence":"HIGH","priority":"immediate",
 "context":{"feature":"f23","skill":"feature-implement","step":"3"},
 "trigger_message":"不对，这个方案的并发模型有问题，用 actor model 重做",
 "ai_output_before":"建议使用 mutex + channel 方案处理并发...",
 "confirmed":false}
```

字段说明：
- `confirmed`: 人类是否已确认这条反馈（通过 prog-note 确认后置 true）
- `context.skill`: 触发时正在使用的 skill，用于追溯和进化时的精准定位
- `ai_output_before`: 触发修正时 AI 刚输出的内容摘要，提供完整上下文

## 实现方式

### 选项 A：Hook 驱动（推荐）

在 Claude Code 的 `UserPromptSubmit` hook 中注入检测逻辑：

```
UserPromptSubmit hook
  → 接收用户消息文本
  → 本地规则匹配（纯文本处理，不调用 LLM）
  → 匹配到 → append 到 .prog/feedback/{project}.jsonl
  → 不匹配 → 跳过
```

**优点**：每次用户消息都经过，零遗漏；本地匹配零延迟。
**缺点**：无法理解复杂语义，靠关键词有误报风险。

### 选项 B：Sub-agent 异步扫描（备选）

每 N 轮对话后 spawn haiku sub-agent 扫描最近消息，做语义级判断。

**优点**：语义理解准确，误报率低。
**缺点**：有延迟，消耗 token，无法实时。

### 建议

**Phase 1**：选项 A（hook 本地匹配），先跑起来积累数据。容忍 10-15% 误报率——进化阶段有"人类确认"兜底。

**Phase 2**：数据积累 100+ 条后，评估误报率，决定是否加入 haiku 语义过滤层。

## 存储位置

```
.prog/feedback/
├── {project}.jsonl        # 当前项目的反馈条目
├── evolution_snapshots/   # Evolution Runner 处理后的快照
│   └── 2026-05-12.json    # 某次扫描时处理的反馈集合
└── CONFIG.yml             # 阈值配置
```

## 与进化系统的对接

```
Feedback Observer 写入 → .prog/feedback/{project}.jsonl
                             │
Evolution Runner 扫描 ←──────┘（session 启动时或定时触发）
       │
       ▼
  同一 signal 类型 ≥3 次？
       │
  YES → 生成进化提案 → 人类确认 → 升级为 skill 规则
```

## 影响范围

- **新增**：`.prog/feedback/` 目录及存储逻辑
- **新增**：`UserPromptSubmit` hook（复用现有 hook 基础设施）
- **新增**：关键词匹配规则表（`plugins/progress-tracker/hooks/feedback-signals.py`）
- **不改**：现有 feedback-triage skill（独立运作）
- **PROG CLI**：新增 `prog feedback --list` 子命令查看未确认的反馈

## 成功标准

- [ ] `UserPromptSubmit` hook 能检测到 ≥80% 的明显修正信号（人工抽样验证）
- [ ] 误报率 < 20%（即用户说"不对"但并非指 AI 犯错的情况被错误记录的比例）
- [ ] 反馈条目落盘延迟 < 100ms，不影响对话体验
- [ ] `.prog/feedback/` 中的条目可被 Evolution Runner 消费

## 风险与防御

| 风险 | 概率 | 防御 |
|------|------|------|
| 关键词匹配误报率高 | 中 | 三级置信度 + 人类确认环节，误报不会被自动应用 |
| hook 执行影响对话延迟 | 低 | 纯文本正则匹配，毫秒级 |
| 用户反感被"监控" | 低 | 静默记录，不打断。首次启用时简短告知 |
| 反馈文件膨胀 | 低 | 单文件 < 10MB，按季度归档压缩 |

## 待决策

- [ ] 首次启用时是否需要向用户告知？（建议：第一次 session-start 时一行提示）
- [ ] LOW 置信度条目是否需要去重后才提交给 Evolution Runner？
- [ ] 关键词列表是否需要支持用户自定义（写入 CONFIG.yml）？
