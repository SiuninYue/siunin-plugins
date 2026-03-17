"""测试审计日志模块"""

import json
import pytest
from pathlib import Path
from datetime import datetime
import os

# Add hooks/scripts to path
import sys
SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

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
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        new_id = audit_log.generate_audit_id()
        assert new_id == "AUDIT-003"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_generate_audit_id_when_no_log(self, temp_dir):
        """没有审计日志时应从 001 开始"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        audit_id = audit_log.generate_audit_id()
        assert audit_id == "AUDIT-001"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_generate_tx_id_format(self):
        """事务 ID 格式应该正确"""
        tx_id = audit_log.generate_tx_id()
        assert tx_id.startswith("TX-")
        # TX-YYYYMMDD-HHMMSS-mmmm format: 3 + 8 + 1 + 6 + 1 + 4 = 23 characters
        assert len(tx_id) == 23
        # Verify it matches the expected pattern (with microsecond suffix to avoid collision)
        import re
        assert re.match(r'^TX-\d{8}-\d{6}-\d{4}$', tx_id)


class TestAppendAuditRecord:
    """测试追加审计记录"""

    def test_append_audit_record_success(self, temp_dir):
        """成功追加审计记录"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        record = {
            "id": "AUDIT-001",
            "tx_id": "TX-20240101-120000",
            "timestamp": "2024-01-01T12:00:00Z",
            "feature_id": 1,
            "event_type": "test_event",
            "details": {"key": "value"}
        }

        audit_log.append_audit_record(record)

        # 验证文件存在并包含记录
        audit_path = temp_dir / "audit.log"
        assert audit_path.exists()

        with open(audit_path, 'r') as f:
            content = f.read()
            parsed_record = json.loads(content.strip())
            assert parsed_record["id"] == "AUDIT-001"
            assert parsed_record["tx_id"] == "TX-20240101-120000"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_append_audit_record_missing_id(self, temp_dir):
        """缺少 id 字段时应抛出 ValueError"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        record = {
            "tx_id": "TX-20240101-120000",
            "timestamp": "2024-01-01T12:00:00Z"
        }

        with pytest.raises(ValueError, match="must have 'id' field"):
            audit_log.append_audit_record(record)

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_append_audit_record_missing_tx_id(self, temp_dir):
        """缺少 tx_id 字段时应抛出 ValueError"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        record = {
            "id": "AUDIT-001",
            "timestamp": "2024-01-01T12:00:00Z"
        }

        with pytest.raises(ValueError, match="must have 'tx_id' field"):
            audit_log.append_audit_record(record)

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_append_audit_record_missing_timestamp(self, temp_dir):
        """缺少 timestamp 字段时应抛出 ValueError"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        record = {
            "id": "AUDIT-001",
            "tx_id": "TX-20240101-120000"
        }

        with pytest.raises(ValueError, match="must have 'timestamp' field"):
            audit_log.append_audit_record(record)

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_append_multiple_records(self, temp_dir):
        """追加多条记录应该都保存成功"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        records = [
            {
                "id": "AUDIT-001",
                "tx_id": "TX-20240101-120000",
                "timestamp": "2024-01-01T12:00:00Z",
                "feature_id": 1
            },
            {
                "id": "AUDIT-002",
                "tx_id": "TX-20240101-120001",
                "timestamp": "2024-01-01T12:00:01Z",
                "feature_id": 2
            }
        ]

        for record in records:
            audit_log.append_audit_record(record)

        audit_path = temp_dir / "audit.log"
        with open(audit_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2

            record1 = json.loads(lines[0].strip())
            assert record1["id"] == "AUDIT-001"

            record2 = json.loads(lines[1].strip())
            assert record2["id"] == "AUDIT-002"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]


class TestReadAuditLog:
    """测试读取审计日志"""

    def test_read_audit_log_empty(self, temp_dir):
        """读取空的审计日志应返回空列表"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        records = audit_log.read_audit_log()
        assert records == []

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_read_audit_log_with_records(self, temp_dir):
        """读取包含记录的审计日志"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        # 先写入一些记录
        records = [
            {
                "id": "AUDIT-001",
                "tx_id": "TX-20240101-120000",
                "timestamp": "2024-01-01T12:00:00Z",
                "feature_id": 1,
                "event_type": "event1"
            },
            {
                "id": "AUDIT-002",
                "tx_id": "TX-20240101-120001",
                "timestamp": "2024-01-01T12:00:01Z",
                "feature_id": 2,
                "event_type": "event2"
            }
        ]

        for record in records:
            audit_log.append_audit_record(record)

        # 读取所有记录
        read_records = audit_log.read_audit_log()
        assert len(read_records) == 2
        assert read_records[0]["id"] == "AUDIT-002"  # 默认降序
        assert read_records[1]["id"] == "AUDIT-001"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_read_audit_log_filter_by_feature_id(self, temp_dir):
        """按 feature_id 过滤记录"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        # 写入不同 feature 的记录
        records = [
            {
                "id": "AUDIT-001",
                "tx_id": "TX-20240101-120000",
                "timestamp": "2024-01-01T12:00:00Z",
                "feature_id": 1
            },
            {
                "id": "AUDIT-002",
                "tx_id": "TX-20240101-120001",
                "timestamp": "2024-01-01T12:00:01Z",
                "feature_id": 2
            },
            {
                "id": "AUDIT-003",
                "tx_id": "TX-20240101-120002",
                "timestamp": "2024-01-01T12:00:02Z",
                "feature_id": 1
            }
        ]

        for record in records:
            audit_log.append_audit_record(record)

        # 过滤 feature_id = 1
        filtered = audit_log.read_audit_log(feature_id=1)
        assert len(filtered) == 2
        assert all(r["feature_id"] == 1 for r in filtered)

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_read_audit_log_filter_by_tx_id(self, temp_dir):
        """按 tx_id 过滤记录"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        records = [
            {
                "id": "AUDIT-001",
                "tx_id": "TX-20240101-120000",
                "timestamp": "2024-01-01T12:00:00Z",
                "feature_id": 1
            },
            {
                "id": "AUDIT-002",
                "tx_id": "TX-20240101-120001",
                "timestamp": "2024-01-01T12:00:01Z",
                "feature_id": 2
            }
        ]

        for record in records:
            audit_log.append_audit_record(record)

        # 过滤 tx_id
        filtered = audit_log.read_audit_log(tx_id="TX-20240101-120000")
        assert len(filtered) == 1
        assert filtered[0]["id"] == "AUDIT-001"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_read_audit_log_with_limit(self, temp_dir):
        """测试 limit 参数"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        # 写入 5 条记录
        for i in range(5):
            record = {
                "id": f"AUDIT-{i+1:03d}",
                "tx_id": f"TX-20240101-1200{i}",
                "timestamp": f"2024-01-01T12:00:0{i}Z",
                "feature_id": 1
            }
            audit_log.append_audit_record(record)

        # 限制返回 3 条
        records = audit_log.read_audit_log(limit=3)
        assert len(records) == 3

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_read_audit_log_ascending(self, temp_dir):
        """测试升序排列"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        records = [
            {
                "id": "AUDIT-001",
                "tx_id": "TX-20240101-120000",
                "timestamp": "2024-01-01T12:00:00Z",
                "feature_id": 1
            },
            {
                "id": "AUDIT-002",
                "tx_id": "TX-20240101-120001",
                "timestamp": "2024-01-01T12:00:01Z",
                "feature_id": 2
            }
        ]

        for record in records:
            audit_log.append_audit_record(record)

        # 升序读取
        ascending_records = audit_log.read_audit_log(ascending=True)
        assert len(ascending_records) == 2
        assert ascending_records[0]["id"] == "AUDIT-001"
        assert ascending_records[1]["id"] == "AUDIT-002"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]


class TestGetLatestAuditRecord:
    """测试获取最新审计记录"""

    def test_get_latest_audit_record_exists(self, temp_dir):
        """获取存在的最新记录"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        records = [
            {
                "id": "AUDIT-001",
                "tx_id": "TX-20240101-120000",
                "timestamp": "2024-01-01T12:00:00Z",
                "feature_id": 1,
                "event_type": "old"
            },
            {
                "id": "AUDIT-002",
                "tx_id": "TX-20240101-120001",
                "timestamp": "2024-01-01T12:00:01Z",
                "feature_id": 1,
                "event_type": "new"
            }
        ]

        for record in records:
            audit_log.append_audit_record(record)

        latest = audit_log.get_latest_audit_record(feature_id=1)
        assert latest is not None
        assert latest["event_type"] == "new"
        assert latest["id"] == "AUDIT-002"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_get_latest_audit_record_not_exists(self, temp_dir):
        """获取不存在的 feature 的记录应返回 None"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        latest = audit_log.get_latest_audit_record(feature_id=999)
        assert latest is None

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]


class TestGetAuditRecordById:
    """测试根据 ID 获取审计记录"""

    def test_get_audit_record_by_id_exists(self, temp_dir):
        """获取存在的记录"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        record = {
            "id": "AUDIT-001",
            "tx_id": "TX-20240101-120000",
            "timestamp": "2024-01-01T12:00:00Z",
            "feature_id": 1,
            "event_type": "test"
        }

        audit_log.append_audit_record(record)

        found = audit_log.get_audit_record_by_id("AUDIT-001")
        assert found is not None
        assert found["event_type"] == "test"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_get_audit_record_by_id_not_exists(self, temp_dir):
        """获取不存在的记录应返回 None"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        found = audit_log.get_audit_record_by_id("AUDIT-999")
        assert found is None

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]


class TestCountAuditRecords:
    """测试统计审计记录数"""

    def test_count_audit_records_empty(self, temp_dir):
        """统计空日志应返回 0"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        count = audit_log.count_audit_records()
        assert count == 0

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_count_audit_records_with_data(self, temp_dir):
        """统计包含记录的日志"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        # 写入 3 条记录
        for i in range(3):
            record = {
                "id": f"AUDIT-{i+1:03d}",
                "tx_id": f"TX-20240101-1200{i}",
                "timestamp": f"2024-01-01T12:00:0{i}Z",
                "feature_id": 1
            }
            audit_log.append_audit_record(record)

        count = audit_log.count_audit_records()
        assert count == 3

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]


class TestGetAuditLogPath:
    """测试获取审计日志路径"""

    def test_get_audit_log_path_with_env_var(self, temp_dir):
        """使用环境变量覆盖路径"""
        os.environ["PROGRESS_TRACKER_STATE_DIR"] = str(temp_dir)

        path = audit_log.get_audit_log_path()
        assert path == temp_dir / "audit.log"

        # 清理环境变量
        del os.environ["PROGRESS_TRACKER_STATE_DIR"]

    def test_get_audit_log_path_default(self):
        """默认路径应该是相对于项目根目录"""
        # 不设置环境变量，使用默认路径
        path = audit_log.get_audit_log_path()
        # 默认路径应该包含 audit.log
        assert path.name == "audit.log"
