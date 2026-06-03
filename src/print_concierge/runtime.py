from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from dataclasses import is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return value.__dict__
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


class RuntimeState:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("PRINT_CONCIERGE_STATE_DB")
        self.path = Path(configured or "~/.print-concierge/state.sqlite3").expanduser()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS print_plans (
                    plan_hash TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS confirmation_challenges (
                    token_hash TEXT PRIMARY KEY,
                    challenge_id TEXT NOT NULL,
                    plan_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(plan_hash) REFERENCES print_plans(plan_hash)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_results (
                    job_id TEXT PRIMARY KEY,
                    plan_hash TEXT NOT NULL,
                    queue_payload_json TEXT NOT NULL,
                    queue_result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(plan_hash) REFERENCES print_plans(plan_hash)
                )
                """
            )
            connection.commit()
        self.path.chmod(0o600)

    def save_plan(self, plan: Mapping[str, Any]) -> None:
        payload = dict(plan)
        plan_hash = str(payload["plan_hash"])
        job_id = str(payload["job_id"])
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO print_plans
                    (plan_hash, job_id, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    plan_hash,
                    job_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    _iso(_utc_now()),
                ),
            )
            connection.commit()

    def get_plan(self, plan_hash: str) -> dict[str, Any]:
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM print_plans WHERE plan_hash = ?",
                (plan_hash,),
            ).fetchone()
        if row is None:
            raise LookupError("print plan was not found")
        return dict(json.loads(row[0]))

    def create_challenge(
        self, plan: Mapping[str, Any], *, ttl: timedelta = timedelta(minutes=5)
    ) -> dict[str, Any]:
        payload = dict(plan)
        self.save_plan(payload)
        token = f"pc_{secrets.token_urlsafe(12)}"
        now = _utc_now()
        challenge = {
            "challenge_id": uuid4().hex,
            "job_id": str(payload["job_id"]),
            "plan_hash": str(payload["plan_hash"]),
            "user_id": str(payload["user_id"]),
            "chat_id": str(
                payload.get("session_id")
                or payload.get("slicer_settings", {}).get("session_id")
                or payload["user_id"]
            ),
            "file_hash": str(payload["file_hash"]),
            "printer_id": str(payload["printer"]["printer_id"]),
            "material_profile": str(payload["material_profile"]),
            "expires_at": _iso(now + ttl),
            "created_at": _iso(now),
        }
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO confirmation_challenges
                    (token_hash, challenge_id, plan_hash, payload_json, expires_at, used_at, created_at)
                VALUES (?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    _hash_token(token),
                    challenge["challenge_id"],
                    challenge["plan_hash"],
                    json.dumps(challenge, ensure_ascii=False, sort_keys=True),
                    challenge["expires_at"],
                    challenge["created_at"],
                ),
            )
            connection.commit()
        return {**challenge, "token": token}

    def consume_challenge(self, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
        token_hash = _hash_token(token)
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT payload_json, expires_at, used_at
                FROM confirmation_challenges
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                raise ValueError("confirmation token not found")
            challenge = dict(json.loads(row[0]))
            if row[2] is not None:
                raise ValueError("confirmation token already used")
            if _utc_now() > _parse_iso(str(row[1])):
                raise ValueError("confirmation token expired")
            plan = self.get_plan(str(challenge["plan_hash"]))
            self._validate_challenge_binding(challenge, plan)
            connection.execute(
                "UPDATE confirmation_challenges SET used_at = ? WHERE token_hash = ?",
                (_iso(_utc_now()), token_hash),
            )
            connection.commit()
        return challenge, plan

    def save_queue_result(
        self,
        *,
        plan_hash: str,
        job_id: str,
        queue_payload: Mapping[str, Any],
        queue_result: Mapping[str, Any],
    ) -> None:
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO queue_results
                    (job_id, plan_hash, queue_payload_json, queue_result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    plan_hash,
                    json.dumps(dict(queue_payload), ensure_ascii=False, sort_keys=True),
                    json.dumps(dict(queue_result), ensure_ascii=False, sort_keys=True),
                    _iso(_utc_now()),
                ),
            )
            connection.commit()

    @staticmethod
    def _validate_challenge_binding(
        challenge: Mapping[str, Any], plan: Mapping[str, Any]
    ) -> None:
        expected = {
            "job_id": str(plan["job_id"]),
            "plan_hash": str(plan["plan_hash"]),
            "user_id": str(plan["user_id"]),
            "chat_id": str(
                plan.get("session_id")
                or plan.get("slicer_settings", {}).get("session_id")
                or plan["user_id"]
            ),
            "file_hash": str(plan["file_hash"]),
            "printer_id": str(plan["printer"]["printer_id"]),
            "material_profile": str(plan["material_profile"]),
        }
        actual = {key: str(challenge[key]) for key in expected}
        if actual != expected:
            raise ValueError("confirmation token binding mismatch")


class RuntimeConfirmationService:
    def __init__(
        self,
        state: RuntimeState | None = None,
        *,
        ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self.state = state or RuntimeState()
        self.ttl = ttl

    def request_confirmation(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        payload = _jsonable(plan)
        return self.state.create_challenge(payload, ttl=self.ttl)


class RuntimeQueueGateway:
    def __init__(self, state: RuntimeState | None = None, client: Any = None) -> None:
        self.state = state or RuntimeState()
        self.client = client

    def queue_confirmed_print(self, confirmation_token: str) -> dict[str, Any]:
        if self.client is None or not hasattr(self.client, "queue_print"):
            raise TypeError("Bambuddy queue client is not configured")
        challenge, plan = self.state.consume_challenge(confirmation_token)
        queue_payload = {
            **plan,
            "_print_concierge_confirmed": True,
            "confirmation": {
                "challenge_id": challenge["challenge_id"],
                "plan_hash": challenge["plan_hash"],
            },
        }
        result = dict(self.client.queue_print(queue_payload))
        job_id = str(result["job_id"])
        self.state.save_queue_result(
            plan_hash=str(plan["plan_hash"]),
            job_id=job_id,
            queue_payload=queue_payload,
            queue_result=result,
        )
        return result
