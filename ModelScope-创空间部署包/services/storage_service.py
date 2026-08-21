from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "xijian.db"


def initialize_database(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS comments (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opportunities (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS briefs (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, opportunity_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (task_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            """
        )


def save_analysis(state: dict, path: Path = DB_PATH) -> None:
    if not state or not state.get("task", {}).get("id"):
        return
    initialize_database(path)
    task = state["task"]
    task_id = task["id"]
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO tasks(id, payload, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (task_id, _json(task)),
        )
        _replace_rows(connection, "comments", state.get("comments", []), task_id)
        _replace_rows(connection, "signals", state.get("signals", []), task_id)
        _replace_rows(connection, "opportunities", state.get("opportunities", []), task_id)
        connection.execute(
            "INSERT OR REPLACE INTO snapshots(task_id, payload, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (task_id, _json(state)),
        )


def save_briefs(task_id: str, opportunity_id: str, briefs: list[dict], path: Path = DB_PATH) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM briefs WHERE task_id=? AND opportunity_id=?", (task_id, opportunity_id))
        connection.executemany(
            "INSERT INTO briefs(id, task_id, opportunity_id, payload) VALUES (?, ?, ?, ?)",
            [(f"{task_id}:{item['id']}", task_id, opportunity_id, _json(item)) for item in briefs],
        )


def load_briefs(task_id: str, opportunity_id: str, path: Path = DB_PATH) -> list[dict]:
    if not path.exists():
        return []
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT payload FROM briefs WHERE task_id=? AND opportunity_id=? ORDER BY rowid",
            (task_id, opportunity_id),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def load_latest_analysis(path: Path = DB_PATH) -> dict:
    if not path.exists():
        return {}
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT payload FROM snapshots ORDER BY updated_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    return json.loads(row[0]) if row else {}


def _replace_rows(connection, table: str, items: list[dict], task_id: str) -> None:
    connection.execute(f"DELETE FROM {table} WHERE task_id=?", (task_id,))
    connection.executemany(
        f"INSERT INTO {table}(id, task_id, payload) VALUES (?, ?, ?)",
        [(f"{task_id}:{item['id']}", task_id, _json(item)) for item in items],
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
