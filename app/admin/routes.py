"""FastAPI routes for the administrator dashboard and decision API.

**GET /admin** — the web dashboard (HTML page) listing pending reservations with
approve/refuse buttons. Uses the same dark theme as the main chat UI.

**GET /admin/api/reservations** — JSON list of pending + recent reservations.

**POST /admin/api/reservations/{id}/decision** — apply an approve/refuse decision.
  ``{decision: "approve"|"refuse", reason?: str}``

Reservation data and decision endpoints require the configured administrator
token in the ``X-Admin-Token`` header. They fail closed when no token is set.
"""

from __future__ import annotations

import hmac
import logging
from pathlib import Path
from typing import Optional

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..config import Settings

if TYPE_CHECKING:
    from ..admin.escalation import EscalationService

logger = logging.getLogger(__name__)

router = APIRouter()

# The dashboard HTML is in this directory; loaded at import time.
_DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


# --- Dependency placeholders (overridden by the FastAPI app) -----------------
def get_escalation_dep():
    """Placeholder; the app overrides this to return the real escalation service."""
    raise NotImplementedError("escalation dependency not configured")


def get_settings_dep() -> Settings:
    """Placeholder; the app overrides this to return the real settings."""
    raise NotImplementedError("settings dependency not configured")


def require_admin_access(
    settings: Settings = Depends(get_settings_dep),
    token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Require a configured administrator token for protected endpoints."""
    if not settings.admin_token:
        raise HTTPException(
            status_code=503,
            detail="admin access is disabled; configure ADMIN_TOKEN",
        )
    if token is None or not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=403, detail="invalid or missing admin token")


class DecisionRequest(BaseModel):
    decision: str  # "approve" or "refuse"
    reason: Optional[str] = None


class DecisionReply(BaseModel):
    success: bool
    reservation_id: int
    status: str
    reason: str


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard() -> str:
    """The administrator dashboard — a single-page HTML UI."""
    return _DASHBOARD_HTML


@router.get("/admin/api/reservations")
def list_reservations(
    limit: int = Query(default=50, ge=1, le=200),
    escalation: "EscalationService" = Depends(get_escalation_dep),
    _: None = Depends(require_admin_access),
):
    """Pending reservations (top) + recent decided ones (up to ``limit`` total)."""
    pending = escalation.pending()
    recent = escalation.recent(limit)
    return {
        "pending": [r.as_dict() for r in pending],
        "recent": [r.as_dict() for r in recent if r.id not in {p.id for p in pending}],
    }


@router.post("/admin/api/reservations/{reservation_id}/decision", response_model=DecisionReply)
def decide(
    reservation_id: int,
    req: DecisionRequest,
    escalation: "EscalationService" = Depends(get_escalation_dep),
    _: None = Depends(require_admin_access),
):
    """Apply the administrator's confirm/refuse decision."""
    decision_lower = req.decision.strip().lower()
    if decision_lower not in {"approve", "refuse", "confirm", "reject", "decline"}:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'refuse'")

    try:
        updated, parsed = escalation.decide(
            reservation_id, req.decision, reason=req.reason, decided_by="admin-dashboard"
        )
        return DecisionReply(
            success=True,
            reservation_id=updated.id,
            status=updated.status,
            reason=parsed.reason,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"reservation #{reservation_id} not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
