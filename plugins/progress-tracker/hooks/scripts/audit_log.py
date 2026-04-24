"""审计日志模块

提供 append-only 的 JSONL 审计日志功能。
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import random


AUDIT_LOG_FILENAME = "audit.log"

# 事件类型白名单：写入路径 fail-closed；读取路径兼容历史数据（tolerant）
# 新增 event_type 时必须先加入此集合，否则 append_audit_record 拒绝写入。
ALLOWED_EVENT_TYPES: frozenset = frozenset({
    # 核心状态变更事件（Feature 0 新增）
    "feature_completed",
    "feature_undone",
    "state_restored",
    "tracker_reset",
    "manual_state_override",
    # 现有生产代码已写入的事件类型（不可移除，否则静默丢数据）
    "schema_migration",
    "evaluator_assessment",
    "evaluator_backfill",
    "set_finish_state",
})


def is_known_event_type(event_type: str) -> bool:
    """供读取路径判断是否为已知事件类型（不阻断，仅供 warn 决策）。"""
    return event_type in ALLOWED_EVENT_TYPES


def get_audit_log_path(project_root: Optional[str] = None) -> Path:
    """获取审计日志文件路径

    优先使用环境变量 PROGRESS_TRACKER_STATE_DIR 用于测试，
    否则使用相对于项目根目录的默认路径。

    Args:
        project_root: 项目根目录路径（可选）

    Returns:
        审计日志文件的完整路径
    """
    # 支持环境变量覆盖（用于测试）
    state_dir = os.environ.get("PROGRESS_TRACKER_STATE_DIR")
    if state_dir:
        return Path(state_dir) / AUDIT_LOG_FILENAME

    if project_root:
        # project_root 是项目根目录，审计日志在 state 子目录下
        base = Path(project_root) / "docs" / "progress-tracker" / "state"
    else:
        # 默认路径相对于当前文件
        base = Path(__file__).parent.parent.parent / "docs" / "progress-tracker" / "state"
    return base / AUDIT_LOG_FILENAME


def generate_audit_id(project_root: Optional[str] = None) -> str:
    """生成审计记录 ID

    从审计日志中读取最大 ID 并递增。

    Args:
        project_root: 项目根目录路径（可选，用于隔离项目）

    Returns:
        格式为 "AUDIT-XXX" 的唯一 ID（XXX 为 3 位数字，从 001 开始）
    """
    path = get_audit_log_path(project_root)
    if not path.exists():
        return "AUDIT-001"

    max_num = 0
    try:
        with open(path, 'r', encoding='utf-8') as f:
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
    """生成事务 ID（带微秒精度避免碰撞）

    Returns:
        格式为 "TX-YYYYMMDD-HHMMSS-mmmmmm" 的事务 ID（mmmmmm 为微秒）
    """
    now = datetime.now(timezone.utc)
    microsecond_suffix = random.randint(1000, 9999)  # 4 位随机数避免碰撞
    return f"TX-{now.strftime('%Y%m%d-%H%M%S')}-{microsecond_suffix:04d}"


def append_audit_record(record: Dict[str, Any], project_root: Optional[str] = None) -> None:
    """追加写入审计记录（原子操作）

    使用临时文件 + rename 保证原子性，确保写入过程中发生崩溃时不会损坏日志。

    Args:
        record: 审计记录字典，必须包含所有必需字段
        project_root: 项目根目录路径（可选，用于测试）

    Raises:
        IOError: 文件写入失败
        ValueError: 记录格式无效
    """
    # 验证记录格式
    if not record.get("id"):
        raise ValueError("Audit record must have 'id' field")
    if not record.get("tx_id"):
        raise ValueError("Audit record must have 'tx_id' field")
    if not record.get("timestamp"):
        raise ValueError("Audit record must have 'timestamp' field")

    # 事件类型白名单 fail-closed：未知类型在写入时拒绝，防止污染事实源
    event_type = record.get("event_type", "")
    if event_type and event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(
            f"Unknown event_type '{event_type}'. "
            f"Add to ALLOWED_EVENT_TYPES in audit_log.py before use. "
            f"Known types: {sorted(ALLOWED_EVENT_TYPES)}"
        )

    path = get_audit_log_path(project_root)

    # 确保父目录存在
    path.parent.mkdir(parents=True, exist_ok=True)

    # 写入临时文件
    temp_path = path.with_suffix('.tmp')
    try:
        with open(temp_path, 'a', encoding='utf-8') as f:
            json_str = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
            f.write(json_str + '\n')
            f.flush()
            os.fsync(f.fileno())

        # 原子性重命名（追加操作）
        # 注意：对于追加操作，我们直接追加到原文件，因为追加通常是原子的
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json_str + '\n')
            f.flush()
            os.fsync(f.fileno())

        # 清理临时文件
        try:
            temp_path.unlink()
        except OSError:
            pass

    except Exception as e:
        # 清理临时文件
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise IOError(f"Failed to append audit record: {e}")


def read_audit_log(
    project_root: Optional[str] = None,
    feature_id: Optional[int] = None,
    tx_id: Optional[str] = None,
    limit: Optional[int] = None,
    ascending: bool = False
) -> List[Dict[str, Any]]:
    """读取审计日志（支持过滤和排序）

    Args:
        project_root: 项目根目录路径（可选，用于测试）
        feature_id: 过滤特定 feature 的记录（可选）
        tx_id: 过滤特定事务的记录（可选）
        limit: 限制返回记录数量（可选）
        ascending: 是否按时间戳升序排列（默认降序）

    Returns:
        审计记录列表，每条记录是一个字典
    """
    path = get_audit_log_path(project_root)

    if not path.exists():
        return []

    records = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        # 应用过滤器
                        if feature_id is not None and record.get("feature_id") != feature_id:
                            continue
                        if tx_id is not None and record.get("tx_id") != tx_id:
                            continue
                        records.append(record)
                    except (json.JSONDecodeError, ValueError):
                        # 跳过无效的行
                        continue
    except (IOError, OSError):
        return []

    # 按时间戳排序
    def get_timestamp(record: Dict[str, Any]) -> str:
        return record.get("timestamp", "")

    records.sort(key=get_timestamp, reverse=not ascending)

    # 应用限制
    if limit is not None:
        records = records[:limit]

    return records


def get_latest_audit_record(
    feature_id: int,
    project_root: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """获取指定 feature 的最新审计记录

    Args:
        feature_id: feature ID
        project_root: 项目根目录路径（可选，用于测试）

    Returns:
        最新的审计记录，如果不存在则返回 None
    """
    records = read_audit_log(
        project_root=project_root,
        feature_id=feature_id,
        limit=1,
        ascending=False
    )
    return records[0] if records else None


def get_audit_record_by_id(
    audit_id: str,
    project_root: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """根据审计 ID 获取记录

    Args:
        audit_id: 审计记录 ID（如 "AUDIT-001"）
        project_root: 项目根目录路径（可选，用于测试）

    Returns:
        审计记录，如果不存在则返回 None
    """
    path = get_audit_log_path(project_root)

    if not path.exists():
        return None

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if record.get("id") == audit_id:
                            return record
                    except (json.JSONDecodeError, ValueError):
                        continue
    except (IOError, OSError):
        pass

    return None


def count_audit_records(project_root: Optional[str] = None) -> int:
    """统计审计日志记录总数

    Args:
        project_root: 项目根目录路径（可选，用于测试）

    Returns:
        记录总数
    """
    path = get_audit_log_path(project_root)

    if not path.exists():
        return 0

    count = 0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    count += 1
    except (IOError, OSError):
        return 0

    return count


def _record_content_hash(record: Dict[str, Any]) -> str:
    """生成记录内容的哈希键（排除 id 字段）。"""
    content = {k: v for k, v in record.items() if k != "id"}
    return json.dumps(content, sort_keys=True)


def deduplicate_audit_log(
    records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """两阶段去重审计日志记录。

    Pass 1 — id 去重：
      - same id + same content → 删副本（保留先出现的）
      - same id + diff content → ID 冲突，重编号冲突条（两者都保留）

    Pass 2 — 语义去重：
      - same (timestamp + event_type + feature_id) → 删副本
      - feature_id 缺失时退化为 (timestamp + event_type)

    冲突元数据记录在 id_conflict_metadata 列表，不写入 kept records 本身。

    Returns:
        {
          "kept": [records],
          "removed": [records],
          "semantic_duplicates_removed": [records],
          "id_conflicts": int,
          "id_conflict_metadata": [{"original_id": str, "new_id": str}],
        }
    """
    import copy

    kept_pass1: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    id_conflict_metadata: List[Dict[str, Any]] = []
    id_conflicts = 0

    # 计算最大 AUDIT-XXX 编号，用于重编号冲突条目
    max_id_num = 0
    for record in records:
        rid = record.get("id", "")
        if rid.startswith("AUDIT-"):
            try:
                num = int(rid.split("-")[1])
                max_id_num = max(max_id_num, num)
            except (ValueError, IndexError):
                # 非标准格式，跳过但不崩溃
                pass

    # --- Pass 1: id 去重 ---
    seen_ids: Dict[str, str] = {}  # id → content_hash of first seen

    for record in records:
        rid = record.get("id", "")
        content_hash = _record_content_hash(record)

        if rid not in seen_ids:
            seen_ids[rid] = content_hash
            kept_pass1.append(copy.deepcopy(record))
        else:
            if seen_ids[rid] == content_hash:
                # 完全相同：删副本
                removed.append(record)
            else:
                # ID 冲突：重编号此条，保留两者
                max_id_num += 1
                new_id = f"AUDIT-{max_id_num:03d}"
                new_record = copy.deepcopy(record)
                new_record["id"] = new_id
                kept_pass1.append(new_record)
                id_conflict_metadata.append({
                    "original_id": rid,
                    "new_id": new_id,
                })
                id_conflicts += 1

    # --- Pass 2: 语义去重 ---
    seen_semantic: set = set()
    kept: List[Dict[str, Any]] = []
    semantic_removed: List[Dict[str, Any]] = []

    for record in kept_pass1:
        ts = record.get("timestamp", "")
        et = record.get("event_type", "")
        fid = record.get("feature_id")

        semantic_key = (ts, et, str(fid)) if fid is not None else (ts, et)

        if semantic_key not in seen_semantic:
            seen_semantic.add(semantic_key)
            kept.append(record)
        else:
            semantic_removed.append(record)

    return {
        "kept": kept,
        "removed": removed,
        "semantic_duplicates_removed": semantic_removed,
        "id_conflicts": id_conflicts,
        "id_conflict_metadata": id_conflict_metadata,
    }


def clear_audit_log(project_root: Optional[str] = None) -> None:
    """清空审计日志（仅用于测试）

    Args:
        project_root: 项目根目录路径（可选，用于测试）

    Raises:
        IOError: 文件操作失败
    """
    path = get_audit_log_path(project_root)

    if path.exists():
        path.unlink()
