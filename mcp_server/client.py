"""MCP Server client for integrating with the escalation service.

This client provides a clean interface for the administrator agent to call
MCP server tools when a reservation is confirmed.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for interacting with the CityPark MCP server."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        token: Optional[str] = None,
        timeout: float = 10.0,
    ):
        """Initialize MCP client.

        Args:
            base_url: Base URL of the MCP server
            token: Authentication token (X-MCP-Token header)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.token = token or os.getenv("MCP_SERVER_TOKEN", "")
        self.timeout = timeout
        self.headers = {}
        if self.token:
            self.headers["X-MCP-Token"] = self.token

    def write_confirmed_reservation(
        self,
        reservation_id: int,
        first_name: str,
        last_name: str,
        car_number: str,
        start_ts: str,
        end_ts: str,
        approved_by: str = "admin",
        approval_time: Optional[str] = None,
    ) -> dict:
        """Write a confirmed reservation to persistent storage via MCP server.

        Args:
            reservation_id: Unique reservation ID
            first_name: Customer first name
            last_name: Customer last name
            car_number: Vehicle license plate
            start_ts: Reservation start timestamp
            end_ts: Reservation end timestamp
            approved_by: Administrator who approved
            approval_time: ISO format approval timestamp

        Returns:
            dict with success status and details

        Raises:
            httpx.HTTPError: If the request fails
        """
        url = f"{self.base_url}/tools/call/write_confirmed_reservation"
        payload = {
            "reservation_id": reservation_id,
            "first_name": first_name,
            "last_name": last_name,
            "car_number": car_number,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "approved_by": approved_by,
        }
        if approval_time:
            payload["approval_time"] = approval_time

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                logger.info(
                    "MCP server confirmed write for reservation #%s", reservation_id
                )
                return result
        except httpx.HTTPError as e:
            logger.error(
                "Failed to write reservation #%s to MCP server: %s",
                reservation_id,
                e,
                exc_info=True,
            )
            raise

    def read_confirmed_reservations(self) -> dict:
        """Read all confirmed reservations from storage.

        Returns:
            dict with list of entries and count
        """
        url = f"{self.base_url}/tools/call/read_confirmed_reservations"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json={}, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error("Failed to read reservations from MCP server: %s", e)
            raise

    def health_check(self) -> dict:
        """Check if the MCP server is healthy.

        Returns:
            dict with health status
        """
        url = f"{self.base_url}/health"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error("MCP server health check failed: %s", e)
            raise

    def is_available(self) -> bool:
        """Check if the MCP server is available.

        Returns:
            True if server is reachable and healthy, False otherwise
        """
        try:
            health = self.health_check()
            return health.get("status") == "healthy"
        except Exception:
            return False
