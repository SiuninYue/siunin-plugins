# F14: 落地 wf_state_machine + wf_auto_driver + hook 自动推进

**Feature ID:** 14
**Date:** 2026-04-22
**Branch:** feature/feature-14
**Worktree:** /Users/siunin/Projects/Claude-Plugins/.worktrees/feature-14

## Goal

实现工作流状态机（wf_state_machine）、自动驱动器（wf_auto_driver）和 hook 自动推进机制，使 progress-tracker 在 Claude Code 的 Stop 和 UserPromptSubmit 生命周期事件中自动计算并写回 `pending_action`，无需人工触发。

## Architecture

```
Claude Code lifecycle event (Stop / UserPromptSubmit)
        │
        ▼
wf_auto_driver.py  (hook 入口，fail-open)
        │
        ├── 调用 progress_manager wf-auto-driver 子命令
        │         │
        │         └── 锁内: load → wf_state_machine.compute_next_action() → save(pending_action)
        │
        └── fail-open: 任何错误静默退出，不阻塞用户
```

### 核心组件

1. **`wf_state_machine.py`** - 纯函数 FSM
   - 无 I/O，无副作用，纯输入→输出
   - `compute_next_action(phase, context) → str | None`
   - `execution_complete` 阶段 → 触发 `run_prog_done` gate

2. **`wf_auto_driver.py`** - 薄层 driver
   - hook 入口，接收 Claude Code lifecycle 事件
   - fail-open：捕获所有异常，静默退出码 0
   - 委托给 `progress_manager wf-auto-driver` 子命令写回 `pending_action`

3. **`progress_manager` wf-auto-driver 子命令**
   - 使用现有 `acquire_lock` 保证原子性
   - load → `compute_next_action` → 写回 `workflow_state.pending_action`
   - 幂等：重复调用不改变最终状态

4. **hooks.json Stop + UPS 注册**
   - `Stop` hook → 调用 wf_auto_driver
   - `UserPromptSubmit` 已有 `auto-checkpoint`，追加 `wf-auto-driver`

## Tasks

### T1: [RED] 编写 wf_state_machine.py 失败测试

文件：`tests/test_wf_state_machine.py`

覆盖场景：
- `execution_complete` phase → pending_action 为 `run_prog_done`
- `execution` phase, tasks < total → pending_action 为 `continue_execution`
- `execution` phase, tasks == total → pending_action 为 `run_prog_done`
- `planning:draft` phase → pending_action 为 `resume_planning_draft`
- `planning:approved` phase → pending_action 为 `execute_approved_plan`
- `None` / unknown phase → pending_action 为 `None`（无操作）
- 纯函数性：相同输入产生相同输出，无副作用

预期 API：
```python
from wf_state_machine import compute_next_action

result = compute_next_action(
    phase="execution_complete",
    context={"completed_tasks": [1,2,3], "total_tasks": 3}
)
assert result == "run_prog_done"
```

### T2: [GREEN] 实现 wf_state_machine.py

文件：`hooks/scripts/wf_state_machine.py`

```python
"""
wf_state_machine.py — 纯函数工作流状态机

compute_next_action(phase, context) → str | None
- 无 I/O，无副作用
- execution_complete → "run_prog_done"
- execution + tasks_done == total → "run_prog_done"
- execution + tasks_done < total → "continue_execution"
- planning:draft → "resume_planning_draft"
- planning:approved → "execute_approved_plan"
- planning:clarifying → "resume_planning_clarifying"
- None/unknown → None
"""
```

验收：`pytest -q tests/test_wf_state_machine.py` 全绿

### T3: [RED] 编写 wf_auto_driver.py 失败测试

文件：`tests/test_wf_auto_driver.py`

覆盖场景：
- 正常路径：有 workflow_state → pending_action 写回
- fail-open：progress_manager 抛出异常 → 静默退出 0
- fail-open：progress.json 不存在 → 静默退出 0
- fail-open：no current_feature_id → 静默退出 0
- 幂等：重复调用同一 phase，pending_action 不变

集成断言（end-to-end）：
```python
def test_wf_auto_driver_writes_pending_action_end_to_end(tmp_path):
    # 搭建真实 progress.json（execution_complete phase）
    # 调用 wf_auto_driver.run()
    # 断言 progress.json 中 workflow_state.pending_action == "run_prog_done"
```

### T4: [GREEN] 实现 wf_auto_driver.py

文件：`hooks/scripts/wf_auto_driver.py`

```python
"""
wf_auto_driver.py — 薄层自动驱动器（hook 入口）

职责：
1. 读取当前 workflow_state.phase
2. 调用 wf_state_machine.compute_next_action()
3. 写回 pending_action（在锁内，通过 progress_manager）
4. fail-open：任何错误静默退出 0

入口：python wf_auto_driver.py [--project-root <path>]
"""

def run(project_root=None) -> None:
    try:
        _drive(project_root)
    except Exception:
        pass  # fail-open

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    run(args.project_root)
```

验收：`pytest -q tests/test_wf_auto_driver.py` 全绿

### T5: progress_manager 添加 wf-auto-driver 子命令

文件：`hooks/scripts/progress_manager.py`

CLI 接口：
```bash
plugins/progress-tracker/prog wf-auto-driver [--project-root <path>]
```

实现要求：
- 在 `acquire_lock` 上下文内执行（原子性）
- load → `compute_next_action(phase, context)` → 写回 `workflow_state.pending_action`
- 无 current_feature_id 时静默返回（退出 0）
- 无 workflow_state 时静默返回（退出 0）
- 幂等

### T6: hooks.json 注册 Stop + UPS hook，补充集成断言

文件：`hooks/hooks.json`

添加 `Stop` hook：
```json
"Stop": [
  {
    "matcher": "*",
    "hooks": [
      {
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh wf-auto-driver",
        "timeout": 5000
      }
    ]
  }
]
```

在 `UserPromptSubmit` 追加（auto-checkpoint 之后）：
```json
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh wf-auto-driver",
  "timeout": 5000
}
```

确保 `run-hook.sh` 路由 `wf-auto-driver` 到 `wf_auto_driver.py`。

集成断言：
```python
def test_hooks_json_has_stop_and_ups_wf_auto_driver():
    hooks = json.load(open("hooks/hooks.json"))
    stop_commands = [h["command"] for entry in hooks["hooks"]["Stop"] for h in entry["hooks"]]
    assert any("wf-auto-driver" in c for c in stop_commands)
    ups_commands = [h["command"] for entry in hooks["hooks"]["UserPromptSubmit"] for h in entry["hooks"]]
    assert any("wf-auto-driver" in c for c in ups_commands)
```

## Tasks Summary

| # | Task | File(s) | Type |
|---|------|---------|------|
| T1 | 编写 wf_state_machine 失败测试 | `tests/test_wf_state_machine.py` | RED |
| T2 | 实现 wf_state_machine.py | `hooks/scripts/wf_state_machine.py` | GREEN |
| T3 | 编写 wf_auto_driver 失败测试 | `tests/test_wf_auto_driver.py` | RED |
| T4 | 实现 wf_auto_driver.py | `hooks/scripts/wf_auto_driver.py` | GREEN |
| T5 | progress_manager wf-auto-driver 子命令 | `hooks/scripts/progress_manager.py` | GREEN |
| T6 | hooks.json 注册 + 集成断言 | `hooks/hooks.json`, tests | GREEN+ASSERT |

## Acceptance Criteria

- [ ] `pytest -q plugins/progress-tracker/tests/test_wf_state_machine.py` 全绿
- [ ] `pytest -q plugins/progress-tracker/tests/test_wf_auto_driver.py` 全绿
- [ ] `plugins/progress-tracker/prog wf-auto-driver --project-root plugins/progress-tracker` 成功执行
- [ ] hooks.json 包含 Stop 和 UserPromptSubmit 的 wf-auto-driver 条目
- [ ] 集成断言验证 end-to-end pending_action 写回路径

## Acceptance Mapping

| Acceptance Scenario | Tasks |
|---------------------|-------|
| 新增 wf_state_machine.py 纯函数 compute_next_action 与 wf_auto_driver.py hook 入口 | T1, T2, T3, T4 |
| 运行: pytest -q tests/test_wf_state_machine.py | T1, T2 |
| 运行: pytest -q tests/test_wf_auto_driver.py | T3, T4 |

## Risks

- **progress_manager.py 体积大**：T5 添加子命令需精确定位注入点，避免破坏现有功能
- **run-hook.sh 路由**：需确认 run-hook.sh 的命令分发机制，正确路由 wf-auto-driver
- **fail-open 设计**：wf_auto_driver 捕获所有异常确保不阻塞用户，但可能掩盖配置错误
