from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from print_concierge.audit import AuditLogger
from print_concierge.models import (
    AuditEvent,
    ModelSearchResult as PlanModelSearchResult,
    PrintPlan,
    PrinterInfo,
    RiskFlag,
)
from print_concierge.policy import PolicyConfig, PolicyEngine


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
                CREATE TABLE IF NOT EXISTS print_requests (
                    request_id TEXT PRIMARY KEY,
                    plan_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    approved_at TEXT,
                    rejected_at TEXT,
                    queued_at TEXT,
                    queue_job_id TEXT,
                    queue_result_json TEXT,
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

    def create_print_request(
        self, plan: Mapping[str, Any], *, ttl: timedelta = timedelta(minutes=30)
    ) -> dict[str, Any]:
        payload = dict(plan)
        self._validate_plan_hash(payload)
        self.save_plan(payload)
        now = _utc_now()
        request = {
            "request_id": f"req_{uuid4().hex}",
            "status": "pending_user_approval",
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
            "summary": self._request_summary(payload),
            "expires_at": _iso(now + ttl),
            "created_at": _iso(now),
        }
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO print_requests
                    (
                        request_id,
                        plan_hash,
                        payload_json,
                        status,
                        expires_at,
                        approved_at,
                        rejected_at,
                        queued_at,
                        queue_job_id,
                        queue_result_json,
                        created_at
                    )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?)
                """,
                (
                    request["request_id"],
                    request["plan_hash"],
                    json.dumps(request, ensure_ascii=False, sort_keys=True),
                    request["status"],
                    request["expires_at"],
                    request["created_at"],
                ),
            )
            connection.commit()
        return dict(request)

    def get_print_request(self, request_id: str) -> dict[str, Any]:
        request = self._get_print_request_raw(request_id)
        if (
            request["status"] == "pending_user_approval"
            and _utc_now() > _parse_iso(str(request["expires_at"]))
        ):
            request = self._set_request_status(request_id, "expired")
        return request

    def list_print_requests(
        self, *, status: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        self.initialize()
        query = """
            SELECT
                payload_json,
                status,
                approved_at,
                rejected_at,
                queued_at,
                queue_job_id,
                queue_result_json,
                expires_at
            FROM print_requests
        """
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self.get_print_request(self._request_from_row(row)["request_id"]) for row in rows]

    def approve_print_request(self, request_id: str) -> dict[str, Any]:
        request = self.get_print_request(request_id)
        if request["status"] != "pending_user_approval":
            raise ValueError(f"print request is not pending: {request['status']}")
        return self._set_request_status(request_id, "approved", approved_at=_iso(_utc_now()))

    def reject_print_request(self, request_id: str) -> dict[str, Any]:
        request = self.get_print_request(request_id)
        if request["status"] != "pending_user_approval":
            raise ValueError(f"print request is not pending: {request['status']}")
        return self._set_request_status(request_id, "rejected", rejected_at=_iso(_utc_now()))

    def load_approved_request_plan(self, request_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        request = self.get_print_request(request_id)
        if request["status"] == "queued":
            raise ValueError("print request already used")
        if request["status"] != "approved":
            raise ValueError(f"print request is not approved: {request['status']}")
        plan = self.get_plan(str(request["plan_hash"]))
        self._validate_request_binding(request, plan)
        return request, plan

    def load_queueable_request_plan(self, request_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        request = self.get_print_request(request_id)
        self._raise_if_not_queueable(request["status"])
        plan = self.get_plan(str(request["plan_hash"]))
        self._validate_request_binding(request, plan)
        return request, plan

    def claim_request_for_queue(self, request_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        request, plan = self.load_queueable_request_plan(request_id)
        now = _iso(_utc_now())
        updated = {
            **request,
            "status": "queueing",
            "queueing_at": now,
            "approved_at": request.get("approved_at") or now,
        }
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                """
                UPDATE print_requests
                SET
                    status = ?,
                    payload_json = ?,
                    approved_at = COALESCE(approved_at, ?)
                WHERE request_id = ? AND status = ?
                """,
                (
                    "queueing",
                    json.dumps(updated, ensure_ascii=False, sort_keys=True),
                    updated["approved_at"],
                    request_id,
                    request["status"],
                ),
            )
            connection.commit()

        if cursor.rowcount != 1:
            latest = self.get_print_request(request_id)
            self._raise_if_not_queueable(latest["status"])
            raise ValueError("print request could not be claimed for queue")
        return updated, plan

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

    def mark_request_queued(
        self,
        *,
        request_id: str,
        plan_hash: str,
        job_id: str,
        queue_payload: Mapping[str, Any],
        queue_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _iso(_utc_now())
        self.save_queue_result(
            plan_hash=plan_hash,
            job_id=job_id,
            queue_payload=queue_payload,
            queue_result=queue_result,
        )
        request = self.get_print_request(request_id)
        updated = {
            **request,
            "status": "queued",
            "queued_at": now,
            "queue_job_id": job_id,
            "queue_result": dict(queue_result),
        }
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE print_requests
                SET
                    status = ?,
                    payload_json = ?,
                    queued_at = ?,
                    queue_job_id = ?,
                    queue_result_json = ?
                WHERE request_id = ?
                """,
                (
                    "queued",
                    json.dumps(updated, ensure_ascii=False, sort_keys=True),
                    now,
                    job_id,
                    json.dumps(dict(queue_result), ensure_ascii=False, sort_keys=True),
                    request_id,
                ),
            )
            connection.commit()
        return updated

    def mark_request_failed(self, *, request_id: str, error: str) -> dict[str, Any]:
        now = _iso(_utc_now())
        request = self.get_print_request(request_id)
        message = str(error)[:500]
        updated = {
            **request,
            "status": "failed",
            "failed_at": now,
            "queue_error": message,
        }
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                """
                UPDATE print_requests
                SET
                    status = ?,
                    payload_json = ?
                WHERE request_id = ? AND status = ?
                """,
                (
                    "failed",
                    json.dumps(updated, ensure_ascii=False, sort_keys=True),
                    request_id,
                    "queueing",
                ),
            )
            connection.commit()
        if cursor.rowcount != 1:
            return self.get_print_request(request_id)
        return updated

    @staticmethod
    def _validate_request_binding(
        request: Mapping[str, Any], plan: Mapping[str, Any]
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
        actual = {key: str(request[key]) for key in expected}
        if actual != expected:
            raise ValueError("print request binding mismatch")

    @staticmethod
    def _raise_if_not_queueable(status: str) -> None:
        if status == "queued":
            raise ValueError("print request already used")
        if status == "queueing":
            raise ValueError("print request already queueing")
        if status not in {"pending_user_approval", "approved"}:
            raise ValueError(f"print request cannot be queued: {status}")

    @staticmethod
    def _request_summary(plan: Mapping[str, Any]) -> dict[str, Any]:
        model = dict(plan.get("model") or {})
        printer = dict(plan.get("printer") or {})
        return {
            "title": str(model.get("title") or plan.get("job_id")),
            "file_name": model.get("file_name"),
            "file_hash": str(plan.get("file_hash", "")),
            "printer_id": str(printer.get("printer_id", "")),
            "printer": printer.get("display_name") or printer.get("printer_id"),
            "material_profile": str(plan.get("material_profile", "")),
            "source": model.get("source"),
        }

    @classmethod
    def _validate_plan_hash(cls, plan: Mapping[str, Any]) -> None:
        expected = str(plan.get("plan_hash") or "")
        if not expected:
            raise ValueError("plan_hash is required")
        actual = cls._compute_plan_hash(plan)
        if actual != expected:
            raise ValueError("plan_hash does not match immutable plan payload")

    @staticmethod
    def _compute_plan_hash(plan: Mapping[str, Any]) -> str:
        printer = dict(plan.get("printer") or {})
        model = dict(plan.get("model") or {})
        risk_flags = [
            item if isinstance(item, RiskFlag) else RiskFlag(**dict(item))
            for item in plan.get("risk_flags", [])
        ]
        print_plan = PrintPlan(
            job_id=str(plan["job_id"]),
            user_id=str(plan["user_id"]),
            file_hash=str(plan["file_hash"]),
            printer=PrinterInfo(**printer),
            model=PlanModelSearchResult(**model),
            material_profile=str(plan["material_profile"]),
            schema_version=int(plan.get("schema_version", 1)),
            risk_flags=risk_flags,
            slicer_settings=dict(plan.get("slicer_settings") or {}),
            estimated_grams=plan.get("estimated_grams"),
            estimated_minutes=plan.get("estimated_minutes"),
            created_at=str(plan.get("created_at")) if plan.get("created_at") else _iso(_utc_now()),
            transient_metadata=dict(plan.get("transient_metadata") or {}),
            status=plan.get("status", "confirmation_required"),
        )
        return print_plan.plan_hash

    @staticmethod
    def _request_from_row(row: Any) -> dict[str, Any]:
        request = dict(json.loads(row[0]))
        request["status"] = str(row[1])
        if row[2]:
            request["approved_at"] = str(row[2])
        if row[3]:
            request["rejected_at"] = str(row[3])
        if row[4]:
            request["queued_at"] = str(row[4])
        if row[5]:
            request["queue_job_id"] = str(row[5])
        if row[6]:
            request["queue_result"] = dict(json.loads(row[6]))
        request["expires_at"] = str(row[7])
        return request

    def _set_request_status(
        self,
        request_id: str,
        status: str,
        *,
        approved_at: str | None = None,
        rejected_at: str | None = None,
    ) -> dict[str, Any]:
        request = self._get_print_request_raw(request_id)
        updated = {**request, "status": status}
        if approved_at:
            updated["approved_at"] = approved_at
        if rejected_at:
            updated["rejected_at"] = rejected_at
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE print_requests
                SET
                    status = ?,
                    payload_json = ?,
                    approved_at = COALESCE(?, approved_at),
                    rejected_at = COALESCE(?, rejected_at)
                WHERE request_id = ?
                """,
                (
                    status,
                    json.dumps(updated, ensure_ascii=False, sort_keys=True),
                    approved_at,
                    rejected_at,
                    request_id,
                ),
            )
            connection.commit()
        return updated

    def _get_print_request_raw(self, request_id: str) -> dict[str, Any]:
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT
                    payload_json,
                    status,
                    approved_at,
                    rejected_at,
                    queued_at,
                    queue_job_id,
                    queue_result_json,
                    expires_at
                FROM print_requests
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        if row is None:
            raise LookupError("print request was not found")
        return self._request_from_row(row)


class RuntimeApprovalService:
    def __init__(
        self,
        state: RuntimeState | None = None,
        *,
        ttl: timedelta = timedelta(minutes=30),
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.state = state or RuntimeState()
        self.ttl = ttl
        self.audit_logger = audit_logger

    def create_print_request(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        payload = _jsonable(plan)
        request = self.state.create_print_request(payload, ttl=self.ttl)
        self._record("print_request.created", request)
        return request

    def get_print_request_status(self, request_id: str) -> dict[str, Any]:
        return self.state.get_print_request(request_id)

    def list_print_requests(
        self, *, status: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self.state.list_print_requests(status=status, limit=limit)

    def approve_print_request(self, request_id: str) -> dict[str, Any]:
        request = self.state.approve_print_request(request_id)
        self._record("print_request.approved", request)
        return request

    def reject_print_request(self, request_id: str) -> dict[str, Any]:
        request = self.state.reject_print_request(request_id)
        self._record("print_request.rejected", request)
        return request

    def _record(self, event_type: str, request: Mapping[str, Any]) -> None:
        if self.audit_logger is None:
            return
        self.audit_logger.record(
            AuditEvent(
                event_type=event_type,
                actor_id=str(request.get("user_id") or ""),
                job_id=str(request.get("job_id") or ""),
                details={
                    "request_id": request.get("request_id"),
                    "plan_hash": request.get("plan_hash"),
                    "status": request.get("status"),
                    "printer_id": request.get("printer_id"),
                    "file_hash": request.get("file_hash"),
                },
            )
        )


class RuntimeQueueGateway:
    def __init__(
        self,
        state: RuntimeState | None = None,
        client: Any = None,
        *,
        policy_engine: PolicyEngine | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.state = state or RuntimeState()
        self.client = client
        self.policy_engine = policy_engine or PolicyEngine(PolicyConfig.from_env())
        self.audit_logger = audit_logger

    def queue_approved_print(self, request_id: str) -> dict[str, Any]:
        return self.queue_print_request(request_id)

    def queue_print_request(self, request_id: str) -> dict[str, Any]:
        if self.client is None or not hasattr(self.client, "queue_print"):
            raise TypeError("Bambuddy queue client is not configured")
        request, plan = self.state.load_queueable_request_plan(request_id)
        decision = self.policy_engine.evaluate(
            action="queue_print",
            plan=plan,
            user_id=str(request["user_id"]),
            chat_id=str(request["chat_id"]),
            printer_id=str(request["printer_id"]),
            confirmation_id=str(request["request_id"]),
            remote=_env_bool("PRINT_CONCIERGE_REMOTE_QUEUE", default=False),
            snapshot_id=str(plan.get("snapshot_id") or request.get("snapshot_id") or "")
            or None,
        )
        if not decision.allowed:
            self._record(
                "print_request.queue.denied",
                request=request,
                plan=plan,
                details={
                    "reasons": decision.reasons,
                    "risk_flags": decision.risk_flags,
                },
            )
            raise ValueError(
                "queue policy denied: " + "; ".join(decision.reasons or decision.risk_flags)
            )
        self._record(
            "print_request.queue.policy_allowed",
            request=request,
            plan=plan,
            details={"risk_flags": decision.risk_flags},
        )
        request, plan = self.state.claim_request_for_queue(request_id)
        self._record("print_request.queue.claimed", request=request, plan=plan)
        queue_payload = {
            **plan,
            "_print_concierge_confirmed": True,
            "approval": {
                "request_id": request["request_id"],
                "plan_hash": request["plan_hash"],
                "approved_at": request.get("approved_at"),
            },
        }
        try:
            result = dict(self.client.queue_print(queue_payload))
            if not result.get("job_id"):
                raise ValueError("queue response must include job_id")
        except Exception as exc:
            self.state.mark_request_failed(
                request_id=str(request["request_id"]),
                error=str(exc),
            )
            self._record(
                "print_request.queue.failed",
                request=request,
                plan=plan,
                details={"error": str(exc)},
            )
            raise
        job_id = str(result["job_id"])
        self.state.mark_request_queued(
            request_id=str(request["request_id"]),
            plan_hash=str(plan["plan_hash"]),
            job_id=job_id,
            queue_payload=queue_payload,
            queue_result=result,
        )
        self._record(
            "print_request.queue.queued",
            request=request,
            plan=plan,
            job_id=job_id,
            details={"queue_result": result},
        )
        return result

    def _record(
        self,
        event_type: str,
        *,
        request: Mapping[str, Any],
        plan: Mapping[str, Any],
        job_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if self.audit_logger is None:
            return
        payload = {
            "request_id": request.get("request_id"),
            "plan_hash": plan.get("plan_hash"),
            "printer_id": request.get("printer_id"),
            "file_hash": request.get("file_hash"),
            **dict(details or {}),
        }
        self.audit_logger.record(
            AuditEvent(
                event_type=event_type,
                actor_id=str(request.get("user_id") or ""),
                job_id=job_id or str(request.get("job_id") or ""),
                details=payload,
            )
        )


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
