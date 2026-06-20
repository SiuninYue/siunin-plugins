"""Tests for progress-tracker storage migration side effects."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import prog_paths


class TestStorageMigrationLog:
    def test_noop_migration_does_not_write_log(self, temp_dir):
        result = prog_paths.ensure_storage_migrated(temp_dir)

        log_path = temp_dir / "docs" / "progress-tracker" / "state" / "migration_log.json"
        assert result["migrated"] is False
        assert not log_path.exists()

    def test_real_migration_writes_log(self, temp_dir):
        legacy_dir = temp_dir / ".claude"
        legacy_dir.mkdir()
        (legacy_dir / "progress.json").write_text('{"project_name": "Legacy"}', encoding="utf-8")

        result = prog_paths.ensure_storage_migrated(temp_dir)

        log_path = temp_dir / "docs" / "progress-tracker" / "state" / "migration_log.json"
        log_entries = json.loads(log_path.read_text(encoding="utf-8"))

        assert result["migrated"] is True
        assert (temp_dir / "docs" / "progress-tracker" / "state" / "progress.json").exists()
        assert len(log_entries) == 1
        assert log_entries[0]["status"] == "migrated"
        assert log_entries[0]["operations"]
