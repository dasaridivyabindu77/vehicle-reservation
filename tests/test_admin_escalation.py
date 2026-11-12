"""Tests for the escalation service (bridge between the two agents)."""

import pytest

from app.admin.agent import AdminAgent
from app.admin.channels import RecordingChannel
from app.admin.escalation import EscalationService
from app.sql_store import STATUS_CONFIRMED, STATUS_PENDING, STATUS_REFUSED


@pytest.fixture
def escalation(settings):
    from app.sql_store import DynamicDataStore

    sql = DynamicDataStore(settings.sqlite_path)
    sql.seed()
    agent = AdminAgent(settings, chat_model=None, channels=[RecordingChannel()])
    service = EscalationService(sql, agent)
    yield service
    sql.close()


def test_submit_escalates_pending_reservation(escalation):
    rid = escalation.sql.create_reservation(
        "Grace", "Hopper", "GH2026", "2026-12-10T08:00", "2026-12-10T18:00"
    )
    result = escalation.submit(rid)
    assert result.reservation.id == rid
    assert result.reservation.status == STATUS_PENDING
    assert result.message  # the composed approval request
    # The agent has a RecordingChannel; confirm it received the escalation.
    recorder = escalation.agent.channels[0]
    assert len(recorder.sent) == 1


def test_pending_lists_only_pending(escalation):
    escalation.sql.create_reservation(
        "Ada", "Lovelace", "AL1234", "2026-12-01T09:00", "2026-12-01T17:00"
    )
    rid2 = escalation.sql.create_reservation(
        "Alan", "Turing", "AT1912", "2026-12-02T09:00", "2026-12-02T17:00"
    )
    escalation.sql.set_decision(rid2, STATUS_CONFIRMED, "ok")
    pending = escalation.pending()
    assert len(pending) == 1
    assert pending[0].first_name == "Ada"


def test_decide_approves_reservation(escalation):
    rid = escalation.sql.create_reservation(
        "Test", "User", "TU1234", "2026-12-05T10:00", "2026-12-05T16:00"
    )
    updated, decision = escalation.decide(rid, "approve", decided_by="test")
    assert updated.status == STATUS_CONFIRMED
    assert decision.approved is True
    assert updated.decided_by == "test"


def test_decide_refuses_reservation(escalation):
    rid = escalation.sql.create_reservation(
        "Test", "User", "TU1234", "2026-12-05T10:00", "2026-12-05T16:00"
    )
    updated, decision = escalation.decide(rid, "refuse: no space", decided_by="admin")
    assert updated.status == STATUS_REFUSED
    assert decision.approved is False
    assert "space" in updated.admin_reason.lower()


def test_decide_raises_on_missing_reservation(escalation):
    with pytest.raises(KeyError):
        escalation.decide(99999, "approve")


def test_decide_raises_on_already_decided(escalation):
    rid = escalation.sql.create_reservation(
        "Test", "User", "TU1234", "2026-12-05T10:00", "2026-12-05T16:00"
    )
    escalation.decide(rid, "approve")
    with pytest.raises(ValueError, match="already"):
        escalation.decide(rid, "refuse")
