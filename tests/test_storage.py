import json

from print_concierge.storage import (
    append_jsonl,
    fetch_all_print_plans,
    initialize_sqlite,
    insert_print_plan,
    read_jsonl,
)


def test_read_jsonl_returns_empty_list_for_missing_path(tmp_path):
    assert read_jsonl(tmp_path / "missing" / "events.jsonl") == []


def test_append_jsonl_creates_parent_directories_and_round_trips_sorted_json(tmp_path):
    path = tmp_path / "nested" / "events.jsonl"

    append_jsonl(path, {"z": 1, "a": {"b": 2}})
    append_jsonl(path, {"message": "ok", "count": 2})

    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == [
        json.dumps({"a": {"b": 2}, "z": 1}, ensure_ascii=False, sort_keys=True),
        json.dumps({"count": 2, "message": "ok"}, ensure_ascii=False, sort_keys=True),
    ]
    assert read_jsonl(path) == [
        {"a": {"b": 2}, "z": 1},
        {"count": 2, "message": "ok"},
    ]


def test_initialize_sqlite_creates_storage_tables(tmp_path):
    connection = initialize_sqlite(tmp_path / "state.sqlite3")
    try:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {"print_plans", "audit_events"}.issubset(table_names)


def test_print_plan_storage_round_trips_payload_and_replaces_existing_hash(tmp_path):
    connection = initialize_sqlite(tmp_path / "state.sqlite3")
    try:
        insert_print_plan(
            connection,
            plan_hash="hash-1",
            job_id="job-1",
            payload={"material": "PLA", "settings": {"supports": False}},
        )
        insert_print_plan(
            connection,
            plan_hash="hash-1",
            job_id="job-2",
            payload={"material": "PETG", "settings": {"supports": True}},
        )

        rows = list(fetch_all_print_plans(connection))
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["plan_hash"] == "hash-1"
    assert rows[0]["job_id"] == "job-2"
    assert rows[0]["payload"] == {"material": "PETG", "settings": {"supports": True}}
    assert rows[0]["created_at"]
