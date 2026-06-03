from datetime import datetime, timedelta, timezone

from print_concierge.confirmations import ConfirmationService, ConfirmationStatus


def test_confirmation_token_verifies_once_and_stores_only_hashes():
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    service = ConfirmationService(now=lambda: now)

    challenge = service.create_challenge(
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )

    assert challenge.token.startswith("pc_")
    assert challenge.token not in repr(service)

    result = service.verify(
        token=challenge.token,
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )
    assert result.status is ConfirmationStatus.VERIFIED
    assert result.challenge_id == challenge.challenge_id

    reused = service.verify(
        token=challenge.token,
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )
    assert reused.status is ConfirmationStatus.ALREADY_USED


def test_confirmation_rejects_expired_token_without_consuming_it():
    clock = {"now": datetime(2026, 6, 3, tzinfo=timezone.utc)}
    service = ConfirmationService(now=lambda: clock["now"], ttl=timedelta(seconds=30))
    challenge = service.create_challenge(
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )

    clock["now"] = clock["now"] + timedelta(seconds=31)
    expired = service.verify(
        token=challenge.token,
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )

    assert expired.status is ConfirmationStatus.EXPIRED


def test_confirmation_rejects_wrong_binding_without_side_effects():
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    service = ConfirmationService(now=lambda: now)
    challenge = service.create_challenge(
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )

    wrong_user = service.verify(
        token=challenge.token,
        user_id="user-2",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )
    assert wrong_user.status is ConfirmationStatus.BINDING_MISMATCH

    wrong_job = service.verify(
        token=challenge.token,
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-2",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )
    assert wrong_job.status is ConfirmationStatus.BINDING_MISMATCH

    wrong_plan = service.verify(
        token=challenge.token,
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:other",
    )
    assert wrong_plan.status is ConfirmationStatus.BINDING_MISMATCH

    correct = service.verify(
        token=challenge.token,
        user_id="user-1",
        chat_id="chat-1",
        job_id="job-1",
        file_hash="sha256:file",
        printer_id="printer-1",
        material_profile="PLA Basic",
        plan_hash="sha256:plan",
    )
    assert correct.status is ConfirmationStatus.VERIFIED
