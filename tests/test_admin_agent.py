"""Tests for the administrator agent (Stage 2 second agent)."""

import pytest

from app.admin.agent import AdminAgent, AdminDecision
from app.admin.channels import RecordingChannel
from app.config import Settings
from app.sql_store import STATUS_CONFIRMED, STATUS_REFUSED


@pytest.fixture
def offline_agent(settings):
    """An admin agent in offline mode (no LLM)."""
    return AdminAgent(settings, chat_model=None, channels=[RecordingChannel()])


@pytest.fixture
def sample_reservation():
    return {
        "id": 7,
        "full_name": "Ada Lovelace",
        "car_number": "AL1234",
        "start_ts": "2026-12-01T09:00",
        "end_ts": "2026-12-01T17:00",
        "created_at": "2026-11-12T10:00:00",
    }


def test_compose_template_offline(offline_agent, sample_reservation):
    msg = offline_agent.compose_request(sample_reservation)
    assert "Ada Lovelace" in msg
    assert "AL1234" in msg
    assert "#7" in msg
    assert "approve" in msg.lower() or "refuse" in msg.lower()


def test_escalate_delivers_through_channels(offline_agent, sample_reservation):
    msg = offline_agent.escalate(sample_reservation)
    assert msg
    # The agent has a RecordingChannel; check it was called.
    recorder = offline_agent.channels[0]
    assert len(recorder.sent) == 1
    assert recorder.sent[0]["reservation"]["id"] == 7


def test_interpret_decision_approve_keywords():
    agent = AdminAgent(Settings(dial_api_key=""), chat_model=None)
    decision = agent.interpret_decision("approve")
    assert decision.approved is True
    assert decision.status == STATUS_CONFIRMED


def test_interpret_decision_refuse_keywords():
    agent = AdminAgent(Settings(dial_api_key=""), chat_model=None)
    decision = agent.interpret_decision("refuse: lot is full")
    assert decision.approved is False
    assert decision.status == STATUS_REFUSED
    assert "full" in decision.reason.lower()


def test_interpret_decision_ambiguous_defaults_refuse():
    agent = AdminAgent(Settings(dial_api_key=""), chat_model=None)
    decision = agent.interpret_decision("maybe later")
    assert decision.approved is False  # ambiguous = refuse for safety


def test_interpret_decision_with_explicit_reason():
    agent = AdminAgent(Settings(dial_api_key=""), chat_model=None)
    decision = agent.interpret_decision("yes", reason="All good!")
    assert decision.approved is True
    assert decision.reason == "All good!"
