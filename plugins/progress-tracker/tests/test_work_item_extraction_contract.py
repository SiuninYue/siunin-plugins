"""Contract tests for F23 work-item selection extraction."""

from datetime import datetime, timezone

import next_feature_commands
import progress_manager
import work_item_selector
from work_item_selector import WorkItemSelectorServices


def test_work_item_selector_exports_and_facade_wrappers():
    assert callable(work_item_selector.get_next_feature)
    assert callable(work_item_selector.get_dispatched_child_feature)
    assert callable(work_item_selector.select_next_work_item)

    assert progress_manager.get_next_feature.is_wrapper is True
    assert progress_manager._get_dispatched_child_feature.is_wrapper is True
    assert progress_manager._select_next_work_item.is_wrapper is True


def test_next_feature_command_export_and_facade_wrapper():
    assert callable(next_feature_commands.next_feature_command)
    assert progress_manager.next_feature.is_wrapper is True


def test_work_item_selector_uses_injected_now_for_stale_routes(tmp_path):
    child_root = tmp_path / "child"
    child_root.mkdir()
    child_payload = {
        "features": [{"id": 7, "name": "Child feature", "completed": False}]
    }

    def _service(now):
        return WorkItemSelectorServices(
            load_progress_json_fn=lambda: {},
            is_feature_deferred_fn=lambda _feature: False,
            parse_iso_timestamp_fn=lambda value: datetime.fromisoformat(value),
            now_fn=lambda: now,
            warn_fn=lambda _message: None,
            resolve_linked_project_root_fn=lambda _raw, _project, _repo: child_root,
            load_progress_payload_at_root_fn=lambda _root: (child_payload, None),
            stale_after_hours=1,
            root_route_code="ROOT",
        )

    routing_queue = ["PT"]
    active_routes = [
        {"project_code": "PT", "assigned_at": "2026-06-04T00:30:00+00:00"}
    ]
    linked_projects = [{"project_code": "PT", "project_root": str(child_root)}]

    fresh_route = work_item_selector.get_dispatched_child_feature(
        routing_queue,
        active_routes,
        linked_projects,
        project_root=tmp_path,
        repo_root=tmp_path,
        svc=_service(datetime(2026, 6, 4, 1, 0, tzinfo=timezone.utc)),
    )
    assert fresh_route is None

    stale_route = work_item_selector.get_dispatched_child_feature(
        routing_queue,
        active_routes,
        linked_projects,
        project_root=tmp_path,
        repo_root=tmp_path,
        svc=_service(datetime(2026, 6, 4, 2, 0, tzinfo=timezone.utc)),
    )
    assert stale_route is not None
    assert stale_route["next_feature_id"] == 7
