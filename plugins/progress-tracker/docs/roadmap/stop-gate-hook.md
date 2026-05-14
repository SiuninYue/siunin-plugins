# Stop Gate Hook

## 目标

在关键操作节点设置硬性检查——操作前验证前置条件是否满足，不满足则阻止操作并说明原因。弥补"自然语言决策的不稳定性"，作为流程的最后一道防线。

## 当前状态

- ✅ PROG 有 session-start 和 preflight hooks
- ✅ `testing-standards` skill 描述中提到"测试不通过不标记 done"，但无技术强制执行
- ❌ 无 Stop Gate 机制——AI 可以跳过 review 直接标记 done
- ❌ 无 Pre-Commit Check——编译失败也能 commit
- ❌ 状态标记全凭 AI 自觉，无兜底

## 方案设计

### 三道 Stop Gate

```
Gate 1: Pre-Commit Check — commit 前
  触发点：git commit 执行前（PreToolUse hook 拦截 git commit）
  检查项：
    [ ] 项目编译通过（根据语言：go build / cargo check / tsc --noEmit）
    [ ] 无未解决的 merge conflict marker（<<<<<<< in files）
    [ ] testing-standards 标记为 passed
  不通过 → 阻止 commit，输出失败原因
  用户绕过 → 允许 git commit --no-verify（记录 audit log）

Gate 2: Pre-Done Check — 标记 done 前
  触发点：prog-done 执行时
  检查项：
    [ ] Code Review 已完成且 Verdict ≠ Rejected
    [ ] 测试全部通过（pytest / go test / etc）
    [ ] 无未提交的变更（git status --porcelain 为空）
    [ ] feature 关联的所有 task 状态为 completed
  不通过 → 阻止 done，逐条列出未满足项
  用户绕过 → prog-done --force（记录 audit log）

Gate 3: Pre-Stop Check — AI 准备停止前
  触发点：agent 准备结束 session 时（Stop hook）
  检查项：
    [ ] 当前 task 状态不是 in_progress（如果是，提醒先 prog-note 记录中断点）
    [ ] 无未推送的 commit（git log origin/HEAD..HEAD）
    [ ] 无 uncommitted 变更（提醒先 checkpoint）
  不通过 → 不阻止停止，但给出警告 + 建议操作
```

### 实现方式

利用 Claude Code 的 hook 机制：

```json
// settings.json 中的 hook 配置
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "pattern": "git commit",
        "command": "python plugins/progress-tracker/hooks/stop_gate.py --gate pre-commit"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Skill",
        "pattern": "progress-tracker:prog-done",
        "command": "python plugins/progress-tracker/hooks/stop_gate.py --gate pre-done"
      }
    ],
    "Stop": [
      {
        "command": "python plugins/progress-tracker/hooks/stop_gate.py --gate pre-stop"
      }
    ]
  }
}
```

### Stop Gate 脚本逻辑

```
stop_gate.py --gate <gate_name>

1. 读取当前项目状态（progress.json + git status + test results）
2. 根据 gate_name 加载对应的检查清单
3. 逐项检查，收集结果
4. 全部通过 → exit 0（允许继续）
5. 有未通过项 → exit 1 + 输出 JSON 格式的失败清单

输出示例（exit 1）：
{
  "gate": "pre-done",
  "passed": false,
  "checks": [
    {"item": "Code Review", "status": "FAIL", "detail": "no review found for feature f23"},
    {"item": "Tests", "status": "PASS"},
    {"item": "Uncommitted changes", "status": "FAIL", "detail": "3 files modified"},
    {"item": "All tasks completed", "status": "PASS"}
  ],
  "action": "Fix 2 failing items or use --force to bypass"
}
```

### 绕过机制

所有 Gate 都支持 `--force` 绕过，但绕过记录写入 audit log：

```jsonl
{"timestamp":"2026-05-12T15:00:00Z","gate":"pre-done","action":"force_bypass",
 "feature":"f23","reason":"review 已完成但未写入状态文件，手动确认通过"}
```

设计原则：**不阻止人类做正确的事，但确保每次绕过都有记录**。

## 与现有机制的关系

| 现有机制 | Stop Gate 的作用 |
|---------|-----------------|
| testing-standards | Gate 2 检查 testing-standards 是否标记 passed |
| code-review | Gate 2 检查 code-review 是否已完成 |
| git-auto | Gate 1 防止编译失败的代码被 commit |
| prog-done | Gate 2 是 prog-done 的前置条件 |
| Session preflight | Gate 3 是 session 结束前的最后提醒 |

Stop Gate 不替代这些 skill，而是确保它们**确实被执行了**——从"应该做"变成"不做就过不去"。

## 实现步骤

```
Phase 1 — Pre-Done Check（最核心）
  [ ] 实现 stop_gate.py 脚本框架
  [ ] 实现 Pre-Done 检查逻辑
  [ ] 集成到 prog-done 流程
  [ ] 测试：正常通过 + 各种失败场景

Phase 2 — Pre-Commit Check
  [ ] 实现编译检查（按语言检测）
  [ ] 集成到 git commit hook
  [ ] --no-verify 绕过逻辑 + audit log

Phase 3 — Pre-Stop Check
  [ ] 实现 stop 前检查
  [ ] session 结束提醒
```

## 影响范围

- **新增**：`plugins/progress-tracker/hooks/stop_gate.py`
- **新增**：`.prog/audit/stop_gate_bypass.jsonl`
- **修改**：`settings.json` — 新增 PreToolUse/Stop hook 配置
- **修改**：`prog-done/SKILL.md` — 流程中标注 Gate 2
- **修改**：`git-auto/SKILL.md` — 流程中标注 Gate 1

## 成功标准

- [ ] Pre-Done Gate 能阻止 ≥95% 的不合格 done（人工验证）
- [ ] Pre-Commit Gate 能阻止编译失败的代码被 commit
- [ ] 正常通过路径延迟 < 500ms
- [ ] 绕过记录 100% 写入 audit log

## 风险与防御

| 风险 | 概率 | 防御 |
|------|------|------|
| Gate 误报，阻止合法操作 | 中 | --force 绕过 + audit log，不阻塞工作流 |
| hook 执行耗时影响体验 | 低 | 只做静态检查（git status / 文件读取），不跑重操作 |
| AI 学会"绕过模式"（总是 --force） | 中 | audit log 中 --force 频率过高时主动提醒用户 |

## 待决策

- [ ] Pre-Done Gate 是否需要检查文档是否更新（docs/ 变更）？
- [ ] Gate 1 的编译检查是否需要限制项目类型（避免在非代码项目中报错）？
- [ ] 是否需要一个全局 `prog gate --disable` 临时关闭所有 Gate？
