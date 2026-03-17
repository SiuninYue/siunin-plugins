# Feature 7: 生命周期 API 与回退规则 - Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 progress-tracker 实现统一的生命周期 API 和回退规则，包括状态机核心、审计日志、精确回退和迁移支持。

**Architecture:** 三层架构 - 语义化业务入口层调用状态机核心层，状态机通过原子性操作同时更新 progress.json 和 audit.log。

**Tech Stack:** Python 3.12+, dataclasses, JSONL 审计日志, 文件锁 + 临时文件原子写入

---

## 文件结构

**新建文件:**
- `hooks/scripts/lifecycle_state_machine.py` - 生命周期状态机核心模块
- `hooks/scripts/audit_log.py` - 审计日志读写模块
- `tests/test_lifecycle_state_machine.py` - 状态机单元测试
- `tests/test_audit_log.py` - 审计日志测试
- `tests/test_lifecycle_integration.py` - 集成测试

**修改文件:**
- `hooks/scripts/progress_manager.py` - 集成新的生命周期 API
- `tests/test_feature_contract_readiness.py` - 添加生命周期相关测试

---

## Chunk 1: 数据结构与审计日志基础

### Task 1: 创建数据结构定义

**Files:**
- Create: `hooks/scripts/lifecycle_state_machine.py`

- [ ] **Step 1: 创建 ValidationError 数据类**

```python
# hooks/scripts/lifecycle_state_machine.py
"""生命周期状态机核心模块

提供统一的状态转换验证、执行和审计功能。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class ValidationError:
    """结构化验证错误"""
    code: str  # "FORBIDDEN_TRANSITION", "FEATURE_NOT_FOUND", "STATE_DIVERGED"
    message: str  # 人类可读错误描述
    suggestion: str = ""  # 建议的修复方法
    context: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 2: 创建 ValidationResult 数据类**

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

- [ ] **Step 3: 创建 TransitionRecord 数据类**

```python
@dataclass
class TransitionRecord:
    """状态转换记录"""
    feature_id: int
    op: str  # "start", "complete", "archive", "rollback", "replan", "reopen"
    from_state: str
    to_state: str
    actor: str  # "system", "user"
    reason: str
    metadata: Dict[str, Any]
    tx_id: str  # 事务ID
    before_snapshot: Dict[str, Any]
    after_snapshot: Dict[str, Any]
    timestamp: str
    success: bool
```

- [ ] **Step 4: 创建 TransitionOutcome 数据类**

```python
@dataclass
class TransitionOutcome:
    """状态转换结果（统一返回类型）"""
    validation: ValidationResult
    record: Optional[TransitionRecord] = None
    changed: bool = False
```

- [ ] **Step 5: 定义常量**

```python
# 生命周期状态常量
LIFECYCLE_STATES = ("approved", "implementing", "verified", "archived")

# 允许的状态转换规则
ALLOWED_TRANSITIONS = {
    "approved": ["implementing"],
    "implementing": ["approved", "verified"],
    "verified": ["implementing", "archived"],
    "archived": [],  # 终态
}

# 操作名称映射
OPERATION_NAMES = {
    "start": "开始功能开发",
    "complete": "功能完成",
    "archive": "功能归档",
    "replan": "重新规划",
    "reopen": "重开修复",
    "rollback": "回退操作",
    "bootstrap": "基线生成",
}
```

- [ ] **Step 6: 运行基础语法检查**

Run: `cd plugins/progress-tracker && python3 -m py_compile hooks/scripts/lifecycle_state_machine.py`
Expected: 无语法错误

- [ ] **Step 7: 提交数据结构定义**

```bash
git add hooks/scripts/lifecycle_state_machine.py
git commit -m "feat(lifecycle): add data structures for state machine

- Add ValidationError, ValidationResult, TransitionRecord, TransitionOutcome
- Define LIFECYCLE_STATES and ALLOWED_TRANSITIONS constants"
```

---

### Task 2: 创建审计日志模块

**Files:**
- Create: `hooks/scripts/audit_log.py`

- [ ] **Step 1: 创建审计日志基础结构**

```python
# hooks/scripts/audit_log.py
"""审计日志模块

提供 append-only 的 JSONL 审计日志功能。
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


AUDIT_LOG_FILENAME = "audit.log"


def get_audit_log_path(project_root: Optional[str] = None) -> Path:
    """获取审计日志文件路径"""
    if project_root:
        base = Path(project_root)
    else:
        base = Path(__file__).parent.parent.parent / "docs" / "progress-tracker" / "state"
    return base / AUDIT_LOG_FILENAME


def generate_audit_id() -> str:
    """生成审计记录 ID"""
    # 从审计日志中读取最大 ID 并递增
    path = get_audit_log_path()
    if not path.exists():
        return "AUDIT-001"

    max_num = 0
    try:
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        audit_id = record.get("id", "")
                        if audit_id.startswith("AUDIT-"):
                            num = int(audit_id.split("-")[1])
                            max_num = max(max_num, num)
                    except (json.JSONDecodeError, ValueError, IndexError):
                        continue
    except (IOError, OSError):
        pass

    return f"AUDIT-{max_num + 1:03d}"


def generate_tx_id() -> str:
    """生成事务 ID"""
    return f"TX-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
```

- [ ] **Step 2: 实现追加写入函数**

```python
def append_audit_record(record: Dict[str, Any], project_root: Optional[str] = None) -> bool:
    """
    追加审计记录到日志文件（原子操作）

    Args:
        record: 审计记录字典
        project_root: 项目根路径

    Returns:
        bool: 是否成功
    """
    path = get_audit_log_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 确保记录有必需字段
        if "id" not in record:
            record["id"] = generate_audit_id()
        if "timestamp" not in record:
            record["timestamp"] = datetime.now().isoformat() + "Z"

        # 追加写入（使用临时文件 + rename 保证原子性）
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, 'a') as f:
            json.dump(record, f, ensure_ascii=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())

        # 追加到原文件
        with open(path, 'a') as f:
            f.write(open(temp_path).read())
            f.flush()
            os.fsync(f.fileno())

        temp_path.unlink()
        return True
    except (IOError, OSError, json.JSONEncodeError) as e:
        # 清理临时文件
        if temp_path.exists():
            temp_path.unlink()
        return False
```

- [ ] **Step 3: 实现读取函数**

```python
def read_audit_log(
    feature_id: Optional[int] = None,
    project_root: Optional[str] = None,
    limit: int = 0
) -> List[Dict[str, Any]]:
    """
    读取审计日志

    Args:
        feature_id: 过滤特定 feature 的记录
        project_root: 项目根路径
        limit: 限制返回数量（0 = 全部）

    Returns:
        List[Dict]: 审计记录列表
    """
    path = get_audit_log_path(project_root)
    if not path.exists():
        return []

    records = []
    try:
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if feature_id is None or record.get("feature_id") == feature_id:
                            records.append(record)
                    except json.JSONDecodeError:
                        continue
    except (IOError, OSError):
        return []

    # 按时间戳排序（新的在前）
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

    if limit > 0:
        records = records[:limit]

    return records
```

- [ ] **Step 4: 运行语法检查**

Run: `cd plugins/progress-tracker && python3 -m py_compile hooks/scripts/audit_log.py`
Expected: 无语法错误

- [ ] **Step 5: 提交审计日志模块**

```bash
git add hooks/scripts/audit_log.py
git commit -m "feat(lifecycle): add audit log module

- Implement append_audit_record() with atomic write
- Implement read_audit_log() with filtering
- Add audit ID and transaction ID generation"
```

---

### Task 3: 创建审计日志测试

**Files:**
- Create: `tests/test_audit_log.py`

- [ ] **Step 1: 写审计日志写入测试**

```python
# tests/test_audit_log.py
"""测试审计日志模块"""

import json
import pytest
from pathlib import Path
from datetime import datetime

import audit_log


class TestAuditLogBasic:
    """测试审计日志基础功能"""

    def test_generate_audit_id_incremental(self, temp_dir):
        """审计 ID 应该递增"""
        audit_path = temp_dir / "audit.log"

        # 模拟已存在的审计记录
        with open(audit_path, 'w') as f:
            json.dump({"id": "AUDIT-001", "feature_id": 1}, f)
            f.write('\n')
            json.dump({"id": "AUDIT-002", "feature_id": 2}, f)
            f.write('\n')

        # 覆盖 project_root
        import os
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        new_id = audit_log.generate_audit_id()
        assert new_id == "AUDIT-003"

    def test_generate_audit_id_when_no_log(self, temp_dir):
        """没有审计日志时应从 001 开始"""
        import os
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        audit_id = audit_log.generate_audit_id()
        assert audit_id == "AUDIT-001"

    def test_generate_tx_id_format(self):
        """事务 ID 格式应该正确"""
        tx_id = audit_log.generate_tx_id()
        assert tx_id.startswith("TX-")
        assert len(tx_id) == 17  # TX-YYYYMMDD-HHMMSS
```

- [ ] **Step 2: 运行测试确保失败**

Run: `cd plugins/progress-tracker && pytest tests/test_audit_log.py::TestAuditLogBasic -v`
Expected: FAIL (模块未集成)

- [ ] **Step 3: 修正审计日志模块以支持环境变量**

```python
# hooks/scripts/audit_log.py
def get_audit_log_path(project_root: Optional[str] = None) -> Path:
    """获取审计日志文件路径"""
    if project_root:
        base = Path(project_root)
    else:
        # 支持环境变量
        state_dir = os.environ.get("PROGRESS_TRACKER_STATE_DIR")
        if state_dir:
            base = Path(state_dir)
        else:
            base = Path(__file__).parent.parent.parent / "docs" / "progress-tracker" / "state"
    return base / AUDIT_LOG_FILENAME
```

- [ ] **Step 4: 再次运行测试**

Run: `cd plugins/progress-tracker && pytest tests/test_audit_log.py::TestAuditLogBasic -v`
Expected: PASS

- [ ] **Step 5: 写追加审计记录测试**

```python
def test_append_audit_record(self, temp_dir):
    """应该成功追加审计记录"""
    import os
    os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

    record = {
        "feature_id": 1,
        "op": "start",
        "from": "approved",
        "to": "implementing",
        "actor": "system",
        "reason": "测试",
    }

    result = audit_log.append_audit_record(record)
    assert result is True

    # 验证文件存在
    audit_path = temp_dir / "audit.log"
    assert audit_path.exists()

    # 验证内容
    with open(audit_path, 'r') as f:
        content = f.read()
        assert '"feature_id": 1' in content
        assert '"op": "start"' in content
```

- [ ] **Step 6: 运行测试**

Run: `cd plugins/progress-tracker && pytest tests/test_audit_log.py::TestAuditLogBasic::test_append_audit_record -v`
Expected: PASS

- [ ] **Step 7: 提交测试**

```bash
git add tests/test_audit_log.py hooks/scripts/audit_log.py
git commit -m "test(lifecycle): add audit log tests

- Test audit ID generation
- Test append_audit_record() functionality
- Support PROGRESS_TRACKER_STATE_DIR environment variable"
```

---

## Chunk 2: 状态机核心实现

### Task 4: 实现状态转换验证

**Files:**
- Modify: `hooks/scripts/lifecycle_state_machine.py`

- [ ] **Step 1: 实现基础验证函数**

```python
# hooks/scripts/lifecycle_state_machine.py
import os
from typing import Dict, Any, Optional


def load_progress_json(project_root: Optional[str] = None) -> Dict[str, Any]:
    """加载 progress.json"""
    if project_root:
        state_dir = Path(project_root) / "docs" / "progress-tracker" / "state"
    else:
        state_dir = Path(__file__).parent.parent.parent / "docs" / "progress-tracker" / "state"

    progress_file = state_dir / "progress.json"
    if not progress_file.exists():
        return {}

    with open(progress_file, 'r') as f:
        return json.load(f)


def get_feature(feature_id: int, project_root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """获取指定 feature"""
    data = load_progress_json(project_root)
    features = data.get("features", [])
    return next((f for f in features if f.get("id") == feature_id), None)


def validate_transition(
    feature_id: int,
    target_state: str,
    ctx: Dict[str, Any],
    project_root: Optional[str] = None
) -> ValidationResult:
    """
    验证状态转换是否合法

    检查项：
    1. feature 是否存在
    2. 目标状态是否有效
    3. 转换是否在 ALLOWED_TRANSITIONS 中
    """
    blockers = []
    warnings = []
    metadata = {}

    # 检查 feature 是否存在
    feature = get_feature(feature_id, project_root)
    if feature is None:
        blockers.append(ValidationError(
            code="FEATURE_NOT_FOUND",
            message=f"Feature ID {feature_id} 不存在",
            suggestion="请检查 feature ID 是否正确"
        ))
        return ValidationResult(
            valid=False,
            blockers=blockers,
            requested_state=target_state,
            metadata=metadata
        )

    current_state = feature.get("lifecycle_state", "approved")
    metadata["feature_name"] = feature.get("name", "")

    # 检查目标状态是否有效
    if target_state not in LIFECYCLE_STATES:
        blockers.append(ValidationError(
            code="INVALID_TARGET_STATE",
            message=f"目标状态 '{target_state}' 无效",
            suggestion=f"有效状态: {', '.join(LIFECYCLE_STATES)}",
            context={"target_state": target_state}
        ))
        return ValidationResult(
            valid=False,
            blockers=blockers,
            current_state=current_state,
            requested_state=target_state,
            metadata=metadata
        )

    # 检查转换是否允许
    allowed = ALLOWED_TRANSITIONS.get(current_state, [])
    if target_state not in allowed:
        blockers.append(ValidationError(
            code="FORBIDDEN_TRANSITION",
            message=f"不能从 '{current_state}' 转换到 '{target_state}'",
            suggestion=get_transition_suggestion(current_state, target_state),
            context={"current_state": current_state, "target_state": target_state}
        ))
        return ValidationResult(
            valid=False,
            blockers=blockers,
            current_state=current_state,
            requested_state=target_state,
            metadata=metadata
        )

    return ValidationResult(
        valid=True,
        current_state=current_state,
        requested_state=target_state,
        metadata=metadata
    )


def get_transition_suggestion(current: str, target: str) -> str:
    """获取状态转换建议"""
    suggestions = {
        ("archived", "implementing"): "归档状态不支持回退，如需重新开发请创建新 feature",
        ("archived", "approved"): "归档状态不支持回退，如需重新开发请创建新 feature",
        ("archived", "verified"): "归档状态已是终态",
        ("verified", "approved"): "verified 状态只能回退到 implementing 或归档到 archived",
    }
    return suggestions.get((current, target), "请检查状态转换规则")
```

- [ ] **Step 2: 运行语法检查**

Run: `cd plugins/progress-tracker && python3 -m py_compile hooks/scripts/lifecycle_state_machine.py`
Expected: 无语法错误

- [ ] **Step 3: 提交验证函数**

```bash
git add hooks/scripts/lifecycle_state_machine.py
git commit -m "feat(lifecycle): implement validate_transition()

- Check feature existence
- Validate target state
- Verify transition is allowed
- Return structured ValidationResult"
```

---

### Task 5: 创建状态机测试

**Files:**
- Create: `tests/test_lifecycle_state_machine.py`

- [ ] **Step 1: 写验证测试**

```python
# tests/test_lifecycle_state_machine.py
"""测试生命周期状态机"""

import pytest
from datetime import datetime

import lifecycle_state_machine


class TestValidateTransition:
    """测试状态转换验证"""

    @pytest.fixture
    def sample_progress(self, temp_dir):
        """创建示例进度数据"""
        data = {
            "schema_version": "2.0",
            "project_name": "Test",
            "features": [
                {
                    "id": 1,
                    "name": "Feature 1",
                    "lifecycle_state": "approved",
                    "development_stage": "planning",
                    "completed": False,
                    "test_steps": ["step 1"],
                },
                {
                    "id": 2,
                    "name": "Feature 2",
                    "lifecycle_state": "implementing",
                    "development_stage": "developing",
                    "completed": False,
                    "test_steps": ["step 1"],
                },
            ],
            "current_feature_id": None,
        }
        state_dir = temp_dir / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        progress_file = state_dir / "progress.json"
        progress_file.write_text(__import__("json").dumps(data))

        # 设置环境变量
        import os
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(state_dir)

        return state_dir

    def test_allowed_transition_succeeds(self, sample_progress):
        """允许的转换应该成功"""
        result = lifecycle_state_machine.validate_transition(
            1, "implementing", {}
        )
        assert result.valid is True
        assert result.current_state == "approved"
        assert result.requested_state == "implementing"

    def test_forbidden_transition_fails_with_suggestion(self, sample_progress):
        """禁止的转换应该失败并提供建议"""
        result = lifecycle_state_machine.validate_transition(
            1, "verified", {}
        )
        assert result.valid is False
        assert len(result.blockers) == 1
        assert result.blockers[0].code == "FORBIDDEN_TRANSITION"
        assert result.blockers[0].suggestion

    def test_feature_not_found_fails(self, sample_progress):
        """不存在的 feature 应该失败"""
        result = lifecycle_state_machine.validate_transition(
            999, "implementing", {}
        )
        assert result.valid is False
        assert result.blockers[0].code == "FEATURE_NOT_FOUND"

    def test_invalid_target_state_fails(self, sample_progress):
        """无效的目标状态应该失败"""
        result = lifecycle_state_machine.validate_transition(
            1, "invalid_state", {}
        )
        assert result.valid is False
        assert result.blockers[0].code == "INVALID_TARGET_STATE"
```

- [ ] **Step 2: 运行测试**

Run: `cd plugins/progress-tracker && pytest tests/test_lifecycle_state_machine.py::TestValidateTransition -v`
Expected: PASS

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_lifecycle_state_machine.py
git commit -m "test(lifecycle): add validate_transition tests

- Test allowed transitions succeed
- Test forbidden transitions fail with suggestions
- Test feature not found error
- Test invalid target state error"
```

---

## Chunk 3: 状态转换执行

### Task 6: 实现派生字段同步

**Files:**
- Modify: `hooks/scripts/lifecycle_state_machine.py`

- [ ] **Step 1: 实现派生字段同步函数**

```python
def _iso_now() -> str:
    """获取当前 ISO 格式时间"""
    return datetime.now().isoformat() + "Z"


def _sync_derived_fields(feature: Dict[str, Any], lifecycle_state: str, current_time: str = None):
    """
    根据 lifecycle_state 同步派生字段

    规则：
    - development_stage: 根据 lifecycle_state 一对一映射
    - completed: verified/archived 为 True，其他为 False
    - completed_at: completed=True 时设置，False 时删除
    - started_at: implementing 时设置（如果未设置）
    - archive_info: archived 时保留，其他状态删除
    """
    if current_time is None:
        current_time = _iso_now()

    state_mapping = {
        "approved": {
            "development_stage": "planning",
            "completed": False,
            "completed_at": None,  # 删除
        },
        "implementing": {
            "development_stage": "developing",
            "completed": False,
            "completed_at": None,  # 删除
        },
        "verified": {
            "development_stage": "completed",
            "completed": True,
            "completed_at": current_time,
            "archive_info": None,  # 删除
        },
        "archived": {
            "development_stage": "completed",
            "completed": True,
            # completed_at 保持不变
            # archive_info 由 archive_feature() 设置
        },
    }

    if lifecycle_state not in state_mapping:
        return

    for key, value in state_mapping[lifecycle_state].items():
        if value is None:
            # 删除字段
            if key in feature:
                del feature[key]
        elif key == "started_at" and value == current_time:
            # started_at 只在未设置时设置
            if not feature.get("started_at"):
                feature[key] = value
        else:
            feature[key] = value
```

- [ ] **Step 2: 运行语法检查**

Run: `cd plugins/progress-tracker && python3 -m py_compile hooks/scripts/lifecycle_state_machine.py`
Expected: 无语法错误

- [ ] **Step 3: 提交派生字段同步**

```bash
git add hooks/scripts/lifecycle_state_machine.py
git commit -m "feat(lifecycle): implement derived field sync

- Add _sync_derived_fields() function
- Sync development_stage, completed, completed_at, started_at
- Handle archive_info deletion for non-archived states"
```

---

### Task 7: 测试派生字段同步

**Files:**
- Modify: `tests/test_lifecycle_state_machine.py`

- [ ] **Step 1: 写派生字段同步测试**

```python
class TestSyncDerivedFields:
    """测试派生字段同步"""

    def test_sync_to_approved_sets_planning(self):
        """同步到 approved 应设置 planning"""
        feature = {
            "id": 1,
            "name": "Test",
            "lifecycle_state": "implementing",
            "development_stage": "developing",
            "completed": False,
            "completed_at": "2024-01-01T00:00:00Z",
        }
        lifecycle_state_machine._sync_derived_fields(feature, "approved", "2024-03-17T00:00:00Z")

        assert feature["development_stage"] == "planning"
        assert feature["completed"] is False
        assert "completed_at" not in feature

    def test_sync_to_implementing_sets_developing(self):
        """同步到 implementing 应设置 developing"""
        feature = {"id": 1, "name": "Test"}
        lifecycle_state_machine._sync_derived_fields(feature, "implementing", "2024-03-17T00:00:00Z")

        assert feature["development_stage"] == "developing"
        assert feature["completed"] is False
        assert feature["started_at"] == "2024-03-17T00:00:00Z"

    def test_sync_to_verified_sets_completed(self):
        """同步到 verified 应设置 completed"""
        feature = {"id": 1, "name": "Test"}
        lifecycle_state_machine._sync_derived_fields(feature, "verified", "2024-03-17T00:00:00Z")

        assert feature["development_stage"] == "completed"
        assert feature["completed"] is True
        assert feature["completed_at"] == "2024-03-17T00:00:00Z"
        assert "archive_info" not in feature

    def test_sync_to_archived_preserves_completed_at(self):
        """同步到 archived 应保留 completed_at"""
        feature = {
            "id": 1,
            "name": "Test",
            "completed_at": "2024-03-17T10:00:00Z",
        }
        lifecycle_state_machine._sync_derived_fields(feature, "archived", "2024-03-17T12:00:00Z")

        assert feature["development_stage"] == "completed"
        assert feature["completed"] is True
        assert feature["completed_at"] == "2024-03-17T10:00:00Z"  # 保持不变
```

- [ ] **Step 2: 运行测试**

Run: `cd plugins/progress-tracker && pytest tests/test_lifecycle_state_machine.py::TestSyncDerivedFields -v`
Expected: PASS

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_lifecycle_state_machine.py
git commit -m "test(lifecycle): add derived field sync tests

- Test sync to approved clears completed_at
- Test sync to implementing sets started_at
- Test sync to verified sets completed fields
- Test sync to archived preserves completed_at"
```

---

### Task 8: 实现状态转换执行

**Files:**
- Modify: `hooks/scripts/lifecycle_state_machine.py`

- [ ] **Step 1: 添加导入和锁工具**

```python
# hooks/scripts/lifecycle_state_machine.py 顶部添加
import json
import os
import fcntl
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

import audit_log


LOCK_FILENAME = "progress.lock"
LOCK_TIMEOUT_SECONDS = 10.0


@contextmanager
def acquire_lock(lock_path: Path, timeout: float = LOCK_TIMEOUT_SECONDS):
    """获取文件锁（上下文管理器）"""
    lock_file = None
    try:
        lock_file = open(lock_path, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield lock_file
    finally:
        if lock_file:
            fcntl.fcntl(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
```

- [ ] **Step 2: 实现原子写入**

```python
def _atomic_write(filepath: Path, content: str):
    """原子写入：临时文件 + fsync + rename"""
    temp_path = filepath.with_suffix(".tmp")
    with open(temp_path, 'w') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.rename(temp_path, filepath)
```

- [ ] **Step 3: 实现状态转换执行**

```python
def _execute_transition(
    feature_id: int,
    target_state: str,
    ctx: Dict[str, Any],
    validation: ValidationResult,
    project_root: Optional[str] = None
) -> TransitionRecord:
    """
    执行状态转换（私有，原子操作）

    步骤：
    1. 获取文件锁
    2. 读取当前状态并生成 before_snapshot
    3. 计算目标状态，生成完整的 after_snapshot
    4. 构建审计记录
    5. 两阶段提交：审计日志 → progress.json
    6. 释放锁
    """
    if project_root:
        state_dir = Path(project_root) / "docs" / "progress-tracker" / "state"
    else:
        state_dir = Path(__file__).parent.parent.parent / "docs" / "progress-tracker" / "state"

    lock_path = state_dir / LOCK_FILENAME
    progress_path = state_dir / "progress.json"

    tx_id = audit_log.generate_tx_id()
    current_time = _iso_now()

    with acquire_lock(lock_path):
        # 读取当前状态
        data = load_progress_json(project_root)
        features = data.get("features", [])
        feature_idx = next((i for i, f in enumerate(features) if f.get("id") == feature_id), -1)

        if feature_idx == -1:
            raise ValueError(f"Feature {feature_id} not found")

        feature = features[feature_idx]
        before_snapshot = {**feature}  # 深拷贝

        # 计算目标状态
        feature["lifecycle_state"] = target_state
        _sync_derived_fields(feature, target_state, current_time)

        # 处理特定操作的额外逻辑
        op = ctx.get("op", "transition")
        if op == "complete" and ctx.get("commit_hash"):
            feature["commit_hash"] = ctx["commit_hash"]

        after_snapshot = {**feature}

        # 构建审计记录
        audit_record = {
            "id": audit_log.generate_audit_id(),
            "tx_id": tx_id,
            "feature_id": feature_id,
            "op": op,
            "from": before_snapshot.get("lifecycle_state", ""),
            "to": target_state,
            "actor": ctx.get("actor", "system"),
            "reason": ctx.get("reason", ""),
            "metadata": ctx.get("metadata", {}),
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "timestamp": current_time,
            "success": True,
        }

        # 两阶段提交
        # 1. 写入审计日志
        audit_path = state_dir / audit_log.AUDIT_LOG_FILENAME
        _atomic_write(audit_path, _read_and_append_audit(audit_path, audit_record))

        # 2. 写入 progress.json
        data["updated_at"] = current_time
        _atomic_write(progress_path, json.dumps(data, indent=2, ensure_ascii=False))

        # 3. 更新 progress.md（非阻塞）
        try:
            from progress_manager import generate_progress_md, save_progress_md
            md_content = generate_progress_md(data)
            save_progress_md(md_content)
        except Exception:
            pass  # markdown 更新失败不影响核心功能

        return TransitionRecord(
            feature_id=feature_id,
            op=op,
            from_state=before_snapshot.get("lifecycle_state", ""),
            to_state=target_state,
            actor=ctx.get("actor", "system"),
            reason=ctx.get("reason", ""),
            metadata=ctx.get("metadata", {}),
            tx_id=tx_id,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            timestamp=current_time,
            success=True,
        )


def _read_and_append_audit(audit_path: Path, record: Dict[str, Any]) -> str:
    """读取现有审计日志并追加新记录"""
    existing_content = ""
    if audit_path.exists():
        with open(audit_path, 'r') as f:
            existing_content = f.read()
            if existing_content and not existing_content.endswith('\n'):
                existing_content += '\n'

    return existing_content + json.dumps(record, ensure_ascii=False) + '\n'
```

- [ ] **Step 4: 实现组合函数**

```python
def transition(
    feature_id: int,
    target_state: str,
    ctx: Dict[str, Any],
    dry_run: bool = False,
    project_root: Optional[str] = None
) -> TransitionOutcome:
    """
    组合验证和执行

    流程：
    1. 验证
    2. 如果 dry_run 或验证失败，返回结果
    3. 否则执行并返回完整结果
    """
    # 验证
    validation = validate_transition(feature_id, target_state, ctx, project_root)

    if not validation.valid or dry_run:
        return TransitionOutcome(
            validation=validation,
            changed=False,
        )

    # 执行
    try:
        record = _execute_transition(feature_id, target_state, ctx, validation, project_root)
        return TransitionOutcome(
            validation=validation,
            record=record,
            changed=True,
        )
    except Exception as e:
        # 执行失败
        validation.valid = False
        validation.blockers.append(ValidationError(
            code="EXECUTION_FAILED",
            message=f"执行失败: {str(e)}",
            suggestion="请检查文件权限和磁盘空间"
        ))
        return TransitionOutcome(
            validation=validation,
            changed=False,
        )
```

- [ ] **Step 5: 运行语法检查**

Run: `cd plugins/progress-tracker && python3 -m py_compile hooks/scripts/lifecycle_state_machine.py`
Expected: 无语法错误

- [ ] **Step 6: 提交执行逻辑**

```bash
git add hooks/scripts/lifecycle_state_machine.py
git commit -m "feat(lifecycle): implement transition execution

- Add file locking with context manager
- Implement _execute_transition() with two-phase commit
- Implement transition() combining validation and execution
- Add atomic write utilities"
```

---

## Chunk 4: 语义化业务入口

### Task 9: 实现语义化业务入口

**Files:**
- Modify: `hooks/scripts/lifecycle_state_machine.py`

- [ ] **Step 1: 实现语义化入口函数**

```python
def start_feature(feature_id: int, reason: str = "", project_root: Optional[str] = None) -> TransitionOutcome:
    """开始功能开发：approved → implementing"""
    return transition(
        feature_id, "implementing",
        {
            "op": "start",
            "actor": "system",
            "reason": reason or "开始功能开发",
            "metadata": {}
        },
        dry_run=False,
        project_root=project_root
    )


def complete_feature(
    feature_id: int,
    commit_hash: str = "",
    reason: str = "",
    archive_after_complete: bool = False,
    project_root: Optional[str] = None
) -> TransitionOutcome:
    """
    完成功能：implementing → verified

    参数：
    - archive_after_complete: 是否在完成后自动归档（默认 False）
    """
    ctx = {
        "op": "complete",
        "actor": "system",
        "reason": reason or "功能完成",
        "metadata": {}
    }
    if commit_hash:
        ctx["commit_hash"] = commit_hash
    if archive_after_complete:
        ctx["metadata"]["archive_after_complete"] = True

    result = transition(feature_id, "verified", ctx, dry_run=False, project_root=project_root)

    # 如果需要自动归档
    if archive_after_complete and result.changed:
        archive_result = archive_feature(feature_id, reason=f"自动归档：{reason or '功能完成'}", project_root=project_root)
        if not archive_result.validation.valid:
            result.validation.blockers.extend(archive_result.validation.blockers)

    return result


def archive_feature(feature_id: int, reason: str = "", project_root: Optional[str] = None) -> TransitionOutcome:
    """归档功能：verified → archived"""
    return transition(
        feature_id, "archived",
        {
            "op": "archive",
            "actor": "system",
            "reason": reason or "功能归档",
            "metadata": {}
        },
        dry_run=False,
        project_root=project_root
    )


def replan_feature(feature_id: int, reason: str = "", project_root: Optional[str] = None) -> TransitionOutcome:
    """重新规划：implementing → approved"""
    return transition(
        feature_id, "approved",
        {
            "op": "replan",
            "actor": "system",
            "reason": reason or "重新规划",
            "metadata": {}
        },
        dry_run=False,
        project_root=project_root
    )


def reopen_feature(feature_id: int, reason: str = "", project_root: Optional[str] = None) -> TransitionOutcome:
    """重开修复：verified → implementing"""
    return transition(
        feature_id, "implementing",
        {
            "op": "reopen",
            "actor": "system",
            "reason": reason or "重开修复",
            "metadata": {}
        },
        dry_run=False,
        project_root=project_root
    )
```

- [ ] **Step 2: 运行语法检查**

Run: `cd plugins/progress-tracker && python3 -m py_compile hooks/scripts/lifecycle_state_machine.py`
Expected: 无语法错误

- [ ] **Step 3: 提交语义化入口**

```bash
git add hooks/scripts/lifecycle_state_machine.py
git commit -m "feat(lifecycle): implement semantic API entry points

- Add start_feature()
- Add complete_feature() with archive_after_complete parameter
- Add archive_feature()
- Add replan_feature()
- Add reopen_feature()"
```

---

### Task 10: 测试语义化入口

**Files:**
- Modify: `tests/test_lifecycle_state_machine.py`

- [ ] **Step 1: 写语义化入口测试**

```python
class TestSemanticEntryPoints:
    """测试语义化业务入口"""

    @pytest.fixture
    def setup_progress(self, temp_dir):
        """设置测试数据"""
        data = {
            "schema_version": "2.0",
            "project_name": "Test",
            "features": [
                {
                    "id": 1,
                    "name": "Feature 1",
                    "lifecycle_state": "approved",
                    "development_stage": "planning",
                    "completed": False,
                    "test_steps": ["step 1"],
                },
            ],
            "current_feature_id": 1,
        }
        state_dir = temp_dir / "docs" / "progress-tracker" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        progress_file = state_dir / "progress.json"
        progress_file.write_text(__import__("json").dumps(data))

        import os
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(state_dir)

        return state_dir

    def test_start_feature_approved_to_implementing(self, setup_progress):
        """start_feature 应转换 approved → implementing"""
        result = lifecycle_state_machine.start_feature(1)

        assert result.changed is True
        assert result.validation.valid is True
        assert result.record.to_state == "implementing"

        # 验证状态已更新
        data = lifecycle_state_machine.load_progress_json()
        feature = data["features"][0]
        assert feature["lifecycle_state"] == "implementing"
        assert feature["development_stage"] == "developing"

    def test_complete_feature_implementing_to_verified(self, setup_progress):
        """complete_feature 应转换 implementing → verified"""
        # 先设置为 implementing
        data = lifecycle_state_machine.load_progress_json()
        data["features"][0]["lifecycle_state"] = "implementing"
        data["features"][0]["development_stage"] = "developing"
        lifecycle_state_machine._save_progress_json(data)

        result = lifecycle_state_machine.complete_feature(1, commit_hash="abc123")

        assert result.changed is True
        assert result.validation.valid is True
        assert result.record.to_state == "verified"
        assert result.record.after_snapshot.get("commit_hash") == "abc123"

    def test_archive_feature_verified_to_archived(self, setup_progress):
        """archive_feature 应转换 verified → archived"""
        # 先设置为 verified
        data = lifecycle_state_machine.load_progress_json()
        data["features"][0]["lifecycle_state"] = "verified"
        data["features"][0]["development_stage"] = "completed"
        data["features"][0]["completed"] = True
        data["features"][0]["completed_at"] = "2024-03-17T00:00:00Z"
        lifecycle_state_machine._save_progress_json(data)

        result = lifecycle_state_machine.archive_feature(1)

        assert result.changed is True
        assert result.validation.valid is True
        assert result.record.to_state == "archived"
```

- [ ] **Step 2: 添加辅助函数到 lifecycle_state_machine.py**

```python
# hooks/scripts/lifecycle_state_machine.py 添加
def _save_progress_json(data: Dict[str, Any], project_root: Optional[str] = None):
    """保存 progress.json"""
    if project_root:
        state_dir = Path(project_root) / "docs" / "progress-tracker" / "state"
    else:
        state_dir = Path(__file__).parent.parent.parent / "docs" / "progress-tracker" / "state"

    state_dir.mkdir(parents=True, exist_ok=True)
    progress_file = state_dir / "progress.json"

    with open(progress_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 3: 运行测试**

Run: `cd plugins/progress-tracker && pytest tests/test_lifecycle_state_machine.py::TestSemanticEntryPoints -v`
Expected: PASS

- [ ] **Step 4: 提交测试**

```bash
git add hooks/scripts/lifecycle_state_machine.py tests/test_lifecycle_state_machine.py
git commit -m "test(lifecycle): add semantic entry point tests

- Test start_feature() transitions
- Test complete_feature() with commit_hash
- Test archive_feature() transition
- Add _save_progress_json() helper"
```

---

## 验收测试

### Task 11: 运行完整的 DoD 验收测试

**Files:**
- Run: `pytest`

- [ ] **Step 1: 运行生命周期测试**

Run: `cd plugins/progress-tracker && pytest tests/test_lifecycle_state_machine.py -v`
Expected: 全部 PASS

- [ ] **Step 2: 运行审计日志测试**

Run: `cd plugins/progress-tracker && pytest tests/test_audit_log.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 运行现有的生命周期相关测试**

Run: `cd plugins/progress-tracker && pytest tests/test_feature_contract_readiness.py -q -k "lifecycle"`
Expected: PASS

- [ ] **Step 4: 运行状态转换测试**

Run: `cd plugins/progress-tracker && pytest tests/test_feature_completion_state_transition.py -q`
Expected: PASS

- [ ] **Step 5: 运行进度管理器测试**

Run: `cd plugins/progress-tracker && pytest tests/test_progress_manager.py -q -k "lifecycle or complete_feature or set_development_stage"`
Expected: PASS

- [ ] **Step 6: 提交验收通过**

```bash
git add .
git commit -m "test(lifecycle): all DoD tests passing

- validate_transition: 验证状态转换合法性
- execute_transition: 原子性执行两阶段提交
- audit log: 完整审计记录
- derived fields: 派生字段正确同步"
```

---

## 完成标准

- [ ] 所有单元测试通过
- [ ] 审计日志正确记录每次转换
- [ ] 派生字段与生命周期状态同步
- [ ] 非法转换被正确拒绝
- [ ] DoD 验收测试全部通过
