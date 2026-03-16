"""生命周期状态机核心模块

提供统一的状态转换验证、执行和审计功能。
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


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
