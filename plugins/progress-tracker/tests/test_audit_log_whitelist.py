"""测试事件 schema 白名单：写入 fail-closed，读取 warn+preserve。"""
import json
import pytest
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log


def _make_record(event_type, id_="AUDIT-001"):
    return {
        "id": id_,
        "tx_id": "TX-20260424-120000-0001",
        "timestamp": "2026-04-24T12:00:00Z",
        "event_type": event_type,
    }


class TestAllowedEventTypesConstant:
    def test_constant_exists_and_is_frozenset(self):
        assert isinstance(audit_log.ALLOWED_EVENT_TYPES, frozenset)

    def test_contains_new_state_events(self):
        required = {
            "feature_completed", "feature_undone", "state_restored",
            "tracker_reset", "manual_state_override",
        }
        assert required.issubset(audit_log.ALLOWED_EVENT_TYPES)

    def test_contains_existing_production_events(self):
        """现有生产代码已在写入的类型必须在白名单内，否则静默丢数据。"""
        production = {
            "schema_migration", "evaluator_assessment", "evaluator_backfill",
            "set_finish_state", "set_sprint_contract",
        }
        assert production.issubset(audit_log.ALLOWED_EVENT_TYPES)

    def test_contains_project_completed_event(self):
        """project_completed must be in whitelist before _reset_active_progress can write it."""
        assert "project_completed" in audit_log.ALLOWED_EVENT_TYPES

    def test_is_known_event_type_helper(self):
        assert audit_log.is_known_event_type("feature_completed") is True
        assert audit_log.is_known_event_type("totally_unknown") is False


class TestWhitelistWriteEnforcement:
    def test_known_event_type_allowed(self, temp_dir, monkeypatch):
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        audit_log.append_audit_record(_make_record("feature_completed"))
        assert (temp_dir / "audit.log").exists()

    def test_set_finish_state_allowed(self, temp_dir, monkeypatch):
        """生产事件 set_finish_state 不应被拒绝。"""
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        audit_log.append_audit_record(_make_record("set_finish_state"))

    def test_set_sprint_contract_allowed(self, temp_dir, monkeypatch):
        """生产事件 set_sprint_contract 不应被拒绝。"""
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        audit_log.append_audit_record(_make_record("set_sprint_contract"))

    def test_unknown_event_type_raises_valueerror(self, temp_dir, monkeypatch):
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        with pytest.raises(ValueError, match="Unknown event_type"):
            audit_log.append_audit_record(_make_record("totally_unknown_event"))

    def test_no_partial_write_on_rejection(self, temp_dir, monkeypatch):
        """被拒绝的写入不应留下任何文件内容。"""
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        log_path = temp_dir / "audit.log"
        try:
            audit_log.append_audit_record(_make_record("bad_event"))
        except ValueError:
            pass
        assert not log_path.exists() or log_path.read_text().strip() == ""


class TestWhitelistReadTolerance:
    def test_unknown_event_preserved_on_read(self, temp_dir, monkeypatch):
        """历史数据中的未知事件：读取时保留（不报错）。"""
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        path = temp_dir / "audit.log"
        path.write_text(json.dumps({
            "id": "AUDIT-001", "tx_id": "TX-old",
            "timestamp": "2024-01-01T00:00:00Z",
            "event_type": "legacy_unknown_event",
        }) + "\n")
        records = audit_log.read_audit_log()
        assert len(records) == 1
        assert records[0]["event_type"] == "legacy_unknown_event"
