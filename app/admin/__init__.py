"""Stage 2 — human-in-the-loop administrator approval.

This package holds the *second* agent of the system: the administrator agent
(:mod:`app.admin.agent`). Where the Stage 1 chatbot talks to the **user**, this
agent talks to the **human administrator** — it composes a reservation approval
request, delivers it through one or more channels (:mod:`app.admin.channels`:
dashboard/REST, terminal CLI, optional email), and interprets the
administrator's free-text confirm/refuse reply back into a structured decision.

:class:`~app.admin.escalation.EscalationService` is the bridge between the two
agents: the reservation (first) agent submits a completed booking to it, and the
decision flows back through the shared SQLite store to the user.
"""

from .agent import AdminAgent, AdminDecision
from .channels import AdminChannel, EmailChannel, LogChannel, RecordingChannel
from .escalation import EscalationService

__all__ = [
    "AdminAgent",
    "AdminDecision",
    "AdminChannel",
    "EmailChannel",
    "LogChannel",
    "RecordingChannel",
    "EscalationService",
]
