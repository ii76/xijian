from __future__ import annotations

import json
import sqlite3

import pytest

from services.analytics_service import EVENT_NAMES, event_summary, funnel_metrics, record_event


def test_all_required_events_can_be_recorded(tmp_path) -> None:
    path = tmp_path / "events.db"
    for event_name in EVENT_NAMES:
        record_event(event_name, "T-TEST", "OPP-001", {"source": "test"}, path)
    summary = event_summary(path)
    assert set(summary) == EVENT_NAMES
    assert all(count == 1 for count in summary.values())


def test_event_metadata_rejects_comment_text_and_secrets(tmp_path) -> None:
    path = tmp_path / "events.db"
    for key in ("comment_content", "raw_text", "api_key", "access_token", "secret"):
        with pytest.raises(ValueError, match="不能包含"):
            record_event("demo_started", metadata={key: "sensitive"}, path=path)


def test_event_storage_contains_ids_and_safe_metadata_only(tmp_path) -> None:
    path = tmp_path / "events.db"
    record_event("brief_generated", "T-1", "OPP-2", {"brief_count": 3}, path)
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT event_name, task_id, opportunity_id, metadata FROM events"
        ).fetchone()
    assert row[:3] == ("brief_generated", "T-1", "OPP-2")
    assert json.loads(row[3]) == {"brief_count": 3}


def test_unknown_event_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="不支持"):
        record_event("unknown", path=tmp_path / "events.db")


def test_funnel_metrics_are_derived_from_events(tmp_path) -> None:
    path = tmp_path / "events.db"
    record_event("import_succeeded", path=path)
    record_event("brief_generated", path=path)
    metrics = funnel_metrics(path)
    assert metrics["core_flow_completion_rate"] == 1.0
