from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from services.storage_service import DB_PATH, initialize_database


EVENT_NAMES = {
    "demo_started",
    "task_created",
    "import_succeeded",
    "import_failed",
    "analysis_completed",
    "analysis_failed",
    "opportunity_clicked",
    "evidence_opened",
    "brief_generated",
    "brief_copied",
    "markdown_exported",
}
SENSITIVE_KEYS = ("content", "text", "comment", "body", "api_key", "token", "secret")


def record_event(
    event_name: str,
    task_id: str = "",
    opportunity_id: str = "",
    metadata: dict | None = None,
    path: Path = DB_PATH,
) -> None:
    if event_name not in EVENT_NAMES:
        raise ValueError(f"不支持的事件：{event_name}")
    if os.getenv("PYTEST_CURRENT_TEST") and Path(path) == DB_PATH:
        return
    safe_metadata = _safe_metadata(metadata or {})
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                task_id TEXT NOT NULL DEFAULT '',
                opportunity_id TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO events(event_name, task_id, opportunity_id, metadata) VALUES (?, ?, ?, ?)",
            (event_name, task_id or "", opportunity_id or "", json.dumps(safe_metadata, ensure_ascii=False)),
        )


def event_summary(path: Path = DB_PATH) -> dict[str, int]:
    if not path.exists():
        return {}
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_name TEXT NOT NULL, task_id TEXT NOT NULL DEFAULT '', opportunity_id TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        rows = connection.execute(
            "SELECT event_name, COUNT(*) FROM events GROUP BY event_name ORDER BY event_name"
        ).fetchall()
    return {name: count for name, count in rows}


def funnel_metrics(path: Path = DB_PATH) -> dict:
    summary = event_summary(path)
    imports = summary.get("import_succeeded", 0)
    briefs = summary.get("brief_generated", 0)
    return {
        "events": summary,
        "successful_imports": imports,
        "brief_generations": briefs,
        "core_flow_completion_rate": min(1.0, briefs / imports) if imports else 0.0,
    }


def _safe_metadata(metadata: dict) -> dict:
    output = {}
    for key, value in metadata.items():
        normalized = str(key).casefold()
        if any(fragment in normalized for fragment in SENSITIVE_KEYS):
            raise ValueError("事件元数据不能包含评论正文、密钥或令牌。")
        if isinstance(value, (str, int, float, bool)) or value is None:
            output[str(key)] = value
    return output
