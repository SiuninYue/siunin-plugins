"""Integration tests: next_feature entropy preflight."""
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "scripts"))

import workspace_entropy
from next_feature_commands import NextFeatureCommandServices, next_feature_command


def _make_svc(**overrides):
    """Build a minimal NextFeatureCommandServices for testing."""
    # Note: a strict spec mock would only expose dataclass fields that carry
    # defaults (entropy_preflight_fn), so use a plain MagicMock and set the
    # attributes next_feature_command actually reads.
    svc = MagicMock()
    svc.load_progress_json_fn.return_value = None
    svc.finish_pending_state = "finish_pending"
    svc.linked_snapshot_schema_version = "1.0"
    svc.root_route_code = "ROOT"
    svc.repo_root = None
    svc.analyze_reconcile_state_fn.return_value = {"diagnosis": None}
    svc.get_next_feature_fn.return_value = None
    svc.entropy_preflight_fn = None  # disabled by default
    for k, v in overrides.items():
        setattr(svc, k, v)
    return svc


def test_next_feature_blocks_on_red_entropy(tmp_path):
    """next_feature must block when entropy preflight finds red blocks."""
    import io
    captured = io.StringIO()

    def _red_preflight(project_root):
        # Return an object simulating has_red_blocks=True
        result = MagicMock()
        result.has_red_blocks = True
        result.report = {
            "dirty_changes": {"block": ["hooks/scripts/some_file.py"], "auto_commit": [], "quarantine": []},
            "branches": {"delete_local": [], "review": [], "keep": []},
        }
        result.to_block_payload.return_value = {
            "status": "blocked",
            "reason": "workspace_entropy_red",
            "block": ["hooks/scripts/some_file.py"],
            "message": "Workspace entropy check found destructive pending changes. Resolve before continuing.",
            "recommended_next_step": "Run `prog entropy-fix --safe` to see safe actions, or resolve manually.",
        }
        return result

    svc = _make_svc(entropy_preflight_fn=_red_preflight)

    with patch("sys.stdout", captured):
        result = next_feature_command(output_json=True, svc=svc)

    assert result is False
    output = captured.getvalue()
    data = json.loads(output)
    assert data["status"] == "blocked"
    assert data["reason"] == "workspace_entropy_red"


def test_next_feature_skips_entropy_when_preflight_fn_is_none(tmp_path):
    """When entropy_preflight_fn is None, next_feature proceeds normally."""
    svc = _make_svc(entropy_preflight_fn=None)
    # load_progress_json_fn returns None → falls through to "no progress file" path
    # We just need it to NOT block with workspace_entropy_red
    import io
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        next_feature_command(output_json=True, svc=svc)
    output = captured.getvalue()
    if output.strip():
        data = json.loads(output)
        assert data.get("reason") != "workspace_entropy_red"
