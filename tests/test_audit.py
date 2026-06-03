import json

from print_concierge.audit import AuditLogger, redact_secrets
from print_concierge.models import AuditEvent


def test_redaction_recurses_through_sensitive_fields_and_values():
    payload = {
        "api_key": "sk-live-secret",
        "headers": {"authorization": "Bearer abc.def.ghi"},
        "nested": [
            {
                "camera_url": "rtsp://user:pass@camera.local/live",
                "serial_number": "SN123456",
                "confirmation_token": "pc_123456",
                "note": "Access code 123456 should be hidden",
            }
        ],
    }

    redacted = redact_secrets(payload)
    encoded = json.dumps(redacted)

    assert "sk-live-secret" not in encoded
    assert "abc.def.ghi" not in encoded
    assert "rtsp://user:pass@camera.local/live" not in encoded
    assert "SN123456" not in encoded
    assert "pc_123456" not in encoded
    assert "123456" not in encoded
    assert "[REDACTED]" in encoded


def test_audit_logger_writes_append_only_redacted_jsonl(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger.jsonl(path)

    logger.record(
        AuditEvent(
            event_type="confirmation.created",
            actor_id="user-1",
            job_id="job-1",
            details={"confirmation_token": "pc_secret", "printer": {"serial": "SN123"}},
        )
    )
    logger.record(
        AuditEvent(
            event_type="confirmation.verified",
            actor_id="user-1",
            job_id="job-1",
            details={"result": "ok"},
        )
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["schema_version"] == 1 for line in lines)
    assert "pc_secret" not in "\n".join(lines)
    assert "SN123" not in "\n".join(lines)


def test_memory_logger_keeps_redacted_events_for_tests():
    logger = AuditLogger.memory()

    logger.record(
        AuditEvent(
            event_type="token.generated",
            actor_id="user-1",
            details={"token": "pc_plaintext"},
        )
    )

    assert len(logger.events) == 1
    assert "pc_plaintext" not in json.dumps(logger.events[0])
