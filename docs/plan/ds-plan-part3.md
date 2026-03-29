# PROG全量规范化计划 - 第三部分：收尾门禁与工作流集成（阶段2：收尾痛点MVP）

## 设计目标与原则

### 核心痛点修复
解决"done后main不完整、worktree尾巴未管"问题，确保每次`/prog-done`后都有明确的收尾状态，避免功能完成但未集成到主分支的情况。

### 设计原则
1. **强制收尾**：每次`/prog-done`必须产生明确的收尾结果（三选一）
2. **自动阻断**：未收尾的feature自动阻断`/prog-next`，防止跳过
3. **安全清理**：脏worktree绝不自动删除，提供明确修复路径
4. **状态追溯**：所有收尾决策记录审计，便于问题排查
5. **用户友好**：错误提示明确，修复动作可执行

## 收尾三选一状态机详细设计

### 状态定义与语义
```python
INTEGRATION_STATUS_CHOICES = {
    "finish_pending": "等待收尾",  # 默认状态，需进一步处理
    "merged_and_cleaned": "已合并且清理",  # 代码已合并到主分支，worktree已清理
    "pr_open": "PR已打开",  # 代码已提交，PR等待合并
    "kept_with_reason": "有原因保留"  # 有明确原因保留分支/worktree
}

CLEANUP_STATUS_CHOICES = {
    "pending": "待清理",  # worktree需要清理
    "done": "已清理",  # worktree已清理
    "skipped": "已跳过"  # 跳过清理（如保留worktree）
}
```

### 合法状态组合矩阵
| lifecycle_state | integration_status | 是否合法 | 说明 |
|-----------------|-------------------|----------|------|
| proposed | finish_pending | ✅ 合法 | 提案阶段，尚未开始实施 |
| approved | finish_pending | ✅ 合法 | 已批准，等待实施 |
| implementing | finish_pending | ✅ 合法 | 实施中，未完成 |
| verified | finish_pending | ✅ 合法 | 已验证，等待收尾 |
| verified | merged_and_cleaned | ✅ 合法 | 已完成合并和清理 |
| verified | pr_open | ✅ 合法 | 已验证，PR已打开 |
| verified | kept_with_reason | ✅ 合法 | 已验证，有保留原因 |
| archived | merged_and_cleaned | ✅ 合法 | 已归档，清理完成 |
| archived | kept_with_reason | ✅ 合法 | 已归档，有保留原因 |
| proposed | merged_and_leaned | ❌ 非法 | 提案阶段不能已完成合并 |
| implementing | merged_and_cleaned | ❌ 非法 | 实施中不能已完成合并 |
| archived | finish_pending | ❌ 非法 | 已归档不能等待收尾 |

### 状态转换约束规则
1. **only** `verified`或`archived`的feature才能设置非`finish_pending`的收尾状态
2. `merged_and_cleaned`必须同时设置`cleanup_status=done`
3. `pr_open`允许`cleanup_status=pending`（等待PR合并后清理）
4. `kept_with_reason`必须有`finish_reason`字段，且长度>10字符
5. 从其他状态回退到`finish_pending`时，必须重置`cleanup_status=pending`

## `/prog-done`收尾门禁实现

### 扩展后的`complete_feature`流程
```python
def complete_feature(feature_id: str, force: bool = False) -> Dict:
    """扩展的complete_feature，增加收尾门禁"""
    with TransactionManager() as tx:
        # 1. 执行原有验收逻辑（保持不变）
        feature = get_feature(feature_id)
        if not force:
            validate_acceptance_tests(feature)

        # 2. 设置生命周期状态为verified
        set_lifecycle_state(feature_id, "verified",
                           reason="验收通过，功能完成")

        # 3. 触发收尾门禁（新增核心逻辑）
        result = apply_finish_gate(feature_id)

        # 4. 记录审计
        tx.add_update(feature_id, "feature_completed",
                     f"功能完成，收尾状态: {result['integration_status']}")

        return result
```

### `apply_finish_gate`算法（核心门禁）
```python
def apply_finish_gate(feature_id: str) -> Dict:
    """收尾门禁：强制三选一收尾状态"""
    feature = get_feature(feature_id)
    project_root = get_project_root()
    git_root = get_git_root(project_root)

    # 1. 检查git状态
    is_clean = is_working_directory_clean(git_root)
    current_branch = get_current_branch(git_root)
    is_main_branch = current_branch in ["main", "master"]

    # 2. 自动检测收尾状态
    if is_main_branch and is_clean:
        # 已在主分支且干净 → merged_and_cleaned
        return {
            "integration_status": "merged_and_cleaned",
            "cleanup_status": "done",
            "integration_ref": get_current_commit_hash(git_root),
            "finish_reason": "已在主分支且工作目录干净"
        }

    elif is_clean and not is_main_branch:
        # 在非主分支且干净 → 检查是否已推送/PR
        remote_branch = get_remote_branch(git_root, current_branch)
        if remote_branch and "pull" in remote_branch:
            # 已关联PR
            return {
                "integration_status": "pr_open",
                "cleanup_status": "pending",
                "integration_ref": remote_branch,
                "finish_reason": "分支已推送，PR等待合并"
            }
        else:
            # 干净分支但未推送，询问用户
            return prompt_finish_choice(feature_id, current_branch)

    else:
        # 脏worktree → 必须用户决策
        return handle_dirty_worktree(feature_id, current_branch, is_clean)
```

### 用户交互决策点（使用input()，需要改为参数化）
```python
def prompt_finish_choice(feature_id: str, branch: str) -> Dict:
    """交互式收尾决策（当自动检测不明确时）"""
    print(f"功能 {feature_id} 已完成，但收尾状态不明确")
    print(f"当前分支: {branch}")
    print("请选择收尾方式:")
    print("1. 合并到主分支并清理 (merged_and_cleaned)")
    print("2. 创建PR等待审查 (pr_open)")
    print("3. 保留当前状态，稍后处理 (kept_with_reason)")

    choice = input("选择 (1/2/3): ").strip()

    if choice == "1":
        # 执行合并流程
        merge_to_main(branch)
        return {
            "integration_status": "merged_and_cleaned",
            "cleanup_status": "done",
            "finish_reason": "用户选择合并到主分支"
        }
    elif choice == "2":
        pr_url = create_pull_request(branch)
        return {
            "integration_status": "pr_open",
            "cleanup_status": "pending",
            "integration_ref": pr_url,
            "finish_reason": "用户选择创建PR"
        }
    else:
        reason = input("请输入保留原因: ").strip()
        if len(reason) < 10:
            reason = "用户选择保留，未提供详细原因"
        return {
            "integration_status": "kept_with_reason",
            "cleanup_status": "pending",
            "finish_reason": reason
        }
```

## worktree清理规则与脏worktree处理策略

### worktree状态检测
```python
def analyze_worktree_state(feature_id: str) -> Dict:
    """分析worktree状态，决定清理策略"""
    worktree_path = get_feature_worktree(feature_id)

    if not worktree_path or not worktree_path.exists():
        return {"exists": False, "status": "not_found"}

    # 检查是否当前工作目录
    is_current = os.path.samefile(worktree_path, os.getcwd())

    # 检查git状态
    git_status = get_git_status(worktree_path)
    is_dirty = git_status["has_changes"]
    uncommitted_files = git_status["uncommitted_files"]

    # 检查是否有未推送提交
    unpushed_commits = get_unpushed_commits(worktree_path)

    return {
        "exists": True,
        "is_current": is_current,
        "is_dirty": is_dirty,
        "uncommitted_files": uncommitted_files,
        "unpushed_commits": unpushed_commits,
        "can_auto_clean": not is_dirty and not unpushed_commits
    }
```

### 脏worktree处理策略矩阵
| worktree状态 | 自动清理 | 用户提示 | cleanup_status |
|-------------|----------|----------|----------------|
| **干净 + 无未推送** | ✅ 自动删除 | 无 | `done` |
| **干净 + 有未推送** | ❌ 不删除 | "有未推送提交，请先推送" | `pending` |
| **脏 + 未提交变更** | ❌ 不删除 | "有未提交变更，请提交或丢弃" | `pending` |
| **当前工作目录** | ❌ 不删除 | "当前位于该worktree，请切换到其他目录" | `pending` |
| **不存在** | ✅ 无操作 | 无 | `skipped` |

### 安全清理算法（使用shutil.rmtree()，需要改为git命令）
```python
def safe_cleanup_worktree(feature_id: str, worktree_state: Dict) -> bool:
    """安全清理worktree，绝不自动删除脏worktree"""
    if not worktree_state["exists"]:
        return True  # 无需清理

    if worktree_state["is_current"]:
        print("❌ 错误: 当前位于待清理的worktree中")
        print("请切换到其他目录后执行:")
        print(f"  cd .. && prog-cleanup-worktree {feature_id}")
        return False

    if worktree_state["is_dirty"]:
        print("❌ 工作目录有未提交变更:")
        for file in worktree_state["uncommitted_files"][:5]:
            print(f"  - {file}")
        print("请先提交或丢弃变更:")
        print(f"  cd {worktree_state['path']}")
        print("  # 提交: git add . && git commit -m '清理前提交'")
        print("  # 丢弃: git checkout -- . && git clean -fd")
        return False

    if worktree_state["unpushed_commits"]:
        print("⚠️  有未推送提交，建议先推送:")
        print(f"  cd {worktree_state['path']}")
        print("  git push origin HEAD")
        response = input("仍要删除未推送分支？(y/N): ")
        if response.lower() != "y":
            return False

    # 安全删除（需要改为git worktree remove）
    try:
        shutil.rmtree(worktree_state["path"])
        print(f"✅ 已清理worktree: {worktree_state['path']}")
        return True
    except Exception as e:
        print(f"❌ 清理失败: {e}")
        return False
```

### 一键清理命令（新增）
```bash
# 新增命令：清理指定feature的worktree
prog-cleanup-worktree <feature_id>

# 行为：
# 1. 检查worktree状态
# 2. 如果干净则自动删除
# 3. 如果脏则提供明确的修复步骤
# 4. 更新cleanup_status
```

## finish_pending阻断`/prog-next`逻辑

### 阻断检查算法
```python
def check_finish_gate_blocking() -> List[str]:
    """检查哪些feature因收尾未完成而被阻断"""
    blocked_features = []

    for feature in get_all_features():
        # 规则1：integration_status=finish_pending的verified/archived feature
        if feature.get("lifecycle_state") in ["verified", "archived"]:
            if feature.get("integration_status") == "finish_pending":
                blocked_features.append({
                    "feature_id": feature["id"],
                    "reason": "verified但未收尾",
                    "required_action": "运行 /prog-done 设置收尾状态"
                })

        # 规则2：cleanup_status=pending的merged_and_cleaned/pr_open
        if feature.get("integration_status") in ["merged_and_cleaned", "pr_open"]:
            if feature.get("cleanup_status") == "pending":
                blocked_features.append({
                    "feature_id": feature["id"],
                    "reason": f"{feature['integration_status']}但worktree未清理",
                    "required_action": f"运行 prog-cleanup-worktree {feature['id']}"
                })

        # 规则3：kept_with_reason但无有效原因
        if feature.get("integration_status") == "kept_with_reason":
            if not feature.get("finish_reason") or len(feature["finish_reason"]) < 10:
                blocked_features.append({
                    "feature_id": feature["id"],
                    "reason": "保留但原因不充分",
                    "required_action": "补充保留原因（>10字符）"
                })

    return blocked_features
```

### `/prog-next`扩展实现
```python
def prog_next_command():
    """扩展的/prog-next，增加收尾门禁检查"""
    # 1. 检查阻断
    blocked = check_finish_gate_blocking()
    if blocked:
        print("❌ 无法开始新功能，以下功能需要先收尾:")
        for block in blocked:
            print(f"  • {block['feature_id']}: {block['reason']}")
            print(f"    需要: {block['required_action']}")
        print("\n请先处理上述问题，再运行 /prog-next")
        return

    # 2. 执行原有选择逻辑
    next_feature = select_next_feature()

    # 3. 开始新功能
    set_current_feature(next_feature["id"])
    print(f"✅ 开始功能: {next_feature['name']}")
```

### 硬规则执行（需要为修复动作添加白名单）
```python
# 不可绕过的规则（在transaction层面强制执行）
HARD_BLOCK_RULES = [
    # 规则1：任何状态变更前检查finish_pending
    lambda feature: feature.get("lifecycle_state") == "verified"
                    and feature.get("integration_status") == "finish_pending"
                    and "不能修改verified但未收尾的功能",

    # 规则2：不能设置除finish_pending外的收尾状态给非verified/archived
    lambda feature: feature.get("integration_status") != "finish_pending"
                    and feature.get("lifecycle_state") not in ["verified", "archived"]
                    and "只有verified/archived功能才能设置收尾状态",
]
```

## 超时策略与二次确认机制

### 超时检测算法
```python
def check_finish_timeouts() -> List[Dict]:
    """检测超时未处理的收尾状态"""
    timeouts = []
    now = datetime.now()

    for feature in get_all_features():
        # 1. finish_pending超过7天
        if feature.get("integration_status") == "finish_pending":
            completed_at = parse_iso8601(feature.get("completed_at"))
            if completed_at and (now - completed_at).days > 7:
                timeouts.append({
                    "feature_id": feature["id"],
                    "type": "finish_pending_timeout",
                    "days": (now - completed_at).days,
                    "action": "强制要求设置收尾状态"
                })

        # 2. cleanup_pending超过3天
        if feature.get("cleanup_status") == "pending":
            last_update = get_last_update_time(feature["id"], "cleanup")
            if last_update and (now - last_update).days > 3:
                timeouts.append({
                    "feature_id": feature["id"],
                    "type": "cleanup_pending_timeout",
                    "days": (now - last_update).days,
                    "action": "提醒清理worktree"
                })

        # 3. pr_open超过14天
        if feature.get("integration_status") == "pr_open":
            pr_created = parse_iso8601(feature.get("integration_created_at"))
            if pr_created and (now - pr_created).days > 14:
                timeouts.append({
                    "feature_id": feature["id"],
                    "type": "pr_stale_timeout",
                    "days": (now - pr_created).days,
                    "action": "检查PR状态或关闭"
                })

    return timeouts
```

### 二次确认机制
```python
def require_reconfirmation(feature_id: str, reason: str) -> bool:
    """对于超时或异常状态，要求用户二次确认"""
    feature = get_feature(feature_id)

    print(f"⚠️  功能 {feature_id} 需要二次确认:")
    print(f"   状态: {feature.get('integration_status')}")
    print(f"   原因: {reason}")
    print(f"   最后更新: {feature.get('completed_at')}")
    print()
    print("请确认是否继续:")
    print("1. 继续并更新状态")
    print("2. 稍后处理（24小时内不再提示）")
    print("3. 标记为需人工检查")

    choice = input("选择 (1/2/3): ").strip()

    if choice == "1":
        return True
    elif choice == "2":
        # 设置24小时免打扰
        set_snooze_until(feature_id, now + timedelta(days=1))
        return False
    else:
        # 标记为需人工检查
        add_update(feature_id, "manual_review_needed",
                  f"用户要求人工检查: {reason}")
        return False
```

## 集成点与现有代码兼容性

### 现有命令扩展点
| 现有命令 | 修改点 | 兼容性保证 |
|----------|--------|------------|
| `/prog-done` | 增加`apply_finish_gate()`调用 | ✅ 原有验收逻辑不变，仅新增收尾状态 |
| `/prog-next` | 增加`check_finish_gate_blocking()`检查 | ✅ 原有选择逻辑不变，仅新增前置检查 |
| `/prog`状态显示 | 显示`integration_status`和`cleanup_status` | ✅ 新增字段，不影响原有显示 |
| `set-development-stage` | 状态映射时初始化收尾字段 | ✅ 新增字段默认值 |

### 向后兼容处理
```python
def migrate_legacy_finish_state(feature: Dict) -> Dict:
    """迁移旧版本的功能完成状态到新收尾模型"""
    # 旧版本：只有completed=true，没有收尾状态
    if feature.get("completed") and "integration_status" not in feature:
        # 推断收尾状态
        if feature.get("development_stage") == "completed":
            # 假设已合并
            feature["integration_status"] = "merged_and_cleaned"
            feature["cleanup_status"] = "done"
            feature["finish_reason"] = "从v2.0迁移，假设已合并"
        else:
            # 未明确状态
            feature["integration_status"] = "finish_pending"
            feature["cleanup_status"] = "pending"

        add_update(feature["id"], "finish_state_migrated",
                  f"从v2.0迁移收尾状态: {feature['integration_status']}")

    return feature
```

### 新增命令（仅排障用）
```bash
# 1. 检查收尾状态
prog-check-finish-gates

# 输出:
# • feat-001: verified, finish_pending (需要收尾)
# • feat-002: merged_and_cleaned, cleanup_pending (需要清理worktree)
# • feat-003: pr_open, PR#123 (正常)

# 2. 强制设置收尾状态
prog-set-finish-state --feature-id <id> --status <status> --reason "<text>"

# 3. 清理worktree（安全模式）
prog-cleanup-worktree <feature_id>
```

## 可观测指标（阶段2）

1. **finish_pending阻断命中率** = `被阻断的/prog-next次数 / 总/prog-next调用`
2. **未收尾进入next的漏拦截率** = `成功绕过收尾门禁的次数 / 总/prog-next调用`
3. **自动收尾决策成功率** = `自动确定收尾状态的次数 / 总/prog-done调用`
4. **脏worktree处理成功率** = `成功处理的脏worktree数 / 总脏worktree数`
5. **超时检测准确率** = `正确检测的超时数 / 实际超时总数`
6. **用户决策平均时间** = `用户收尾决策总时间 / 需要交互决策的次数`

### 监控仪表板示例
```json
{
  "finish_gate_metrics": {
    "total_features": 15,
    "pending_finish": 2,
    "pending_cleanup": 1,
    "merged_and_cleaned": 8,
    "pr_open": 3,
    "kept_with_reason": 1,
    "blocked_next_attempts": 5,
    "avg_decision_time_seconds": 12.5
  },
  "timeout_alerts": [
    {"feature_id": "feat-012", "type": "finish_pending", "days": 8},
    {"feature_id": "feat-015", "type": "cleanup_pending", "days": 4}
  ]
}
```

### 每日自检任务（新增）
```python
def daily_self_check():
    """每日自动检查，输出报告"""
    print("=== Progress Tracker 每日自检 ===")

    # 1. 检查pending状态
    pending = check_finish_gate_blocking()
    if pending:
        print("❌ 待处理收尾:")
        for p in pending:
            print(f"  • {p['feature_id']}: {p['reason']}")

    # 2. 检查超时
    timeouts = check_finish_timeouts()
    if timeouts:
        print("⚠️  超时警告:")
        for t in timeouts:
            print(f"  • {t['feature_id']}: {t['type']} ({t['days']}天)")

    # 3. 检查脏worktree
    dirty = find_dirty_worktrees()
    if dirty:
        print("🧹 待清理worktree:")
        for d in dirty:
            print(f"  • {d['feature_id']}: {d['path']}")

    # 4. 检查状态脑裂
    conflicts = find_state_conflicts()
    if conflicts:
        print("🔧 状态冲突需修复:")
        for c in conflicts:
            print(f"  • {c['feature_id']}: {c['conflict']}")

    if not any([pending, timeouts, dirty, conflicts]):
        print("✅ 所有状态正常")
```

## P0修正项（用户反馈需要补充）

### 1. 自动判定 merged_and_cleaned 条件过宽
**问题**：当前"main + clean 即已收尾"会误判
**修正**：应改为"特性提交已并入主线（如 merge-base --is-ancestor）且工作树可安全清理"

### 2. 不要在核心库里用 input() 交互
**问题**：`/prog-*`流程里阻塞式 input() 不稳定
**修正**：改成命令参数或二段式流程：`/prog-done`返回待决策，再用 `prog-set-finish-state` 落盘

### 3. worktree 清理不能 shutil.rmtree()
**问题**：会留下 .git/worktrees 元数据垃圾
**修正**：必须走 `git worktree remove + git worktree prune`

### 4. /prog-next 阻断要分"硬阻断/软告警"
**问题**：当前全部硬阻断会过度阻塞正常PR流程
**修正**：
- **硬阻断**：finish_pending、无效 kept_with_reason、不一致状态
- **软告警**：pr_open + cleanup=pending（正常PR流程）

### 5. 硬规则1会误伤"修复动作"
**问题**："verified + finish_pending 禁止任何变更"会连设置收尾状态也挡住
**修正**：给 `set-finish-state`/`cleanup` 白名单例外

### 6. 超时与二次确认机制需补数据契约
**问题**：completed_at/last_update 可能缺失；now变量作用域也要固定
**修正**：
- 定义 `snooze_until` 字段
- 统一时区解析（UTC）
- 处理缺失时间字段的默认值

### 集成点说明
与当前代码集成是可行的，但属于"新增主流程"而非小改，因为当前核心仍是 `development_stage/completed`：

1. `progress_manager.py` (line 2086)
2. `progress_manager.py` (line 2382)
3. `progress_manager.py` (line 486)