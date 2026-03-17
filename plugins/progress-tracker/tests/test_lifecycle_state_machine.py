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

        return temp_dir

    def test_allowed_transition_succeeds(self, sample_progress):
        """允许的转换应该成功"""
        result = lifecycle_state_machine.validate_transition(
            1, "implementing", {}, str(sample_progress)
        )
        assert result.valid is True
        assert result.current_state == "approved"
        assert result.requested_state == "implementing"

    def test_forbidden_transition_fails_with_suggestion(self, sample_progress):
        """禁止的转换应该失败并提供建议"""
        result = lifecycle_state_machine.validate_transition(
            1, "verified", {}, str(sample_progress)
        )
        assert result.valid is False
        assert len(result.blockers) == 1
        assert result.blockers[0].code == "FORBIDDEN_TRANSITION"
        assert result.blockers[0].suggestion

    def test_feature_not_found_fails(self, sample_progress):
        """不存在的 feature 应该失败"""
        result = lifecycle_state_machine.validate_transition(
            999, "implementing", {}, str(sample_progress)
        )
        assert result.valid is False
        assert result.blockers[0].code == "FEATURE_NOT_FOUND"

    def test_invalid_target_state_fails(self, sample_progress):
        """无效的目标状态应该失败"""
        result = lifecycle_state_machine.validate_transition(
            1, "invalid_state", {}, str(sample_progress)
        )
        assert result.valid is False
        assert result.blockers[0].code == "INVALID_TARGET_STATE"


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
