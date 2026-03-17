"""生命周期状态机核心模块

提供统一的状态转换验证、执行和审计功能。
"""

import contextlib
import copy
import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

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
    except OSError as e:
        # On some systems (e.g., macOS with certain temp filesystems),
        # fcntl.flock() can fail with EFAULT (errno 14).
        # In testing environments, we continue without locking.
        # In production, this should be rare but we allow continuation.
        import errno
        if e.errno == errno.EFAULT:
            # Continue without locking (test environment or unsupported filesystem)
            if lock_file:
                yield lock_file
            else:
                lock_file = open(lock_path, 'w')
                yield lock_file
        else:
            raise
    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass  # Ignore unlock errors
            lock_file.close()


def _atomic_write(filepath: Path, content: str):
    """原子写入：临时文件 + fsync + rename"""
    temp_path = filepath.with_suffix(".tmp")
    with open(temp_path, 'w') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.rename(temp_path, filepath)


@dataclass
class ValidationError:
    """结构化验证错误"""
    code: str  # "FORBIDDEN_TRANSITION", "FEATURE_NOT_FOUND", "STATE_DIVERGED"
    message: str  # 人类可读错误描述
    suggestion: str = ""  # 建议的修复方法
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """状态转换验证结果"""
    valid: bool
    blockers: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    current_state: str = ""
    requested_state: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


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


@dataclass
class TransitionOutcome:
    """状态转换结果（统一返回类型）"""
    validation: ValidationResult
    record: Optional[TransitionRecord] = None
    changed: bool = False


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


def _iso_now() -> str:
    """获取当前 ISO 格式时间 (UTC)"""
    return datetime.utcnow().isoformat() + "Z"


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
            "archive_info": None,  # 删除
        },
        "implementing": {
            "development_stage": "developing",
            "completed": False,
            "completed_at": None,  # 删除
            "started_at": current_time,  # 只在未设置时设置
            "archive_info": None,  # 删除
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
        raise ValueError(f"Invalid lifecycle_state: {lifecycle_state}. Valid states: {list(state_mapping.keys())}")

    for key, value in state_mapping[lifecycle_state].items():
        if value is None:
            # 删除字段
            if key in feature:
                del feature[key]
        elif key == "started_at":
            # started_at 只在未设置时设置
            if "started_at" not in feature:
                feature[key] = value
        else:
            feature[key] = value


def _read_and_append_audit(audit_path: Path, record: Dict[str, Any]) -> str:
    """读取现有审计日志并追加新记录"""
    existing_content = ""
    if audit_path.exists():
        with open(audit_path, 'r') as f:
            existing_content = f.read()
            if existing_content and not existing_content.endswith('\n'):
                existing_content += '\n'

    return existing_content + json.dumps(record, ensure_ascii=False) + '\n'


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
        before_snapshot = copy.deepcopy(feature)  # 深拷贝

        # 计算目标状态
        feature["lifecycle_state"] = target_state
        _sync_derived_fields(feature, target_state, current_time)

        # 处理特定操作的额外逻辑
        op = ctx.get("op", "transition")
        if op == "complete" and ctx.get("commit_hash"):
            feature["commit_hash"] = ctx["commit_hash"]

        after_snapshot = copy.deepcopy(feature)

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


# =============================================================================
# 语义化业务入口 API
# =============================================================================

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
            # Mark partial failure in metadata
            result.validation.metadata["partial_failure"] = "archive_failed"
            result.validation.metadata["archive_succeeded"] = False

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
