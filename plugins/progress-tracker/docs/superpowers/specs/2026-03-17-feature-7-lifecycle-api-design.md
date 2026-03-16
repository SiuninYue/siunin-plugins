# Feature 7: 生命周期 API 与回退规则 - 设计文档

**日期**: 2026-03-17
**状态**: 设计中
**作者**: Claude
**相关功能**: REQ-007

## 1. 概述

为 progress-tracker 实现统一的生命周期 API 和回退规则，解决以下问题：
- 状态转换逻辑分散在多个函数中
- 缺少集中的状态转换验证
- 回退操作不完整（只重置部分字段）
- 缺少审计日志

## 2. 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    语义化业务入口层                            │
│  start_feature() | complete_feature() | archive_feature()  │
│              rollback_feature() | replan_feature()          │
│              reopen_feature()                                │
└────────────────────────┬────────────────────────────────────┘
                         │ 只做参数整理
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      状态机核心层                             │
│  validate_transition() | _execute_transition() | transition()│
│  - 状态转换规则验证                                          │
│  - 审计日志写入（原子性）                                     │
│  - 原子状态更新（文件锁 + 临时文件 + fsync）                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   数据持久化层                                │
│  progress.json | audit.log (JSONL, append-only)             │
│  - 同一把文件锁保护两文件                                      │
│  - 临时文件 + rename 原子写入                                  │
│  - fsync 确保持久化                                           │
└─────────────────────────────────────────────────────────────┘
```

## 3. 状态转换规则

### 3.1 生命周期状态

```python
LIFECYCLE_STATES = ("approved", "implementing", "verified", "archived")
```

### 3.2 允许的状态转换

```python
ALLOWED_TRANSITIONS = {
    "approved": ["implementing"],          # start_feature()
    "implementing": ["approved", "verified"],  # replan_feature(), complete_feature()
    "verified": ["implementing", "archived"],  # reopen_feature(), archive_feature()
    "archived": []                         # 终态，禁止逆向
}
```

### 3.3 状态图

```
         ┌─────────────────────────────────────────────────┐
         │                                                 │
         ▼                                                 │
    ┌─────────┐    start_feature()              ┌─────────┐
    │ approved│ ──────────────────────────────> │implement│
    │         │                                  │   ing   │
    └────┬────┘                                  └────┬────┘
         │                                            │
         │ replan_feature()                          │ complete_feature()
         │                                            │
         │         ┌──────────────────────────────────┘
         │         │
         │         ▼
         │    ┌─────────┐    reopen/fix           ┌─────────┐
         │    │implement│ <────────────────────── │ verified│
         │    │   ing   │                         └────┬────┘
         │    └─────────┘                              │
         │         │                                   │
         │         │ complete_feature()                │ archive_feature()
         │         │                                   │
         └─────────┘                                   │
                       │                                │
                       ▼                                ▼
                  ┌─────────┐                   ┌─────────┐
                  │ verified│ ──────────────────>│archived │
                  └─────────┘   archive_feature() └─────────┘
                                                          │
                                                  终态（禁止逆向）
```

## 4. 数据结构

### 4.1 ValidationError

```python
@dataclass
class ValidationError:
    """结构化验证错误"""
    code: str           # "FORBIDDEN_TRANSITION", "FEATURE_NOT_FOUND", "STATE_DIVERGED"
    message: str        # 人类可读错误描述
    suggestion: str = ""  # 建议的修复方法
```

### 4.2 ValidationResult

```python
@dataclass
class ValidationResult:
    """状态转换验证结果"""
    valid: bool
    blockers: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    current_state: str = ""
    requested_state: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 4.3 TransitionRecord

```python
@dataclass
class TransitionRecord:
    """状态转换记录"""
    feature_id: int
    op: str                    # "start", "complete", "archive", "rollback", "replan", "reopen"
    from_state: str
    to_state: str
    actor: str                 # "system", "user", or具体用户
    reason: str
    metadata: Dict[str, Any]
    tx_id: str                 # 事务ID，用于关联前后快照
    before_snapshot: Dict[str, Any]  # 转换前的完整 feature 状态
    after_snapshot: Dict[str, Any]   # 转换后的完整 feature 状态
    timestamp: str
    success: bool
```

### 4.4 TransitionOutcome

```python
@dataclass
class TransitionOutcome:
    """状态转换结果（统一返回类型）"""
    validation: ValidationResult
    record: Optional[TransitionRecord] = None
    changed: bool = False
```

### 4.5 审计日志格式 (audit.log)

```json
{
  "id": "AUDIT-001",
  "tx_id": "TX-20260317-001",
  "feature_id": 7,
  "op": "start",
  "from": "approved",
  "to": "implementing",
  "actor": "system",
  "reason": "开始 Feature 7 开发",
  "metadata": {},
  "before_snapshot": {
    "id": 7,
    "name": "7. 生命周期 API 与回退规则",
    "lifecycle_state": "approved",
    "development_stage": "planning",
    "completed": false
  },
  "after_snapshot": {
    "id": 7,
    "name": "7. 生命周期 API 与回退规则",
    "lifecycle_state": "implementing",
    "development_stage": "developing",
    "completed": false,
    "started_at": "2026-03-17T02:00:00Z"
  },
  "timestamp": "2026-03-17T02:00:00Z",
  "success": true
}
```

## 5. 核心接口

### 5.1 状态机核心层

```python
def validate_transition(
    feature_id: int,
    target_state: str,
    ctx: Dict[str, Any]
) -> ValidationResult:
    """
    验证状态转换是否合法

    检查项：
    1. feature 是否存在
    2. 目标状态是否有效（在 LIFECYCLE_STATES 中）
    3. 转换是否在 ALLOWED_TRANSITIONS 中
    4. 当前状态与审计记录是否一致（rollback 前检查）

    返回：结构化的 ValidationResult
    """

def _execute_transition(
    feature_id: int,
    target_state: str,
    ctx: Dict[str, Any],
    validation: ValidationResult
) -> TransitionRecord:
    """
    执行状态转换（私有，原子操作）

    步骤：
    1. 获取文件锁（保护 progress.json + audit.log）
    2. 读取当前状态并生成 before_snapshot
    3. 写入审计日志到临时文件
    4. 更新 progress.json 到临时文件
    5. 生成 after_snapshot
    6. fsync 审计日志临时文件，rename
    7. fsync progress.json 临时文件，rename
    8. 释放文件锁

    返回：TransitionRecord（含完整快照）
    """

def transition(
    feature_id: int,
    target_state: str,
    ctx: Dict[str, Any],
    dry_run: bool = False
) -> TransitionOutcome:
    """
    组合验证和执行

    流程：
    1. 调用 validate_transition()
    2. 如果 dry_run 或验证失败，返回 TransitionOutcome(validation=..., changed=False)
    3. 否则调用 _execute_transition()，返回完整 TransitionOutcome

    返回：TransitionOutcome（统一返回类型）
    """
```

### 5.2 语义化业务入口

```python
def start_feature(feature_id: int, reason: str = "") -> TransitionOutcome:
    """开始功能开发：approved → implementing"""
    return transition(
        feature_id, "implementing",
        {"op": "start", "actor": "system", "reason": reason or "开始功能开发"}
    )

def complete_feature(
    feature_id: int,
    commit_hash: str = "",
    reason: str = ""
) -> TransitionOutcome:
    """完成功能：implementing → verified"""
    ctx = {
        "op": "complete",
        "actor": "system",
        "reason": reason or "功能完成"
    }
    if commit_hash:
        ctx["commit_hash"] = commit_hash
    return transition(feature_id, "verified", ctx)

def archive_feature(
    feature_id: int,
    reason: str = ""
) -> TransitionOutcome:
    """归档功能：verified → archived"""
    return transition(
        feature_id, "archived",
        {"op": "archive", "actor": "system", "reason": reason or "功能归档"}
    )

def replan_feature(feature_id: int, reason: str = "") -> TransitionOutcome:
    """重新规划：implementing → approved"""
    return transition(
        feature_id, "approved",
        {"op": "replan", "actor": "system", "reason": reason or "重新规划"}
    )

def reopen_feature(feature_id: int, reason: str = "") -> TransitionOutcome:
    """重开修复：verified → implementing"""
    return transition(
        feature_id, "implementing",
        {"op": "reopen", "actor": "system", "reason": reason or "重开修复"}
    )

def rollback_feature(feature_id: int, reason: str = "") -> TransitionOutcome:
    """
    基于审计记录回退到前一状态

    步骤：
    1. 读取 audit.log，找到该 feature 最近的成功转换记录
    2. 校验一致性：feature.current_state == last_record.to_state
    3. 如果不一致，返回 STATE_DIVERGED 错误
    4. 恢复到 before_snapshot 的状态（lifecycle_state, development_stage 等）
    5. 清理派生字段：completed, completed_at, commit_hash, archive_info
    6. 写入新的审计记录（op=rollback）

    边界情况：
    - archived 状态返回错误（FORBIDDEN_TRANSITION）
    - approved 状态返回警告（已是初始状态）
    - 找不到审计记录时返回警告（NO_AUDIT_RECORD）

    返回：TransitionOutcome
    """
```

## 6. 实现约束

### 6.1 原子性保证

```python
# 同一把文件锁保护 progress.json + audit.log
LOCK_FILE = "progress.lock"

# 临时文件 + rename 原子写入
TEMP_SUFFIX = ".tmp"

def atomic_write(filepath: str, content: str):
    """原子写入：临时文件 + fsync + rename"""
    temp_path = filepath + TEMP_SUFFIX
    with open(temp_path, 'w') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.rename(temp_path, filepath)
```

### 6.2 回退一致性校验

```python
def _verify_state_consistency(feature: Dict, audit_record: TransitionRecord) -> bool:
    """
    回退前校验状态一致性

    返回 False 时触发 STATE_DIVERGED 错误
    """
    return feature.get("lifecycle_state") == audit_record.to_state
```

### 6.3 派生字段同步

```python
def _sync_derived_fields(feature: Dict, lifecycle_state: str):
    """
    根据 lifecycle_state 同步派生字段
    """
    state_mapping = {
        "approved": {"development_stage": "planning", "completed": False},
        "implementing": {"development_stage": "developing", "completed": False},
        "verified": {"development_stage": "completed", "completed": True},
        "archived": {"development_stage": "completed", "completed": True},
    }
    if lifecycle_state in state_mapping:
        for key, value in state_mapping[lifecycle_state].items():
            feature[key] = value
```

## 7. 迁移策略

### 7.1 bootstrap_audit()

为现有历史数据生成基线审计记录：

```python
def bootstrap_audit() -> Dict[str, Any]:
    """
    为现有 feature 生成基线审计记录

    逻辑：
    1. 读取 progress.json 中所有 features
    2. 对每个 feature，根据当前状态生成一条 "BOOTSTRAP" 记录
    3. before_snapshot 为空（或派生默认值），after_snapshot 为当前状态
    4. 写入 audit.log

    返回：{
        "total_features": N,
        "bootstrap_records": M,
        "skipped": []  # 已有审计记录的 features
    }
    """
```

### 7.2 一性性迁移命令

```bash
# CLI 入口
plugins/progress-tracker/prog bootstrap-audit --project-root plugins/progress-tracker
```

## 8. 测试策略

### 8.1 单元测试

```python
# test_lifecycle_state_machine.py
class TestValidateTransition:
    def test_allowed_transition_succeeds()
    def test_forbidden_transition_fails_with_suggestion()
    def test_archived_is_terminal_state()
    def test_state_diverged_error()

class TestExecuteTransition:
    def test_writes_audit_log_with_snapshots()
    def test_atomic_write_uses_temp_file_and_rename()
    def test_file_lock_protects_both_files()

class TestRollbackFeature:
    def test_restores_full_state_from_snapshot()
    def test_clears_derived_fields()
    def test_verifies_state_consistency_before_rollback()
    def test_returns_error_for_archived_state()
    def test_returns_warning_for_approved_state()
```

### 8.2 集成测试

```python
# test_lifecycle_integration.py
class TestEndToEndLifecycle:
    def test_full_lifecycle_approved_to_archived()
    def test_replan_flow_implementing_to_approved()
    def test_reopen_flow_verified_to_implementing()
    def test_rollback_after_complete()
    def test_bootstrap_audit_generates_baseline_records()
```

## 9. DoD 验证

| DoD 要求 | 实现验证 |
|---------|---------|
| 合法流转成功且审计完整 | 测试验证 execute_transition() 写入完整 audit.log |
| 非法流转被拒绝且无副作用 | 测试验证 validate_transition() 阻断非法转换 |
| 回退会重置验收结果 | 测试验证 rollback_feature() 恢复完整字段 |

## 10. 实现计划拆分

建议按以下顺序实现：

1. **PR 1**: 状态机核心 + 审计写入
   - `validate_transition()`
   - `_execute_transition()`
   - `transition()`
   - `TransitionOutcome`, `ValidationResult`, `TransitionRecord`
   - 审计日志写入（原子性）

2. **PR 2**: 语义化业务入口
   - `start_feature()`
   - `complete_feature()`
   - `archive_feature()`
   - `replan_feature()`
   - `reopen_feature()`
   - CLI 集成

3. **PR 3**: rollback 精确恢复 + 迁移
   - `rollback_feature()`
   - 一致性校验
   - `bootstrap_audit()`
   - 完整测试覆盖

## 11. 风险与注意事项

1. **并发安全**：确保文件锁正确保护两个文件
2. **性能**：audit.log 可能增长很快，考虑后续归档策略
3. **迁移**：bootstrap_audit() 需要处理大量现有 features
4. **兼容性**：确保与现有 `set_development_stage()`, `complete_feature()` 函数兼容
