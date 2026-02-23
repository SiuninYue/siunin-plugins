"""Tests for project_memory.py data layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import project_memory


class TestProjectMemoryCore:
    """Core behavior tests for project memory storage."""

    def test_load_memory_returns_default_shape_when_missing(self, temp_dir):
        """Missing file should return default data without recovery."""
        data, recovered, backup = project_memory.load_memory()

        assert recovered is False
        assert backup is None
        assert data["schema_version"] == "1.0"
        assert data["next_capability_seq"] == 1
        assert data["last_synced_commit"] is None
        assert data["capabilities"] == []
        assert data["rejected_fingerprints"] == []
        assert data["sync_history"] == []
        assert data["limits"]["max_sync_history"] == 50
        assert data["limits"]["max_rejected_fingerprints"] == 500

    def test_append_is_idempotent(self, temp_dir):
        """Appending the same capability twice should dedupe the second write."""
        memory, _, _ = project_memory.load_memory()
        payload = {
            "title": "Registration API",
            "summary": "Add registration endpoint",
            "tags": ["api"],
            "source": {
                "origin": "prog_done",
                "feature_id": 1,
                "commit_hash": "abc123",
            },
            "confidence": 1.0,
        }

        first = project_memory.append_capability(memory, payload)
        project_memory.save_memory(memory)

        memory, _, _ = project_memory.load_memory()
        second = project_memory.append_capability(memory, payload)

        assert first["status"] == "inserted"
        assert second["status"] == "deduped"
        assert len(memory["capabilities"]) == 1
        assert memory["capabilities"][0]["cap_id"] == "CAP-001"

    def test_cross_dedupe_append_then_batch_upsert(self, temp_dir):
        """Capability from /prog done should dedupe during /prog sync batch-upsert."""
        memory, _, _ = project_memory.load_memory()
        done_payload = {
            "title": "OAuth Login",
            "summary": "Support GitHub OAuth login",
            "tags": ["auth", "oauth"],
            "source": {
                "origin": "prog_done",
                "feature_id": 2,
                "commit_hash": "deadbeef",
            },
        }
        append_result = project_memory.append_capability(memory, done_payload)
        assert append_result["status"] == "inserted"

        sync_payloads = [
            {
                "title": "OAuth Login",
                "summary": "Support GitHub OAuth login",
                "tags": ["auth"],
                "source_commit": "deadbeef",
                "feature_id": 2,
                "confidence": 0.91,
            }
        ]
        batch_result = project_memory.batch_upsert_capabilities(
            memory,
            sync_payloads,
            {"sync_id": "sync-1", "last_synced_commit": "deadbeef"},
        )

        assert batch_result["inserted_count"] == 0
        assert batch_result["deduped_count"] == 1
        assert len(memory["capabilities"]) == 1

    def test_sync_history_retention_keeps_latest_50(self, temp_dir):
        """Sync history should retain latest 50 entries."""
        memory, _, _ = project_memory.load_memory()

        for index in range(55):
            payloads = [
                {
                    "title": f"Capability {index}",
                    "summary": f"Summary {index}",
                    "tags": ["misc"],
                    "source_commit": f"commit-{index}",
                    "feature_id": index,
                    "confidence": 0.8,
                }
            ]
            project_memory.batch_upsert_capabilities(
                memory,
                payloads,
                {
                    "sync_id": f"sync-{index}",
                    "last_synced_commit": f"commit-{index}",
                },
            )

        assert len(memory["sync_history"]) == 50
        assert memory["sync_history"][0]["sync_id"] == "sync-5"
        assert memory["sync_history"][-1]["sync_id"] == "sync-54"
        assert memory["last_synced_commit"] == "commit-54"

    def test_rejected_fingerprint_retention_keeps_latest_500(self, temp_dir):
        """Rejected fingerprints should retain latest 500 unique items."""
        memory, _, _ = project_memory.load_memory()

        rejected = [
            {
                "title": f"Rejected {index}",
                "source_commit": f"rej-{index}",
                "feature_id": index,
            }
            for index in range(505)
        ]
        result = project_memory.register_rejections(memory, rejected, sync_id="sync-reject")

        expected_first = project_memory.compute_fingerprint("Rejected 5", "rej-5", 5)
        expected_last = project_memory.compute_fingerprint("Rejected 504", "rej-504", 504)

        assert result["added_count"] == 505
        assert len(memory["rejected_fingerprints"]) == 500
        assert memory["rejected_fingerprints"][0] == expected_first
        assert memory["rejected_fingerprints"][-1] == expected_last

    def test_load_memory_recovers_from_corruption_with_backup(self, temp_dir):
        """Corrupted JSON should be backed up and replaced with default structure."""
        claude_dir = Path(".claude")
        claude_dir.mkdir(parents=True, exist_ok=True)
        memory_path = claude_dir / "project_memory.json"
        memory_path.write_text("{invalid json", encoding="utf-8")

        data, recovered, backup = project_memory.load_memory()

        assert recovered is True
        assert backup is not None
        assert backup.exists()
        assert data["capabilities"] == []
        assert data["schema_version"] == "1.0"

        reloaded = json.loads(memory_path.read_text(encoding="utf-8"))
        assert reloaded["schema_version"] == "1.0"
        assert reloaded["capabilities"] == []

    def test_parse_index_selection_supports_ranges_and_empty(self):
        """Parser should handle mixed selections and empty input."""
        assert project_memory.parse_index_selection("1,3,5-7", total=7) == [0, 2, 4, 5, 6]
        assert project_memory.parse_index_selection("", total=10) == []

    def test_parse_index_selection_rejects_invalid_token(self):
        """Parser should reject invalid tokens and out-of-range indexes."""
        with pytest.raises(ValueError):
            project_memory.parse_index_selection("1,a", total=5)
        with pytest.raises(ValueError):
            project_memory.parse_index_selection("6", total=5)

    def test_register_rejections_updates_matching_sync_history_entry(self, temp_dir):
        """register-rejections should update rejected_count for the same sync_id."""
        memory, _, _ = project_memory.load_memory()
        project_memory.batch_upsert_capabilities(
            memory,
            [
                {
                    "title": "A",
                    "source_commit": "c1",
                    "feature_id": 1,
                }
            ],
            {"sync_id": "sync-42", "last_synced_commit": "c1"},
        )

        result = project_memory.register_rejections(
            memory,
            [{"title": "B", "source_commit": "c2", "feature_id": 2}],
            sync_id="sync-42",
        )

        assert result["added_count"] == 1
        assert memory["sync_history"][-1]["sync_id"] == "sync-42"
        assert memory["sync_history"][-1]["rejected_count"] == 1
