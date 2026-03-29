# PROG全量规范化计划 - 第三部分：收尾门禁与工作流集成（阶段2：收尾痛点MVP）- 修正版

## 设计目标与原则

### 核心痛点修复
解决"done后main不完整、worktree尾巴未管"问题，确保每次`/prog-done`后都有明确的收尾状态，避免功能完成但未集成到主分支的情况。

### 设计原则
1. **强制收尾**：每次`/prog-done`必须产生明确的收尾结果（三选一）
2. **分层阻断**：未收尾的feature分层阻断`/prog-next`（硬阻断+软告警）
3. **安全清理**：脏worktree绝不自动删除，使用git原生命令清理
4. **非交互式**：避免阻塞式input()，采用参数化或二段式流程
5. **状态追溯**：所有收尾决策记录审计，便于问题排查
6. **修复友好**：为修复动作提供白名单例外，避免自锁

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

### 合法状态组合矩阵与修复白名单
| lifecycle_state | integration_status | 是否合法 | 允许的修复动作 |
|-----------------|-------------------|----------|----------------|
| proposed | finish_pending | ✅ 合法 | 所有状态变更 |
| approved | finish_pending | ✅ 合法 | 所有状态变更 |
| implementing | finish_pending | ✅ 合法 | 所有状态变更 |
| verified | finish_pending | ✅ 合法 | **仅限**：set-finish-state, cleanup, 生命周期回退 |
| verified | merged_and_cleaned | ✅ 合法 | 所有状态变更 |
| verified | pr_open | ✅ 合法 | 所有状态变更 |
| verified | kept_with_reason | ✅ 合法 | 所有状态变更 |
| archived | merged_and_cleaned | ✅ 合法 | 所有状态变更 |
| archived | kept_with_reason | ✅ 合法 | 所有状态变更 |
| proposed | merged_and_cleaned | ❌ 非法 | 自动修复为finish_pending |
| implementing | merged_and_cleaned | ❌ 非法 | 自动修复为finish_pending |
| archived | finish_pending | ❌ 非法 | 自动修复为kept_with_reason |

### 状态转换约束规则
1. **only** `verified`或`archived`的feature才能设置非`finish_pending`的收尾状态
2. `merged_and_cleaned`必须同时设置`cleanup_status=done`
3. `pr_open`允许`cleanup_status=pending`（等待PR合并后清理）
4. `kept_with_reason`必须有`finish_reason`字段，且长度>10字符
5. 从其他状态回退到`finish_pending`时，必须重置`cleanup_status=pending`

### 修复动作白名单定义
```python
FINISH_PENDING_WHITELISTED_ACTIONS = {
    "set-finish-state",    # 设置收尾状态
    "cleanup-worktree",    # 清理worktree
    "set-lifecycle-state", # 生命周期状态变更（仅允许回退到implementing）
    "add-update",          # 添加审计记录
    "validate-feature"     # 验证功能状态
}
```

## `/prog-done`收尾门禁实现（修正版）

### 扩展后的`complete_feature`流程（二段式设计）
```python
def complete_feature(feature_id: str, force: bool = False,
                    finish_choice: Optional[str] = None,
                    finish_reason: Optional[str] = None) -> Dict:
    """扩展的complete_feature，二段式收尾门禁"""
    with TransactionManager() as tx:
        # 1. 执行原有验收逻辑（保持不变）
        feature = get_feature(feature_id)
        if not force:
            validate_acceptance_tests(feature)

        # 2. 设置生命周期状态为verified
        set_lifecycle_state(feature_id, "verified",
                           reason="验收通过，功能完成")

        # 3. 触发收尾门禁（二段式：自动检测或使用参数）
        if finish_choice:
            # 直接使用参数设置收尾状态
            result = apply_finish_choice(feature_id, finish_choice, finish_reason)
        else:
            # 自动检测并返回待决策信息
            result = detect_finish_state(feature_id)
            if result["requires_decision"]:
                # 返回待决策信息，不落盘
                return {
                    "status": "pending_decision",
                    "choices": result["available_choices"],
                    "recommendation": result["recommended_choice"],
                    "next_command": f"prog-set-finish-state --feature-id {feature_id} --status <choice>"
                }

        # 4. 记录审计
        tx.add_update(feature_id, "feature_completed",
                     f"功能完成，收尾状态: {result['integration_status']}")

        return {"status": "completed", **result}
```

### `detect_finish_state`算法（基于git历史的精确检测）
```python
def detect_finish_state(feature_id: str) -> Dict:
    """精确检测收尾状态，基于git历史而非简单分支检查"""
    feature = get_feature(feature_id)
    project_root = get_project_root()
    git_root = get_git_root(project_root)

    # 获取feature相关提交（通过worktree或分支关联）
    feature_commits = get_feature_commits(feature_id)
    current_branch = get_current_branch(git_root)
    is_clean = is_working_directory_clean(git_root)

    available_choices = []
    recommended_choice = None

    # 修正1：检查是否已并入主线（使用merge-base --is-ancestor）
    if feature_commits and is_merged_into_main(feature_commits, git_root):
        # 提交已并入主线
        if is_clean:
            # 工作目录干净，可标记为merged_and_cleaned
            available_choices.append("merged_and_cleaned")
            recommended_choice = "merged_and_cleaned"
        else:
            # 工作目录脏，但已合并
            available_choices.append("merged_and_cleaned")
            available_choices.append("kept_with_reason")
            recommended_choice = "merged_and_cleaned"

    # 检查是否有关联PR
    pr_info = get_associated_pr(current_branch, git_root)
    if pr_info:
        available_choices.append("pr_open")
        if not recommended_choice:
            recommended_choice = "pr_open"

    # 默认选项
    available_choices.append("kept_with_reason")
    if not recommended_choice:
        recommended_choice = "kept_with_reason"

    return {
        "requires_decision": len(available_choices) > 1 or recommended_choice == "kept_with_reason",
        "available_choices": available_choices,
        "recommended_choice": recommended_choice,
        "current_branch": current_branch,
        "is_clean": is_clean,
        "pr_info": pr_info,
        "is_merged": feature_commits and is_merged_into_main(feature_commits, git_root)
    }

def is_merged_into_main(feature_commits: List[str], git_root: Path) -> bool:
    """使用git merge-base --is-ancestor检查feature所有提交是否已并入主线

    算法：
    1. 首先检查tip commit（最后一个提交）- 如果tip未合并，整个feature不可能已合并
    2. 然后验证所有feature提交都已并入主线（不只是任一提交）
    3. 只有所有提交都已并入才返回True，避免误判

    保守原则：任何git命令失败或检查失败都返回False
    """
    if not feature_commits:
        return False  # 无提交可检查

    try:
        # 首先检查tip commit（最后一个提交）
        tip_commit = feature_commits[-1]
        tip_merged = False
        for main_branch in ["main", "master", "origin/main", "origin/master"]:
            cmd = ["git", "-C", str(git_root), "merge-base", "--is-ancestor", tip_commit, main_branch]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                tip_merged = True
                break

        if not tip_merged:
            return False  # tip commit未合并，整个feature不可能已合并

        # tip commit已合并，验证所有提交都已并入
        for commit in feature_commits:
            commit_merged = False
            for main_branch in ["main", "master", "origin/main", "origin/master"]:
                cmd = ["git", "-C", str(git_root), "merge-base", "--is-ancestor", commit, main_branch]
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode == 0:
                    commit_merged = True
                    break

            if not commit_merged:
                return False  # 有提交未合并

        return True  # 所有提交都已合并
    except Exception:
        # 如果git命令失败，保守返回False
        return False
```

### `prog-set-finish-state`命令（新增，用于二段式落盘）
```bash
# 用法：设置收尾状态（用于二段式流程）
prog-set-finish-state --feature-id <id> --status <status> [--reason "<text>"]

# 示例：
prog-set-finish-state --feature-id feat-001 --status merged_and_cleaned
prog-set-finish-state --feature-id feat-002 --status pr_open --reason "等待代码审查"
prog-set-finish-state --feature-id feat-003 --status kept_with_reason --reason "需要UX评审"

# 与/prog-done配合使用：
# 第一步：/prog-done feat-001
# 输出：需要决策，建议运行 prog-set-finish-state --feature-id feat-001 --status merged_and_cleaned
# 第二步：prog-set-finish-state --feature-id feat-001 --status merged_and_cleaned
```

### `apply_finish_choice`实现（参数化，无input()）
```python
def apply_finish_choice(feature_id: str, choice: str, reason: Optional[str] = None) -> Dict:
    """应用收尾选择（参数化，无交互），包含状态组合校验"""
    # 获取当前feature状态
    feature = get_feature(feature_id)
    lifecycle = feature.get("lifecycle_state")

    # 校验目标状态组合合法性（与part2状态矩阵规则一致）
    if choice != "finish_pending":
        if lifecycle not in ["verified", "archived"]:
            raise ValueError(f"只有verified/archived功能才能设置收尾状态 {choice}，当前状态: {lifecycle}")

        if choice == "pr_open" and lifecycle != "verified":
            raise ValueError(f"pr_open收尾状态仅允许verified功能，当前状态: {lifecycle}")

        if choice == "kept_with_reason" and lifecycle not in ["verified", "archived"]:
            raise ValueError(f"kept_with_reason收尾状态仅允许verified/archived功能，当前状态: {lifecycle}")

        if choice == "merged_and_cleaned" and lifecycle not in ["verified", "archived"]:
            raise ValueError(f"merged_and_cleaned收尾状态仅允许verified/archived功能，当前状态: {lifecycle}")

    if choice == "merged_and_cleaned":
        return {
            "integration_status": "merged_and_cleaned",
            "cleanup_status": "done",
            "integration_ref": get_current_commit_hash(get_git_root(get_project_root())),
            "finish_reason": reason or "用户选择合并到主分支"
        }

    elif choice == "pr_open":
        # 自动创建PR或使用现有
        pr_url = get_or_create_pr(feature_id)
        return {
            "integration_status": "pr_open",
            "cleanup_status": "pending",
            "integration_ref": pr_url,
            "finish_reason": reason or "用户选择创建PR"
        }

    elif choice == "kept_with_reason":
        if not reason or len(reason) < 10:
            raise ValueError("kept_with_reason必须提供至少10字符的原因")
        return {
            "integration_status": "kept_with_reason",
            "cleanup_status": "pending",
            "finish_reason": reason
        }

    else:
        raise ValueError(f"无效的收尾选择: {choice}")
```

## worktree清理规则（修正：使用git原生命令）

### worktree状态检测
```python
def analyze_worktree_state(feature_id: str) -> Dict:
    """分析worktree状态，决定清理策略"""
    worktree_path = get_feature_worktree(feature_id)

    if not worktree_path or not worktree_path.exists():
        # 始终包含path字段，即使为None，避免清理函数KeyError
        return {"exists": False, "status": "not_found", "path": None}

    # 检查是否当前工作目录
    is_current = os.path.samefile(worktree_path, os.getcwd())

    # 检查git状态
    git_status = get_git_status(worktree_path)
    is_dirty = git_status["has_changes"]
    uncommitted_files = git_status["uncommitted_files"]

    # 检查是否有未推送提交
    unpushed_commits = get_unpushed_commits(worktree_path)

    # 检查是否为合法git worktree
    is_valid_worktree = is_git_worktree(worktree_path)

    return {
        "exists": True,
        "path": worktree_path,
        "is_current": is_current,
        "is_dirty": is_dirty,
        "is_valid_worktree": is_valid_worktree,
        "uncommitted_files": uncommitted_files,
        "unpushed_commits": unpushed_commits,
        "can_auto_clean": not is_dirty and not unpushed_commits and is_valid_worktree
    }
```

### 安全清理算法（使用git worktree命令）
```python
def safe_cleanup_worktree(feature_id: str, worktree_state: Dict, force: bool = False) -> bool:
    """安全清理worktree，使用git原生命令"""
    if not worktree_state["exists"]:
        return True  # 无需清理

    if worktree_state["is_current"]:
        print("❌ 错误: 当前位于待清理的worktree中")
        print("请切换到其他目录后执行:")
        print(f"  cd .. && prog-cleanup-worktree {feature_id}")
        return False

    if not worktree_state["is_valid_worktree"]:
        print("❌ 错误: 不是有效的git worktree")
        print("请手动检查目录结构")
        return False

    if worktree_state["is_dirty"] and not force:
        print("❌ 工作目录有未提交变更:")
        for file in worktree_state["uncommitted_files"][:5]:
            print(f"  - {file}")
        print("请先提交或丢弃变更，或使用--force参数:")
        print(f"  cd {worktree_state['path']}")
        print("  # 提交: git add . && git commit -m '清理前提交'")
        print("  # 丢弃: git checkout -- . && git clean -fd")
        print(f"  # 强制: prog-cleanup-worktree {feature_id} --force")
        return False

    if worktree_state["unpushed_commits"] and not force:
        print("⚠️  有未推送提交，建议先推送:")
        print(f"  cd {worktree_state['path']}")
        print("  git push origin HEAD")
        print("或使用--force参数强制删除")
        return False

    # 修正3：使用git worktree remove（不是shutil.rmtree）
    try:
        worktree_path = worktree_state["path"]
        if not worktree_path:
            print("❌ worktree路径为空")
            return False

        git_root = get_git_root(worktree_path)

        # 使用绝对路径更可靠
        abs_worktree_path = worktree_path.resolve()

        # 执行git worktree remove，--force参数放在路径前避免解析歧义
        cmd = ["git", "-C", str(git_root), "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(abs_worktree_path))

        subprocess.run(cmd, check=True, capture_output=True)

        # 可选：清理残留元数据
        cmd_prune = ["git", "-C", str(git_root), "worktree", "prune"]
        subprocess.run(cmd_prune, check=False, capture_output=True)

        print(f"✅ 已清理worktree: {abs_worktree_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ git worktree remove失败: {e.stderr.decode().strip()}")
        return False
    except Exception as e:
        print(f"❌ 清理失败: {e}")
        return False
```

### `prog-cleanup-worktree`命令实现
```python
def prog_cleanup_worktree_command(feature_id: str, force: bool = False):
    """清理worktree命令实现"""
    worktree_state = analyze_worktree_state(feature_id)

    if not worktree_state["exists"]:
        print(f"✅ 功能 {feature_id} 无worktree需要清理")
        update_cleanup_status(feature_id, "skipped", "无worktree")
        return

    success = safe_cleanup_worktree(feature_id, worktree_state, force)

    if success:
        update_cleanup_status(feature_id, "done", "成功清理worktree")
    elif force:
        # 即使失败也更新状态（用户明确要求强制）
        update_cleanup_status(feature_id, "skipped", f"强制清理失败: {worktree_state['path']}")
    else:
        update_cleanup_status(feature_id, "pending", "等待用户处理")
```

## finish_pending阻断`/prog-next`逻辑（分层设计）

### 分层阻断检查算法
```python
def check_finish_gate_blocking() -> Tuple[List[Dict], List[Dict]]:
    """分层检查：返回(硬阻断列表, 软告警列表)"""
    hard_blocks = []
    soft_warnings = []

    for feature in get_all_features():
        feature_id = feature["id"]
        lifecycle = feature.get("lifecycle_state")
        integration = feature.get("integration_status")
        cleanup = feature.get("cleanup_status")
        finish_reason = feature.get("finish_reason", "")

        # === 硬阻断条件 ===

        # 1. verified但未收尾
        if lifecycle == "verified" and integration == "finish_pending":
            hard_blocks.append({
                "feature_id": feature_id,
                "reason": "verified但未收尾",
                "required_action": "运行 /prog-done 或 prog-set-finish-state 设置收尾状态",
                "severity": "blocking"
            })

        # 2. kept_with_reason但原因不充分
        if integration == "kept_with_reason" and len(finish_reason) < 10:
            hard_blocks.append({
                "feature_id": feature_id,
                "reason": "保留但原因不充分（<10字符）",
                "required_action": "补充保留原因：prog-set-finish-state --feature-id {feature_id} --status kept_with_reason --reason \"详细原因\"",
                "severity": "blocking"
            })

        # 3. 状态不一致（非法组合）
        if not is_valid_state_combo(lifecycle, integration):
            hard_blocks.append({
                "feature_id": feature_id,
                "reason": f"状态不一致: {lifecycle}+{integration}",
                "required_action": "运行 prog-fix-state --feature-id {feature_id} 修复状态",
                "severity": "blocking"
            })

        # === 软告警条件 ===

        # 1. pr_open但cleanup=pending（正常PR流程）
        if integration == "pr_open" and cleanup == "pending":
            soft_warnings.append({
                "feature_id": feature_id,
                "reason": "PR已打开，但worktree未清理",
                "suggested_action": "PR合并后运行 prog-cleanup-worktree {feature_id}",
                "severity": "warning"
            })

        # 2. merged_and_cleaned但cleanup=pending（非法组合，改为硬阻断）
        if integration == "merged_and_cleaned" and cleanup == "pending":
            hard_blocks.append({
                "feature_id": feature_id,
                "reason": "已合并但worktree未清理（状态不一致）",
                "required_action": "运行 prog-cleanup-worktree {feature_id} 清理worktree，或修改收尾状态",
                "severity": "blocking"
            })

        # 3. 即将超时（提前1天警告）
        if is_nearing_timeout(feature):
            soft_warnings.append({
                "feature_id": feature_id,
                "reason": f"{integration}状态即将超时",
                "suggested_action": "检查状态并处理",
                "severity": "warning"
            })

    return hard_blocks, soft_warnings
```

### `/prog-next`扩展实现（分层响应）
```python
def prog_next_command():
    """扩展的/prog-next，分层响应收尾门禁"""
    # 1. 分层检查
    hard_blocks, soft_warnings = check_finish_gate_blocking()

    # 2. 如果有硬阻断，直接失败
    if hard_blocks:
        print("❌ 无法开始新功能，以下问题需要先解决:")
        for block in hard_blocks:
            print(f"  • {block['feature_id']}: {block['reason']}")
            print(f"    需要: {block['required_action']}")
        print("\n请先处理上述硬阻断问题，再运行 /prog-next")
        return

    # 3. 显示软告警（但不阻断）
    if soft_warnings:
        print("⚠️  注意: 以下问题建议处理，但不阻断操作:")
        for warning in soft_warnings:
            print(f"  • {warning['feature_id']}: {warning['reason']}")
            if 'suggested_action' in warning:
                print(f"    建议: {warning['suggested_action']}")
        print()

    # 4. 执行原有选择逻辑
    next_feature = select_next_feature()

    # 5. 开始新功能
    set_current_feature(next_feature["id"])
    print(f"✅ 开始功能: {next_feature['name']}")
```

### 硬规则执行（带修复白名单）
```python
def enforce_hard_rules(feature: Dict, action: str) -> bool:
    """强制执行硬规则，但为修复动作提供白名单"""
    lifecycle = feature.get("lifecycle_state")
    integration = feature.get("integration_status")

    # 规则1：verified+finish_pending禁止常规变更
    if lifecycle == "verified" and integration == "finish_pending":
        if action in FINISH_PENDING_WHITELISTED_ACTIONS:
            # 修复动作允许通过
            return True
        else:
            # 非修复动作被阻断
            raise BlockedError(
                f"功能 {feature['id']} 已验证但未收尾，不能执行 {action}。"
                f"请先设置收尾状态: prog-set-finish-state --feature-id {feature['id']}"
            )

    # 规则2：非法状态组合禁止常规变更，但允许修复动作
    if not is_valid_state_combo(lifecycle, integration):
        # 修复动作白名单：允许修复非法状态
        STATE_REPAIR_WHITELISTED_ACTIONS = {
            "fix-state",           # prog-fix-state
            "validate-feature",    # prog-validate-feature
            "add-update",          # 添加审计记录
            "set-lifecycle-state", # 设置生命周期状态（用于修复）
            "set-finish-state"     # 设置收尾状态（用于修复）
        }

        if action in STATE_REPAIR_WHITELISTED_ACTIONS:
            # 修复动作允许通过
            return True
        else:
            # 非修复动作被阻断
            raise BlockedError(
                f"功能 {feature['id']} 状态非法: {lifecycle}+{integration}。"
                f"请先修复状态: prog-fix-state --feature-id {feature['id']}"
            )

    # 规则3：设置收尾状态时校验目标状态组合合法性
    if action == "set-finish-state":
        new_status = get_requested_finish_status()

        # 3.1: 非finish_pending状态要求lifecycle在verified/archived中
        if new_status != "finish_pending" and lifecycle not in ["verified", "archived"]:
            raise BlockedError(
                f"只有verified/archived功能才能设置收尾状态 {new_status}，"
                f"当前状态: {lifecycle}"
            )

        # 3.2: 校验目标状态组合合法性（基于part2状态矩阵规则）
        if new_status == "pr_open" and lifecycle != "verified":
            raise BlockedError(
                f"pr_open收尾状态仅允许verified功能，当前状态: {lifecycle}"
            )

        if new_status == "kept_with_reason" and lifecycle not in ["verified", "archived"]:
            raise BlockedError(
                f"kept_with_reason收尾状态仅允许verified/archived功能，当前状态: {lifecycle}"
            )

        if new_status == "merged_and_cleaned" and lifecycle not in ["verified", "archived"]:
            raise BlockedError(
                f"merged_and_cleaned收尾状态仅允许verified/archived功能，当前状态: {lifecycle}"
            )

        # 3.3: 如果当前已是非法状态组合，允许通过（修复动作）

    return True
```

## 超时策略与二次确认机制（补全数据契约）

### 超时数据契约定义
```python
# 时间字段契约
TIME_FIELD_CONTRACT = {
    "completed_at": {
        "required": False,
        "default": None,
        "format": "iso8601",
        "timezone": "UTC"
    },
    "integration_created_at": {
        "required": False,
        "default": None,
        "format": "iso8601",
        "timezone": "UTC"
    },
    "last_cleanup_attempt": {
        "required": False,
        "default": None,
        "format": "iso8601",
        "timezone": "UTC"
    },
    "snooze_until": {  # 新增：免打扰截止时间
        "required": False,
        "default": None,
        "format": "iso8601",
        "timezone": "UTC"
    }
}

# 超时配置
TIMEOUT_CONFIG = {
    "finish_pending": {
        "days": 7,
        "action": "require_finish_decision",
        "severity": "high"
    },
    "cleanup_status_pending": {
        "days": 3,
        "action": "remind_cleanup",
        "severity": "medium"
    },
    "pr_open": {
        "days": 14,
        "action": "check_pr_status",
        "severity": "medium"
    },
    "kept_with_reason": {
        "days": 30,
        "action": "review_reason",
        "severity": "low"
    }
}
```

### 带数据契约的超时检测算法
```python
def check_finish_timeouts() -> List[Dict]:
    """检测超时未处理的收尾状态（带数据契约）"""
    timeouts = []
    now = datetime.now(timezone.utc)  # 固定使用UTC时区

    for feature in get_all_features():
        feature_id = feature["id"]
        integration = feature.get("integration_status")
        snooze_until = parse_iso8601_utc(feature.get("snooze_until"))

        # 检查是否在免打扰期
        if snooze_until and snooze_until > now:
            continue

        if integration not in TIMEOUT_CONFIG:
            continue

        config = TIMEOUT_CONFIG[integration]
        timeout_days = config["days"]

        # 获取参考时间（处理缺失字段）
        reference_time = get_reference_time_for_timeout(feature, integration)
        if not reference_time:
            continue

        elapsed_days = (now - reference_time).days

        if elapsed_days > timeout_days:
            timeouts.append({
                "feature_id": feature_id,
                "type": f"{integration}_timeout",
                "elapsed_days": elapsed_days,
                "timeout_days": timeout_days,
                "action": config["action"],
                "severity": config["severity"],
                "reference_time": reference_time.isoformat(),
                "snooze_until": snooze_until.isoformat() if snooze_until else None
            })

    return timeouts

def get_reference_time_for_timeout(feature: Dict, integration: str) -> Optional[datetime]:
    """根据数据契约获取参考时间（处理缺失字段）"""
    try:
        if integration == "finish_pending":
            # 使用completed_at，如果缺失则使用最后一次状态变更时间
            time_str = feature.get("completed_at")
            if not time_str:
                # 查找最后一次状态变更为verified的时间
                last_verified = find_last_update_time(feature["id"], "state_change", "verified")
                if last_verified:
                    return last_verified
                return None

        elif integration == "pr_open":
            # 使用integration_created_at或integration_status设置时间
            time_str = feature.get("integration_created_at")
            if not time_str:
                # 查找最后一次设置pr_open的时间
                last_pr_update = find_last_update_time(feature["id"], "set_finish_state", "pr_open")
                if last_pr_update:
                    return last_pr_update

        elif integration in ["merged_and_cleaned", "kept_with_reason"]:
            # 使用integration_status设置时间
            time_str = feature.get("integration_created_at")
            if not time_str:
                last_update = find_last_update_time(feature["id"], "set_finish_state", integration)
                if last_update:
                    return last_update

        elif integration is None:
            # 没有设置收尾状态，使用completed_at
            time_str = feature.get("completed_at")

        # 统一解析（UTC时区）
        if time_str:
            return parse_iso8601_utc(time_str)
        return None

    except Exception:
        # 解析失败，返回None（跳过这个feature）
        return None
```

### 二次确认机制（参数化，无input()）
```python
def require_reconfirmation(feature_id: str, timeout_info: Dict,
                          auto_snooze_days: int = 1) -> Dict:
    """参数化二次确认，返回决策结果"""
    feature = get_feature(feature_id)

    # 构造确认信息
    confirmation_info = {
        "feature_id": feature_id,
        "feature_name": feature.get("name", "未知"),
        "timeout_type": timeout_info["type"],
        "elapsed_days": timeout_info["elapsed_days"],
        "timeout_days": timeout_info["timeout_days"],
        "integration_status": feature.get("integration_status"),
        "cleanup_status": feature.get("cleanup_status"),
        "last_reference": timeout_info.get("reference_time"),
        "suggested_actions": get_suggested_actions(feature, timeout_info)
    }

    # 记录需要确认的审计
    add_update(feature_id, "timeout_requires_confirmation",
              f"超时需要确认: {timeout_info['type']} ({timeout_info['elapsed_days']}天)")

    # 返回决策信息（不阻塞）
    return {
        "requires_confirmation": True,
        "confirmation_info": confirmation_info,
        "available_options": [
            {"id": "resolve", "label": "立即处理", "command": f"prog-resolve-timeout {feature_id}"},
            {"id": "snooze", "label": f"暂不处理（{auto_snooze_days}天内不再提示）",
             "command": f"prog-snooze-timeout {feature_id} --days {auto_snooze_days}"},
            {"id": "ignore", "label": "标记为已查看",
             "command": f"prog-ignore-timeout {feature_id}"}
        ]
    }

def apply_confirmation_decision(feature_id: str, decision: str, **kwargs) -> bool:
    """应用确认决策"""
    if decision == "resolve":
        # 触发相应的处理逻辑
        return handle_timeout_resolution(feature_id)

    elif decision == "snooze":
        days = kwargs.get("days", 1)
        snooze_until = datetime.now(timezone.utc) + timedelta(days=days)
        set_snooze_until(feature_id, snooze_until)
        add_update(feature_id, "timeout_snoozed",
                  f"超时提醒暂停 {days} 天")
        return True

    elif decision == "ignore":
        # 只是标记为已查看，不改变snooze状态
        add_update(feature_id, "timeout_ignored",
                  "用户标记超时为已查看")
        return True

    return False
```

### 新增命令：超时管理
```bash
# 检查超时状态
prog-check-timeouts [--include-snoozed]

# 处理单个超时
prog-resolve-timeout <feature_id>

# 暂停提醒
prog-snooze-timeout <feature_id> [--days <n>]

# 标记为已查看
prog-ignore-timeout <feature_id>
```

## 集成点与现有代码兼容性

### 现有命令扩展点（修正说明）
| 现有命令 | 修改点 | 兼容性保证 | 改动类型 |
|----------|--------|------------|----------|
| `/prog-done` | 增加`detect_finish_state()`调用，支持二段式 | ✅ 原有验收逻辑不变，新增参数化接口 | 扩展 |
| `/prog-next` | 增加分层`check_finish_gate_blocking()` | ✅ 原有选择逻辑不变，仅新增前置检查 | 扩展 |
| `/prog`状态显示 | 显示`integration_status`和分层告警 | ✅ 新增字段，不影响原有显示 | 扩展 |
| `set-development-stage` | 状态映射时初始化收尾字段 | ✅ 新增字段默认值 | 扩展 |
| 所有mutating命令 | 增加`enforce_hard_rules()`检查 | ✅ 新增检查，为修复动作提供白名单 | 新增保护 |

### 向后兼容处理（迁移策略）
```python
def migrate_legacy_finish_state(feature: Dict) -> Dict:
    """迁移旧版本的功能完成状态到新收尾模型（增强版）"""
    # 旧版本：只有completed=true，没有收尾状态
    if feature.get("completed") and "integration_status" not in feature:
        # 尝试推断更准确的收尾状态
        git_root = get_git_root(get_project_root())
        feature_commits = get_feature_commits(feature["id"])

        if feature_commits and is_merged_into_main(feature_commits, git_root):
            # 已并入主线 → merged_and_cleaned
            feature["integration_status"] = "merged_and_cleaned"
            feature["cleanup_status"] = "done"
            feature["finish_reason"] = "从v2.0迁移，检测到已合并"
        else:
            # 未明确状态 → finish_pending（需要用户确认）
            feature["integration_status"] = "finish_pending"
            feature["cleanup_status"] = "pending"
            feature["finish_reason"] = "从v2.0迁移，需要确认收尾状态"

        # 设置迁移时间戳
        feature["integration_created_at"] = datetime.now(timezone.utc).isoformat()

        add_update(feature["id"], "finish_state_migrated_v2",
                  f"从v2.0迁移收尾状态: {feature['integration_status']}")

    # 确保所有时间字段符合契约
    for field in TIME_FIELD_CONTRACT:
        if field in feature and feature[field]:
            # 尝试标准化时间格式
            try:
                dt = parse_iso8601_utc(feature[field])
                feature[field] = dt.isoformat()
            except Exception:
                # 如果解析失败，清除非标准格式
                feature[field] = None

    return feature
```

### 新增命令清单（排障与修复）
```bash
# 收尾状态管理
prog-set-finish-state --feature-id <id> --status <status> [--reason "<text>"]
prog-check-finish-gates [--verbose]

# worktree清理
prog-cleanup-worktree <feature_id> [--force]

# 超时管理
prog-check-timeouts [--include-snoozed]
prog-resolve-timeout <feature_id>
prog-snooze-timeout <feature_id> [--days <n>]
prog-ignore-timeout <feature_id>

# 状态修复
prog-fix-state --feature-id <id> [--auto]
prog-validate-feature --feature-id <id>
```

## 可观测指标（阶段2）与监控

### 分层指标定义
```python
METRICS_DEFINITION = {
    # 硬阻断指标
    "hard_block_hit_rate": {
        "formula": "被硬阻断的/prog-next次数 / 总/prog-next调用",
        "target": "< 0.05",  # 硬阻断率应低于5%
        "collection": "每次/prog-next调用时记录"
    },

    # 软告警指标
    "soft_warning_rate": {
        "formula": "产生软告警的/prog-next次数 / 总/prog-next调用",
        "target": "< 0.20",  # 软告警率可接受20%
        "collection": "每次/prog-next调用时记录"
    },

    # 自动决策成功率
    "auto_finish_success_rate": {
        "formula": "自动确定收尾状态的次数 / 总/prog-done调用",
        "target": "> 0.70",  # 70%以上应能自动决策
        "collection": "每次/prog-done调用时记录"
    },

    # 二段式使用率
    "two_stage_usage_rate": {
        "formula": "需要二段式决策的次数 / 总/prog-done调用",
        "target": "< 0.30",  # 少于30%需要交互
        "collection": "每次/prog-done调用时记录"
    },

    # 超时处理时效性
    "timeout_resolution_rate": {
        "formula": "7天内处理的超时数 / 总超时数",
        "target": "> 0.80",  # 80%超时应在7天内处理
        "collection": "每日检查"
    }
}
```

### 监控仪表板示例（增强版）
```json
{
  "finish_gate_metrics": {
    "total_features": 15,
    "by_status": {
      "finish_pending": {"count": 2, "avg_age_days": 3.5},
      "merged_and_cleaned": {"count": 8, "cleanup_status_pending_count": 1},
      "pr_open": {"count": 3, "avg_age_days": 5.2},
      "kept_with_reason": {"count": 1, "reason_length": 25}
    },
    "blocking_stats": {
      "hard_blocks_today": 2,
      "soft_warnings_today": 4,
      "avg_resolution_time_hours": 6.3
    }
  },
  "timeout_alerts": {
    "active": [
      {"feature_id": "feat-012", "type": "finish_pending", "days": 8, "severity": "high"},
      {"feature_id": "feat-015", "type": "cleanup_status_pending", "days": 4, "severity": "medium"}
    ],
    "snoozed": [
      {"feature_id": "feat-008", "type": "pr_open", "snooze_until": "2025-03-15T10:00:00Z"}
    ],
    "resolved_today": 3
  },
  "worktree_cleanup": {
    "total_worktrees": 10,
    "clean": 7,
    "dirty": 2,
    "pending_cleanup": 1,
    "auto_clean_success_rate": 0.85
  }
}
```

### 每日自检任务（增强版）
```python
def daily_self_check(output_format: str = "text") -> Dict:
    """增强版每日自检，支持多种输出格式"""
    checks = {
        "pending_finish": check_finish_gate_blocking(),
        "timeouts": check_finish_timeouts(),
        "dirty_worktrees": find_dirty_worktrees(),
        "state_conflicts": find_state_conflicts(),
        "data_integrity": validate_data_integrity()
    }

    issues_found = any(len(v) > 0 for v in checks.values())

    if output_format == "json":
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "issues_found": issues_found,
            "checks": checks,
            "summary": generate_check_summary(checks)
        }
    else:
        # 文本输出
        print("=== Progress Tracker 每日自检 ===")
        print(f"时间: {datetime.now(timezone.utc).isoformat()}")

        for check_name, results in checks.items():
            if results:
                print(f"\n❌ {check_name.replace('_', ' ').title()}:")
                for result in results[:5]:  # 最多显示5条
                    print(f"  • {format_check_result(result)}")
                if len(results) > 5:
                    print(f"  ... 还有 {len(results) - 5} 条未显示")

        if not issues_found:
            print("\n✅ 所有状态正常")
        else:
            print("\n📊 汇总:")
            print(f"  待处理收尾: {len(checks['pending_finish'][0])} 硬阻断, {len(checks['pending_finish'][1])} 软告警")
            print(f"  超时警告: {len(checks['timeouts'])}")
            print(f"  脏worktree: {len(checks['dirty_worktrees'])}")
            print(f"  状态冲突: {len(checks['state_conflicts'])}")

        return checks
```

## P0修正总结

### 1. ✅ 自动判定 merged_and_cleaned 条件过宽
**修正**：改为基于git历史检查，使用`merge-base --is-ancestor`验证特性提交是否已并入主线

### 2. ✅ 不要在核心库里用 input() 交互
**修正**：改为参数化或二段式流程：`/prog-done`返回待决策信息，用`prog-set-finish-state`落盘

### 3. ✅ worktree 清理不能 shutil.rmtree()
**修正**：必须使用`git worktree remove + git worktree prune`，避免.git/worktrees元数据垃圾

### 4. ✅ /prog-next 阻断要分"硬阻断/软告警"
**修正**：
- **硬阻断**：finish_pending、无效kept_with_reason、不一致状态
- **软告警**：pr_open + cleanup=pending（正常PR流程）

### 5. ✅ 硬规则1会误伤"修复动作"
**修正**：为`set-finish-state`/`cleanup`/`set-lifecycle-state`（仅回退）等修复动作添加白名单

### 6. ✅ 超时与二次确认机制需补数据契约
**修正**：
- 定义`snooze_until`字段和完整时间字段契约
- 统一使用UTC时区解析
- 处理缺失时间字段的默认值逻辑
- 参数化二次确认（无阻塞式input）

### 集成点确认
与当前代码集成是可行的，但属于"新增主流程"而非小改。核心集成点：
1. `progress_manager.py` (line 2086) - `complete_feature`函数
2. `progress_manager.py` (line 2382) - `prog_next_command`相关逻辑
3. `progress_manager.py` (line 486) - 状态管理核心

**所有修正已在本版本中实现，等待批准进入实施阶段。**