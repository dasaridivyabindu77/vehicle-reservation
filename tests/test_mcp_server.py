"""Tests for Stage 3 MCP server and client integration."""

import os
from pathlib import Path
from datetime import datetime, timezone

import pytest

# Ensure mcp_server can be imported
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.server import app, RESERVATIONS_FILE
from mcp_server.client import MCPClient
from fastapi.testclient import TestClient


@pytest.fixture
def test_file(tmp_path):
    """Use a temporary file for testing."""
    test_file = tmp_path / "test_reservations.txt"
    original_file = RESERVATIONS_FILE

    # Monkey-patch the RESERVATIONS_FILE
    import mcp_server.server as server_module
    server_module.RESERVATIONS_FILE = test_file

    yield test_file

    # Restore original
    server_module.RESERVATIONS_FILE = original_file

    # Clean up
    if test_file.exists():
        test_file.unlink()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mcp_client():
    """MCP client without authentication for testing."""
    return MCPClient(token="")


def test_health_check(client):
    """Test MCP server health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "citypark-mcp-server"
    assert "file_path" in data


def test_list_tools(client):
    """Test MCP tools listing."""
    response = client.get("/tools/list")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) == 2

    tool_names = [t["name"] for t in data["tools"]]
    assert "write_confirmed_reservation" in tool_names
    assert "read_confirmed_reservations" in tool_names


def test_write_confirmed_reservation(client, test_file):
    """Test writing a confirmed reservation."""
    payload = {
        "reservation_id": 1,
        "first_name": "John",
        "last_name": "Doe",
        "car_number": "ABC-123",
        "start_ts": "2026-11-15T10:00:00",
        "end_ts": "2026-11-15T18:00:00",
        "approved_by": "admin",
        "approval_time": "2026-11-12T16:00:00Z",
    }

    response = client.post("/tools/call/write_confirmed_reservation", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["entry_count"] == 1
    assert "file_path" in data

    # Verify file content
    content = test_file.read_text()
    assert "John Doe" in content
    assert "ABC-123" in content
    assert "2026-11-15T10:00:00 to 2026-11-15T18:00:00" in content
    assert "2026-11-12T16:00:00Z" in content


def test_write_multiple_reservations(client, test_file):
    """Test writing multiple reservations."""
    reservations = [
        {
            "reservation_id": 1,
            "first_name": "Alice",
            "last_name": "Smith",
            "car_number": "XYZ-789",
            "start_ts": "2026-11-15T10:00:00",
            "end_ts": "2026-11-15T18:00:00",
        },
        {
            "reservation_id": 2,
            "first_name": "Bob",
            "last_name": "Johnson",
            "car_number": "DEF-456",
            "start_ts": "2026-11-16T09:00:00",
            "end_ts": "2026-11-16T17:00:00",
        },
    ]

    for res in reservations:
        response = client.post("/tools/call/write_confirmed_reservation", json=res)
        assert response.status_code == 200

    # Verify both are in the file
    content = test_file.read_text()
    assert "Alice Smith" in content
    assert "Bob Johnson" in content
    assert "XYZ-789" in content
    assert "DEF-456" in content

    # Count lines
    lines = [line for line in content.split("\n") if line.strip()]
    assert len(lines) == 2


def test_read_confirmed_reservations_empty(client, test_file):
    """Test reading when no reservations exist."""
    response = client.post("/tools/call/read_confirmed_reservations", json={})
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["count"] == 0
    assert len(data["entries"]) == 0


def test_read_confirmed_reservations(client, test_file):
    """Test reading confirmed reservations."""
    # Write some reservations first
    payload = {
        "reservation_id": 1,
        "first_name": "Charlie",
        "last_name": "Brown",
        "car_number": "GHI-321",
        "start_ts": "2026-11-20T10:00:00",
        "end_ts": "2026-11-20T18:00:00",
    }

    client.post("/tools/call/write_confirmed_reservation", json=payload)

    # Read them back
    response = client.post("/tools/call/read_confirmed_reservations", json={})
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["count"] == 1
    assert len(data["entries"]) == 1
    assert "Charlie Brown" in data["entries"][0]


def test_reservations_summary(client, test_file):
    """Test the summary endpoint."""
    # Write a reservation
    payload = {
        "reservation_id": 5,
        "first_name": "Diana",
        "last_name": "Prince",
        "car_number": "WW-1984",
        "start_ts": "2026-11-25T10:00:00",
        "end_ts": "2026-11-25T18:00:00",
    }

    client.post("/tools/call/write_confirmed_reservation", json=payload)

    response = client.get("/reservations")
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 1
    assert data["file_exists"] is True
    assert len(data["entries"]) == 1


def test_authentication_with_token():
    """Test that authentication works when token is configured."""
    # Set a token
    os.environ["MCP_SERVER_TOKEN"] = "test-secret-token"

    # Reload the module to pick up the new token
    import importlib
    import mcp_server.server as server_module
    importlib.reload(server_module)

    client = TestClient(server_module.app)

    # Request without token should fail
    response = client.get("/tools/list")
    assert response.status_code == 401

    # Request with correct token should succeed
    response = client.get("/tools/list", headers={"X-MCP-Token": "test-secret-token"})
    assert response.status_code == 200

    # Clean up
    del os.environ["MCP_SERVER_TOKEN"]
    importlib.reload(server_module)


def test_format_compliance(client, test_file):
    """Test that the file format matches Stage 3 requirements."""
    # Required format: Name | Car Number | Reservation Period | Approval Time
    payload = {
        "reservation_id": 99,
        "first_name": "Test",
        "last_name": "User",
        "car_number": "TEST-001",
        "start_ts": "2026-11-30T14:00:00",
        "end_ts": "2026-11-30T16:00:00",
        "approval_time": "2026-11-12T20:00:00Z",
    }

    response = client.post("/tools/call/write_confirmed_reservation", json=payload)
    assert response.status_code == 200

    content = test_file.read_text().strip()
    parts = content.split(" | ")

    # Verify format: Name | Car Number | Reservation Period | Approval Time
    assert len(parts) == 4
    assert parts[0] == "Test User"
    assert parts[1] == "TEST-001"
    assert "2026-11-30T14:00:00 to 2026-11-30T16:00:00" in parts[2]
    assert "2026-11-12T20:00:00Z" in parts[3]


def test_mcp_client_health_check():
    """Test MCP client health check."""
    # This will fail if server is not running, which is expected in tests
    client = MCPClient(base_url="http://127.0.0.1:8001", token="")

    # is_available should handle connection errors gracefully
    available = client.is_available()
    # In tests, the server isn't running, so this should be False
    # But we're testing the method doesn't crash
    assert isinstance(available, bool)


def test_mcp_client_write_operation(monkeypatch):
    """Test MCP client write operation with mocked httpx."""
    import httpx

    class MockResponse:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "success": True,
                "message": "Reservation written",
                "file_path": "/tmp/test.txt",
                "entry_count": 1,
            }

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json, headers):
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", lambda timeout: MockClient())

    client = MCPClient(token="test-token")
    result = client.write_confirmed_reservation(
        reservation_id=1,
        first_name="John",
        last_name="Doe",
        car_number="ABC-123",
        start_ts="2026-11-15T10:00:00",
        end_ts="2026-11-15T18:00:00",
    )

    assert result["success"] is True
    assert result["entry_count"] == 1
