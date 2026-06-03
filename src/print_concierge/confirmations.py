from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, Optional
from uuid import uuid4

from .models import ConfirmationChallenge


class ConfirmationStatus(str, Enum):
    VERIFIED = "verified"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    ALREADY_USED = "already_used"
    BINDING_MISMATCH = "binding_mismatch"


@dataclass(frozen=True)
class IssuedChallenge:
    challenge_id: str
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class ConfirmationResult:
    status: ConfirmationStatus
    challenge_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class _StoredChallenge:
    challenge: ConfirmationChallenge
    expires_at: datetime
    used_at: Optional[datetime] = None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ConfirmationService:
    def __init__(
        self,
        *,
        ttl: timedelta = timedelta(minutes=5),
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.ttl = ttl
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._challenges_by_hash: Dict[str, _StoredChallenge] = {}

    def __repr__(self) -> str:
        return f"ConfirmationService(challenges={len(self._challenges_by_hash)})"

    def create_challenge(
        self,
        *,
        user_id: str,
        chat_id: str,
        job_id: str,
        file_hash: str,
        printer_id: str,
        material_profile: str,
        plan_hash: str,
    ) -> IssuedChallenge:
        issued_at = self._now()
        expires_at = issued_at + self.ttl
        token = f"pc_{secrets.token_urlsafe(12)}"
        challenge_id = uuid4().hex
        challenge = ConfirmationChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            chat_id=chat_id,
            job_id=job_id,
            file_hash=file_hash,
            printer_id=printer_id,
            material_profile=material_profile,
            plan_hash=plan_hash,
            token_hash=_hash_token(token),
            expires_at=_iso(expires_at),
            created_at=_iso(issued_at),
        )
        self._challenges_by_hash[challenge.token_hash] = _StoredChallenge(
            challenge=challenge,
            expires_at=expires_at,
        )
        return IssuedChallenge(challenge_id=challenge_id, token=token, expires_at=expires_at)

    def verify(
        self,
        *,
        token: str,
        user_id: str,
        chat_id: str,
        job_id: str,
        file_hash: str,
        printer_id: str,
        material_profile: str,
        plan_hash: str,
    ) -> ConfirmationResult:
        token_hash = _hash_token(token)
        stored = self._challenges_by_hash.get(token_hash)
        if stored is None:
            return ConfirmationResult(ConfirmationStatus.NOT_FOUND, error="token not found")

        challenge = stored.challenge
        if stored.used_at is not None:
            return ConfirmationResult(
                ConfirmationStatus.ALREADY_USED,
                challenge_id=challenge.challenge_id,
                error="token already used",
            )
        if self._now() > stored.expires_at:
            return ConfirmationResult(
                ConfirmationStatus.EXPIRED,
                challenge_id=challenge.challenge_id,
                error="token expired",
            )

        expected = {
            "user_id": user_id,
            "chat_id": chat_id,
            "job_id": job_id,
            "file_hash": file_hash,
            "printer_id": printer_id,
            "material_profile": material_profile,
            "plan_hash": plan_hash,
        }
        actual = {
            "user_id": challenge.user_id,
            "chat_id": challenge.chat_id,
            "job_id": challenge.job_id,
            "file_hash": challenge.file_hash,
            "printer_id": challenge.printer_id,
            "material_profile": challenge.material_profile,
            "plan_hash": challenge.plan_hash,
        }
        if expected != actual:
            return ConfirmationResult(
                ConfirmationStatus.BINDING_MISMATCH,
                challenge_id=challenge.challenge_id,
                error="token binding mismatch",
            )

        stored.used_at = self._now()
        return ConfirmationResult(ConfirmationStatus.VERIFIED, challenge_id=challenge.challenge_id)
