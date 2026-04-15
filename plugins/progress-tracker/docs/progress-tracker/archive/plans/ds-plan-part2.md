# PROG全量规范化计划 - 第二部分：数据模型、迁移安全与事务管理（有条件批准版本）

## 批准条件（P0必须实现）

1. **合法状态组合矩阵**：定义lifecycle_state与integration_status的合法组合
2. **持久化fsync链路**：fsync(tmp) -> os.replace -> fsync(parent_dir)完整链
3. **审计与状态同事务**：add_update必须在同一事务内，共享transaction_id/correlation_id
4. **ID唯一性与时间戳校验**：feature.id、scenario.id唯一约束，时间格式ISO 8601
5. **PROG_DISABLE_V2的读写不破坏测试**：降级模式下读2.1不丢字段，写回不破坏数据结构

## Schema 2.1数据模型详细设计

### progress.json顶层结构（兼容性优先）
```json
{
  "schema_version": "2.1",
  "validation_policy": {
    "strictness": "warn_only",  // "blocking"或"warn_only"
    "blocking_checks": ["lifecycle_state", "requirement_ids"],
    "warning_checks": ["change_id", "acceptance_scenarios"]
  },
  "features": [],
  "retrospectives": [],  // 新字段：复盘分离
  "updates": [],        // 沿用并扩展
  // 所有现有字段保持不变
  "project_name": "...",
  "project_goal": "...",
  "current_feature": "...",
  "development_stage": "...",
  "completed": false,
  "bugs": [],
  "archive_info": null
}
```

### feature对象（强制与可选字段）
```json
{
  "id": "feat-123",
  "name": "用户认证",

  // 新增强制字段（阶段3启用）
  "lifecycle_state": "proposed",  // "proposed"|"approved"|"implementing"|"verified"|"archived"
  "requirement_ids": ["REQ-AUTH-001", "REQ-AUTH-002"],
  "change_spec": {
    "change_id": "CHANGE-20250311-001",
    "why": "现有认证逻辑不支持多因素验证",
    "in_scope": ["MFA设置页面", "登录流程增强"],
    "out_of_scope": ["密码重置", "第三方OAuth集成"],
    "risks": ["向后兼容性", "会话管理复杂度"]
  },

  // 验收测试规范（P0：ID唯一约束）
  "acceptance_scenarios": [
    {
      "id": "scen-001",  // 唯一约束：同一feature内scenario.id不能重复
      "given": "用户已注册账户",
      "when": "用户启用MFA",
      "then": "下次登录需验证MFA"
    }
  ],
  "acceptance_results": [
    {
      "scenario_id": "scen-001",
      "status": "untested",  // "untested"|"passed"|"failed"
      "evidence": "手动测试截图",
      "updated_at": "2025-03-11T10:00:00Z"  // ISO 8601格式
    }
  ],

  // 收尾状态（阶段2新增）
  "integration_status": "finish_pending",  // "finish_pending"|"merged_and_cleaned"|"pr_open"|"kept_with_reason"
  "integration_ref": "https://github.com/.../pull/123",
  "cleanup_status": "pending",  // "pending"|"done"|"skipped"
  "finish_reason": "等待代码审查",
  "archive_pending": {
    "attempts": 0,
    "last_error": null,
    "next_retry_at": null  // ISO 8601格式
  },

  // 向后兼容镜像字段（自动同步）
  "development_stage": "planning",  // 由lifecycle_state映射
  "completed": false,               // 由lifecycle_state映射

  // 其他现有字段保持不变
  "test_steps": [],
  "started_at": "...",              // ISO 8601格式
  "completed_at": null,             // ISO 8601格式
  "ai_metrics": {},
  "verification": {}
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
| proposed | merged_and_cleaned | ❌ 非法 | 提案阶段不能已完成合并 |
| implementing | merged_and_cleaned | ❌ 非法 | 实施中不能已完成合并 |
| archived | finish_pending | ❌ 非法 | 已归档不能等待收尾 |

**规则**：
1. `finish_pending`仅允许`proposed`、`approved`、`implementing`、`verified`
2. `merged_and_cleaned`仅允许`verified`、`archived`
3. `pr_open`仅允许`verified`
4. `kept_with_reason`仅允许`verified`、`archived`
5. `archived`不能与`finish_pending`共存

### 状态映射规则（单向同步）
```python
LIFECYCLE_TO_LEGACY_MAPPING = {
    "proposed": ("planning", False),
    "approved": ("planning", False),
    "implementing": ("developing", False),
    "verified": ("completed", True),
    "archived": ("completed", True)
}

# 优先级规则：lifecycle_state永远为真源，旧字段只镜像，不反向覆盖新字段
```

## 向后兼容与双写机制

### 兼容性保证
1. **读取路径**：优先读取`lifecycle_state`，如缺失则从`development_stage`+`completed`反推
2. **写入路径**：设置`lifecycle_state`时自动同步写入镜像字段
3. **冲突检测**：`reconcile_legacy_state()`检测并修复不一致状态

### 双写优先级规则
```python
# 规则1：lifecycle_state永远为真源
# 规则2：development_stage/completed仅为镜像，不参与决策
# 规则3：状态冲突时以lifecycle_state为准修复镜像字段
# 规则4：PROG_DISABLE_V2=1时，读2.1不丢字段，写回不降级破坏
```

### 降级开关（P0测试要求）
```python
# 环境变量控制
DISABLE_V2 = os.environ.get("PROG_DISABLE_V2", "0") == "1"

if DISABLE_V2:
    # 回退到v2.0逻辑，但必须保证：
    # 1. 读取2.1字段不丢失（转换为兼容表示）
    # 2. 写回操作不破坏现有2.1数据结构
    # 3. 状态变更仍通过add_update记录审计
    log_warning("Schema 2.1功能已禁用，使用v2.0兼容模式")

    # P0测试：验证降级模式下数据完整性
    # - 读取lifecycle_state并正确映射到development_stage
    # - 读取integration_status并正确提示用户
    # - 写入时保留所有2.1字段（即使不处理）
```

## 迁移安全机制（P0：持久化fsync链路）

### 写路径唯一化约束
**所有状态变更必须走transaction_manager + add_update**，禁止旁路写JSON。

### TransactionManager实现（P0：fsync链路）
```python
class TransactionManager:
    def __init__(self, progress_path: Path):
        self.progress_path = progress_path
        self.lock_path = progress_path.with_suffix(".lock")

    def atomic_update(self, update_func: Callable[[Dict], Dict], reason: str):
        """独占锁 + 原子写 + fsync链路 + 备份回滚"""
        with filelock.FileLock(self.lock_path, timeout=10):
            # 1. 创建预写日志（P0：审计与状态同事务）
            pre_update = self._read_progress()
            transaction_id = self._generate_transaction_id()
            self._write_precommit_log(pre_update, reason, transaction_id)

            # 2. 执行用户更新
            new_state = update_func(pre_update)

            # 3. 验证后迁移
            new_state = self._apply_schema_defaults(new_state)
            self._validate_post_migration(new_state)

            # 4. 原子写入（P0：fsync完整链路）
            temp_path = self.progress_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(new_state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # 第一步：fsync临时文件

            os.replace(temp_path, self.progress_path)

            # 第二步：fsync父目录（确保元数据持久化）
            parent_dir = os.path.dirname(self.progress_path)
            dir_fd = os.open(parent_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

            # 5. 同步更新summary（P0：同事务或版本号+重试）
            self._update_progress_summary(new_state, transaction_id)

            # 6. 写入审计记录（P0：同一事务内）
            self._add_update_record(new_state, reason, transaction_id)

    def _add_update_record(self, state: Dict, reason: str, transaction_id: str):
        """P0：审计与状态同事务，共享transaction_id"""
        if "current_feature" not in state:
            return

        update_entry = {
            "feature_id": state["current_feature"],
            "type": "state_change",
            "description": reason,
            "timestamp": datetime.now().isoformat(),
            "transaction_id": transaction_id,
            "correlation_id": transaction_id,  # 用于跨命令追溯
            "refs": ["transaction:" + transaction_id]
        }

        # 确保updates数组存在
        if "updates" not in state:
            state["updates"] = []
        state["updates"].append(update_entry)

    def _update_progress_summary(self, state: Dict, transaction_id: str):
        """P0：summary与主状态一致性保证"""
        summary_path = self.progress_path.with_name("progress_summary.json")
        summary = self._compute_summary(state)
        summary["_source_checksum"] = self._compute_state_checksum(state)
        summary["_last_transaction_id"] = transaction_id
        summary["_updated_at"] = datetime.now().isoformat()

        # 版本号+重试机制防止漂移
        retry_count = 0
        while retry_count < 3:
            try:
                with open(summary_path, "w") as f:
                    json.dump(summary, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                break
            except IOError:
                retry_count += 1
                time.sleep(0.1 * retry_count)
```

### 备份与回滚策略
1. **预写日志**：每次变更前创建`progress.json.pre-<timestamp>-<transaction_id>.log`
2. **备份快照**：每日首次变更创建完整备份`progress.json.backup-YYYYMMDD`
3. **回滚机制**：自动回退到最近可用precommit/backup
   ```bash
   # 手动回滚到指定时间点
   prog-rollback --to 2025-03-11T10:00:00
   ```

### 脑裂修复与状态一致

#### reconcile_legacy_state算法（P0：ID唯一性检查）
```python
def reconcile_legacy_state(feature: Dict) -> Dict:
    """修复lifecycle_state与镜像字段的不一致，检查ID唯一性"""

    # P0：检查feature.id唯一性（在features数组层面）
    if not feature.get("id") or not isinstance(feature["id"], str):
        raise ValidationError(f"Invalid feature.id: {feature.get('id')}")

    if not feature.get("name") or not isinstance(feature["name"], str):
        raise ValidationError(f"Invalid feature.name: {feature.get('name')}")

    # P0：检查acceptance_scenarios.id唯一性
    if "acceptance_scenarios" in feature:
        scenario_ids = set()
        for scenario in feature["acceptance_scenarios"]:
            if "id" not in scenario:
                raise ValidationError("acceptance_scenario missing id")
            if scenario["id"] in scenario_ids:
                raise ValidationError(f"Duplicate scenario.id: {scenario['id']}")
            scenario_ids.add(scenario["id"])

    # P0：检查时间戳格式
    for time_field in ["started_at", "completed_at"]:
        if time_field in feature and feature[time_field]:
            if not self._validate_iso8601(feature[time_field]):
                raise ValidationError(f"Invalid {time_field} format: {feature[time_field]}")

    # 状态一致性修复（原有逻辑）
    has_lifecycle = "lifecycle_state" in feature
    has_legacy = "development_stage" in feature and "completed" in feature

    if not has_lifecycle and not has_legacy:
        feature["lifecycle_state"] = "proposed"
        feature["development_stage"], feature["completed"] = LIFECYCLE_TO_LEGACY_MAPPING["proposed"]

    elif has_lifecycle and has_legacy:
        expected_stage, expected_completed = LIFECYCLE_TO_LEGACY_MAPPING[feature["lifecycle_state"]]
        if (feature["development_stage"] != expected_stage or
            feature["completed"] != expected_completed):
            feature["development_stage"] = expected_stage
            feature["completed"] = expected_completed
            add_update(feature["id"], "reconcile",
                      f"修复镜像字段不一致: {feature['lifecycle_state']}")

    elif has_lifecycle and not has_legacy:
        stage, completed = LIFECYCLE_TO_LEGACY_MAPPING[feature["lifecycle_state"]]
        feature["development_stage"] = stage
        feature["completed"] = completed

    elif not has_lifecycle and has_legacy:
        feature["lifecycle_state"] = infer_lifecycle_from_legacy(
            feature["development_stage"], feature["completed"]
        )

    return feature
```

## 坏数据迁移策略（增强版）

| 故障类型 | 检测方法 | 修复策略 | 审计记录 |
|----------|----------|----------|----------|
| **JSON解析失败** | `json.JSONDecodeError` | **自动回退到最近可用precommit/backup**，只读模式提示恢复 | `json_decode_failed_with_fallback` |
| **缺失schema_version** | 字段不存在 | 回填`"2.0"`，执行迁移 | `schema_version_added` |
| **features[]非数组** | `type(features) != list` | 尝试转换为数组，失败则阻断 | `features_type_fixed` |
| **重复feature.id** | ID重复检测 | 为重复ID添加后缀`-dup<index>`，告警用户 | `duplicate_feature_id_fixed` |
| **缺失feature.id/name** | 字段缺失检查 | 生成临时ID/名称，要求用户修复 | `missing_id_name_generated` |
| **scenario.id重复** | ID重复检测 | 为重复ID添加后缀`-dup<index>` | `duplicate_scenario_id_fixed` |
| **非法时间戳** | ISO 8601格式检查 | 尝试转换，失败则设为null并告警 | `invalid_timestamp_fixed` |
| **超大文件/截断** | 文件大小异常+解析失败 | 使用备份恢复，记录文件大小 | `truncated_file_recovered` |
| **状态冲突** | 镜像字段与lifecycle_state不一致 | 以lifecycle_state为准修复 | `state_reconciled` |
| **未知lifecycle_state** | 值不在允许集合内 | 回退到`"proposed"` | `invalid_state_reset` |

### JSON解析失败自动回退算法
```python
def safe_read_progress(progress_path: Path) -> Dict:
    """安全读取progress.json，自动回退到备份"""
    try:
        with open(progress_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        # 尝试最近precommit日志
        precommit = find_latest_precommit(progress_path)
        if precommit:
            logging.warning(f"主文件损坏，使用precommit恢复: {precommit}")
            with open(precommit, "r") as f:
                return json.load(f)

        # 尝试最近备份
        backup = find_latest_backup(progress_path)
        if backup:
            logging.warning(f"使用备份恢复: {backup}")
            with open(backup, "r") as f:
                return json.load(f)

        # 无可用备份，进入只读修复模式
        logging.error(f"无可用备份，文件可能已损坏: {e}")
        raise RecoveryError("无法恢复progress.json，请手动修复")
```

## PROG_DISABLE_V2读写不破坏测试（P0）

### 测试场景
1. **读2.1字段不丢失测试**
   - 创建完整的2.1数据结构
   - 设置`PROG_DISABLE_V2=1`
   - 验证所有2.1字段在读取时正确映射到兼容表示

2. **写回不破坏测试**
   - 在降级模式下执行状态变更
   - 验证写回后2.1字段保持不变
   - 验证镜像字段正确更新

3. **双向切换测试**
   - 2.1 → 降级模式 → 2.1
   - 验证数据往返一致性

### 测试断言
```python
def test_disable_v2_read_preservation():
    """P0：降级模式下读2.1不丢字段"""
    # 设置完整2.1数据
    setup_v21_data()

    # 启用降级模式
    os.environ["PROG_DISABLE_V2"] = "1"

    # 读取并验证
    state = read_progress()
    assert "lifecycle_state" in state["features"][0]  # 字段存在
    assert state["features"][0]["development_stage"] == "planning"  # 正确映射

def test_disable_v2_write_no_corruption():
    """P0：降级模式下写回不破坏"""
    # 初始2.1数据
    setup_v21_data()
    os.environ["PROG_DISABLE_V2"] = "1"

    # 执行写操作
    update_feature_status("feat-001", "developing")

    # 验证2.1字段完整
    state = read_progress()
    assert state["features"][0]["lifecycle_state"] == "implementing"
    assert state["schema_version"] == "2.1"  # 不被降级
```

## 可观测指标（阶段1）

1. **迁移失败率** = `迁移失败次数 / 总迁移尝试`
2. **自动修复成功率** = `自动修复成功次数 / 需要修复的总数`
3. **回滚成功率** = `成功回滚次数 / 回滚尝试次数`
4. **并发冲突解决率** = `锁超时解决次数 / 锁等待超时总数`
5. **ID冲突检测率** = `检测到的ID冲突数 / 总检查次数`
6. **时间戳校验通过率** = `有效时间戳数 / 总时间戳数`

## /prog-next阻断规则

**硬规则**：`/prog-next`前必须通过finish_gate，不允许任何bypass。

```python
def check_finish_gate_blocking(feature_id: str) -> bool:
    """检查单个feature是否因收尾未完成而被阻断（简化版，详细版本见part3-v2）

    硬阻断条件（与part3-v2一致）：
    1. verified + finish_pending
    2. kept_with_reason + 原因不充分（<10字符）
    3. 状态不一致（非法组合）
    4. merged_and_cleaned + cleanup=pending（非法组合）

    注意：pr_open + cleanup=pending 是软告警，不阻断（正常PR流程）
    """
    feature = get_feature(feature_id)
    lifecycle = feature.get("lifecycle_state")
    integration = feature.get("integration_status")
    cleanup = feature.get("cleanup_status")
    finish_reason = feature.get("finish_reason", "")

    # 硬阻断条件
    if lifecycle == "verified" and integration == "finish_pending":
        return True  # verified但未收尾

    if integration == "kept_with_reason" and len(finish_reason) < 10:
        return True  # 保留但原因不充分

    if not is_valid_state_combo(lifecycle, integration):
        return True  # 状态不一致

    if integration == "merged_and_cleaned" and cleanup == "pending":
        return True  # 已合并但worktree未清理（非法组合）

    # 旧逻辑兼容（但优先使用新逻辑）
    if feature.get("completed") and not feature.get("integration_status"):
        # 已标记完成但未设置收尾状态，触发自动修复
        auto_fix_finish_state(feature_id)
        return True  # 修复期间阻断

    return False  # 不被阻断（pr_open + pending等软告警情况允许通过）
```

## 故障演练测试（P0必须覆盖）

1. **JSON损坏恢复**：模拟文件损坏、编码错误、截断
2. **并发写冲突**：多进程同时写progress.json
3. **半迁移中断**：迁移过程中断（kill -9）
4. **磁盘空间不足**：写过程中空间耗尽
5. **权限问题**：只读文件、无写权限
6. **重复ID处理**：创建重复feature.id、scenario.id
7. **非法状态组合**：测试非法lifecycle_state+integration_status组合
8. **降级模式往返**：2.1↔降级模式多次切换
9. **审计断链**：状态变更成功但审计记录失败
10. **summary漂移**：主状态与summary不一致场景