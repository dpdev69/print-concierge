from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


def append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def initialize_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS print_plans (
            plan_hash TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    return connection


def insert_print_plan(connection: sqlite3.Connection, plan_hash: str, job_id: str, payload: Mapping[str, Any]) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO print_plans (plan_hash, job_id, payload_json) VALUES (?, ?, ?)",
        (plan_hash, job_id, json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)),
    )
    connection.commit()


def fetch_all_print_plans(connection: sqlite3.Connection) -> Iterable[Dict[str, Any]]:
    rows = connection.execute("SELECT plan_hash, job_id, payload_json, created_at FROM print_plans").fetchall()
    for plan_hash, job_id, payload_json, created_at in rows:
        yield {
            "plan_hash": plan_hash,
            "job_id": job_id,
            "payload": json.loads(payload_json),
            "created_at": created_at,
        }
