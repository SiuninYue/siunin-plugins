"""Tests for _auto_state_commit and supporting functions."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import sys

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager


class TestStateFileConstants:
    def test_state_file_names_contains_required_files(self):
        assert "progress.json" in progress_manager.STATE_FILE_NAMES
        assert "progress.md" in progress_manager.STATE_FILE_NAMES
        assert "checkpoints.json" in progress_manager.STATE_FILE_NAMES
        assert "audit.log" in progress_manager.STATE_FILE_NAMES
        assert "project_memory.json" in progress_manager.STATE_FILE_NAMES
        assert "sprint_ledger.jsonl" in progress_manager.STATE_FILE_NAMES

    def test_state_file_names_excludes_lock(self):
        assert "progress.lock" not in progress_manager.STATE_FILE_NAMES

    def test_state_dir_names_contains_required_dirs(self):
        assert "test_reports" in progress_manager.STATE_DIR_NAMES
        assert "progress_archive" in progress_manager.STATE_DIR_NAMES
