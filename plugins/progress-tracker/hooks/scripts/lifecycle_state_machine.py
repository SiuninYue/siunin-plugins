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
