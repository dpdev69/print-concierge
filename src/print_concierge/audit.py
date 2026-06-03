from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .models import AuditEvent


REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "access_code",
    "accesscode",
    "serial",
    "camera_url",
    "confirmation_token",
    "token",
)
SENSITIVE_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
    re.compile(r"\bpc_[A-Za-z0-9_-]+\b"),
    re.compile(r"rtsp://[^\s\"']+", re.IGNORECASE),
    re.compile(r"\baccess code\s+\d+\b", re.IGNORECASE),
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _redact_string(value: str) -> str:
    redacted = value
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            result[text_key] = REDACTED if _is_sensitive_key(text_key) else redact_secrets(item)
        return result
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


class AuditLogger:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self.events: List[Dict[str, Any]] = []

    @classmethod
    def jsonl(cls, path: Path) -> "AuditLogger":
        return cls(Path(path))

    @classmethod
    def memory(cls) -> "AuditLogger":
        return cls()

    @classmethod
    def from_env(cls) -> "AuditLogger | None":
        configured = os.environ.get("PRINT_CONCIERGE_AUDIT_LOG")
        if configured and configured.strip().lower() in {"0", "false", "no", "off"}:
            return None
        if not configured:
            state_db = Path(
                os.environ.get("PRINT_CONCIERGE_STATE_DB", "~/.print-concierge/state.sqlite3")
            ).expanduser()
            return cls.jsonl(state_db.parent / "audit.jsonl")
        return cls.jsonl(Path(configured).expanduser())

    def record(self, event: AuditEvent) -> Dict[str, Any]:
        payload = redact_secrets(event.to_dict())
        if self.path is None:
            self.events.append(payload)
            return payload

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.write("\n")
        self.path.chmod(0o600)
        return payload
