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

from ..sql_store import DynamicDataStore, Reservation, STATUS_PENDING
from .agent import AdminAgent, AdminDecision

logger = logging.getLogger(__name__)


@dataclass
class SubmitResult:
    reservation: Reservation
    message: str  # the approval request delivered to the administrator


class EscalationService:
    def __init__(self, sql: DynamicDataStore, agent: AdminAgent) -> None:
        self.sql = sql
        self.agent = agent

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
        return updated, decision
