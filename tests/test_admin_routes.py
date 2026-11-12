"""Tests for the admin dashboard + REST API."""

from fastapi.testclient import TestClient

from app.admin.agent import AdminAgent
from app.admin.channels import RecordingChannel
from app.admin.escalation import EscalationService
from app.chatbot import Chatbot
from app.config import Settings
from app.sql_store import DynamicDataStore
from app.web import server


def _client_with_admin(tmp_path):
    from app.admin import routes as admin_routes

    settings = Settings(dial_api_key="", sqlite_path=str(tmp_path / "admin.db"))
    sql = DynamicDataStore(settings.sqlite_path)
    sql.seed()
    agent = AdminAgent(settings, chat_model=None, channels=[RecordingChannel()])
    escalation = EscalationService(sql, agent)
    bot = Chatbot(settings=settings, prefer_weaviate=False, escalation=escalation)
    server._bot = bot

    # Override the admin route dependencies for this test.
    server.app.dependency_overrides[admin_routes.get_escalation_dep] = lambda: escalation
    server.app.dependency_overrides[admin_routes.get_settings_dep] = lambda: settings

    client = TestClient(server.app)
    return client, bot, escalation


def test_admin_dashboard_serves_html(tmp_path):
    client, bot, _ = _client_with_admin(tmp_path)
    try:
        r = client.get("/admin")
        assert r.status_code == 200
        assert "CityPark Admin Dashboard" in r.text
    finally:
        bot.close()
        server._bot = None


def test_list_reservations_empty(tmp_path):
    client, bot, _ = _client_with_admin(tmp_path)
    try:
        r = client.get("/admin/api/reservations")
        assert r.status_code == 200
        body = r.json()
        assert body["pending"] == []
        assert body["recent"] == []
    finally:
        bot.close()
        server._bot = None


def test_list_reservations_with_pending(tmp_path):
    client, bot, escalation = _client_with_admin(tmp_path)
    try:
        rid = escalation.sql.create_reservation(
            "Ada", "Lovelace", "AL1234", "2026-12-01T09:00", "2026-12-01T17:00"
        )
        r = client.get("/admin/api/reservations")
        assert r.status_code == 200
        body = r.json()
        assert len(body["pending"]) == 1
        assert body["pending"][0]["id"] == rid
        assert body["pending"][0]["full_name"] == "Ada Lovelace"
    finally:
        bot.close()
        server._bot = None


def test_decide_approve_reservation(tmp_path):
    client, bot, escalation = _client_with_admin(tmp_path)
    try:
        rid = escalation.sql.create_reservation(
            "Test", "User", "TU1234", "2026-12-05T10:00", "2026-12-05T16:00"
        )
        r = client.post(
            f"/admin/api/reservations/{rid}/decision",
            json={"decision": "approve", "reason": "All good!"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["status"] == "confirmed"
        assert "good" in body["reason"].lower()
    finally:
        bot.close()
        server._bot = None


def test_decide_refuse_reservation(tmp_path):
    client, bot, escalation = _client_with_admin(tmp_path)
    try:
        rid = escalation.sql.create_reservation(
            "Test", "User", "TU1234", "2026-12-05T10:00", "2026-12-05T16:00"
        )
        r = client.post(
            f"/admin/api/reservations/{rid}/decision",
            json={"decision": "refuse", "reason": "Lot is full"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["status"] == "refused"
    finally:
        bot.close()
        server._bot = None


def test_decide_missing_reservation_404(tmp_path):
    client, bot, _ = _client_with_admin(tmp_path)
    try:
        r = client.post("/admin/api/reservations/99999/decision", json={"decision": "approve"})
        assert r.status_code == 404
    finally:
        bot.close()
        server._bot = None


def test_decide_already_decided_409(tmp_path):
    client, bot, escalation = _client_with_admin(tmp_path)
    try:
        rid = escalation.sql.create_reservation(
            "Test", "User", "TU1234", "2026-12-05T10:00", "2026-12-05T16:00"
        )
        client.post(f"/admin/api/reservations/{rid}/decision", json={"decision": "approve"})
        r = client.post(f"/admin/api/reservations/{rid}/decision", json={"decision": "refuse"})
        assert r.status_code == 409
    finally:
        bot.close()
        server._bot = None
