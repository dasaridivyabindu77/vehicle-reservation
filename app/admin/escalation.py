"""Escalation service — the bridge between the first and second agents.

The reservation (first) agent finishes slot-filling and submits a completed
booking here; this service hands it to the administrator (second) agent to
notify the human, and records the request as ``pending_admin``. When the
administrator responds — via the dashboard, the admin CLI or an email reply —
the decision comes back through :meth:`decide`, which asks the admin agent to
interpret it and writes the result to the shared SQLite store. The user agent
then reads that status back to the customer.

    reservation agent ──submit()──▶ EscalationService ──escalate()──▶ admin agent ──▶ human
          ▲                               │                                            │
          └──────── decide() ◀────────────┴────────── administrator's reply ◀──────────┘
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from ..sql_store import DynamicDataStore, Reservation, STATUS_PENDING, STATUS_CONFIRMED
from .agent import AdminAgent, AdminDecision

logger = logging.getLogger(__name__)

# Stage 3: MCP server integration (optional dependency)
try:
    from mcp_server.client import MCPClient
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("MCP server client not available - Stage 3 file writing disabled")


@dataclass
class SubmitResult:
    reservation: Reservation
    message: str  # the approval request delivered to the administrator


class EscalationService:
    def __init__(
        self,
        sql: DynamicDataStore,
        agent: AdminAgent,
        mcp_client: Optional["MCPClient"] = None,
    ) -> None:
        self.sql = sql
        self.agent = agent
        # Stage 3: MCP client for writing confirmed reservations
        self.mcp_client = mcp_client
        if self.mcp_client and self.mcp_client.is_available():
            logger.info("MCP server is available for Stage 3 file writing")
        elif self.mcp_client:
            logger.warning("MCP server configured but not reachable")

    def submit(self, reservation_id: int) -> SubmitResult:
        """Hand a freshly created pending reservation to the administrator."""
        reservation = self.sql.get_reservation(reservation_id)
        if reservation is None:
            raise KeyError(f"reservation #{reservation_id} not found")
        message = self.agent.escalate(reservation.as_dict())
        logger.info("Escalated reservation #%s to administrator", reservation_id)
        return SubmitResult(reservation=reservation, message=message)

    def pending(self) -> List[Reservation]:
        return self.sql.pending_reservations()

    def recent(self, limit: int = 50) -> List[Reservation]:
        return self.sql.recent_reservations(limit)

    def get(self, reservation_id: int) -> Optional[Reservation]:
        return self.sql.get_reservation(reservation_id)

    def decide(
        self,
        reservation_id: int,
        raw_decision: str,
        reason: Optional[str] = None,
        decided_by: str = "admin",
    ) -> tuple[Reservation, AdminDecision]:
        """Apply the administrator's reply to a pending reservation.

        Returns the updated reservation and the interpreted decision. Raises
        ``KeyError`` if the reservation doesn't exist and ``ValueError`` if it
        has already been decided.

        Stage 3: If the decision is 'confirmed' and an MCP server is available,
        writes the reservation details to persistent storage.
        """
        reservation = self.sql.get_reservation(reservation_id)
        if reservation is None:
            raise KeyError(f"reservation #{reservation_id} not found")
        if reservation.status != STATUS_PENDING:
            raise ValueError(
                f"reservation #{reservation_id} is already {reservation.status}"
            )

        decision = self.agent.interpret_decision(raw_decision, reason=reason)
        updated = self.sql.set_decision(
            reservation_id, decision.status, decision.reason, decided_by=decided_by
        )
        assert updated is not None  # just written
        logger.info(
            "Reservation #%s %s by %s", reservation_id, decision.status, decided_by
        )

        # Stage 3: Write confirmed reservation to file via MCP server
        if decision.status == STATUS_CONFIRMED and self.mcp_client:
            try:
                result = self.mcp_client.write_confirmed_reservation(
                    reservation_id=updated.id,
                    first_name=updated.first_name,
                    last_name=updated.last_name,
                    car_number=updated.car_number,
                    start_ts=updated.start_ts,
                    end_ts=updated.end_ts,
                    approved_by=decided_by,
                    approval_time=updated.decided_at,
                )
                logger.info(
                    "Stage 3: Wrote confirmed reservation #%s to file: %s",
                    reservation_id,
                    result.get("file_path"),
                )
            except Exception as e:
                # Non-fatal: log the error but don't fail the decision
                logger.error(
                    "Stage 3: Failed to write reservation #%s to MCP server: %s",
                    reservation_id,
                    e,
                    exc_info=True,
                )

        return updated, decision
