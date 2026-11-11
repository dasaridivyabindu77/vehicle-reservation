"""Interactive reservation collection (slot filling).

Collects the required booking details one at a time, validating each: first
name, last name, car (licence plate) number, and the reservation period
(start and end). When every slot is filled the flow produces a confirmation
summary and marks the booking ``pending_admin`` — the hand-off point for the
Stage-later human-in-the-loop confirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from dateutil import parser as dateparser

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,39}$")
PLATE_RE = re.compile(r"^[A-Z0-9]{4,10}$")

SLOTS: List[str] = ["first_name", "last_name", "car_number", "start", "end"]

PROMPTS: Dict[str, str] = {
    "first_name": "Let's book your spot. What's your first name?",
    "last_name": "Thanks! And your last name?",
    "car_number": "What's your car's licence plate number?",
    "start": "When should the reservation start? (e.g. 2026-11-20 09:00)",
    "end": "And when should it end? (e.g. 2026-11-20 18:00)",
}


@dataclass
class ReservationSession:
    data: Dict[str, str] = field(default_factory=dict)
    active: bool = False
    completed: bool = False
    reservation_id: Optional[int] = None

    def next_slot(self) -> Optional[str]:
        for slot in SLOTS:
            if slot not in self.data:
                return slot
        return None

    def is_complete(self) -> bool:
        return self.next_slot() is None


@dataclass
class IngestResult:
    reply: str
    done: bool = False
    reservation_ready: bool = False


def _validate(slot: str, raw: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(value, error)``. Exactly one is non-None."""
    text = raw.strip()
    if not text:
        return None, "I didn't catch that — could you type it again?"

    if slot in ("first_name", "last_name"):
        if not NAME_RE.match(text):
            return None, "That doesn't look like a valid name. Please use letters only."
        return text.title(), None

    if slot == "car_number":
        normalized = text.upper().replace(" ", "").replace("-", "")
        if not PLATE_RE.match(normalized):
            return None, (
                "A licence plate should be 4-10 letters/numbers. "
                "Please re-enter it (e.g. ABC1234)."
            )
        return normalized, None

    if slot in ("start", "end"):
        try:
            dt = dateparser.parse(text)
        except (ValueError, OverflowError):
            dt = None
        if dt is None:
            return None, "I couldn't read that date/time. Try e.g. 2026-11-20 09:00."
        if dt < datetime.now():
            return None, "That time is in the past. Please pick a future date/time."
        return dt.isoformat(timespec="minutes"), None

    return text, None  # pragma: no cover - unreachable


def start_session() -> ReservationSession:
    session = ReservationSession(active=True)
    return session


def first_prompt() -> str:
    return PROMPTS["first_name"]


def ingest(session: ReservationSession, user_text: str, store=None) -> IngestResult:
    """Feed one user message into the active reservation flow."""
    slot = session.next_slot()
    if slot is None:
        return IngestResult(reply="Your reservation is already complete.", done=True)

    value, error = _validate(slot, user_text)
    if error:
        return IngestResult(reply=error)

    session.data[slot] = value  # type: ignore[assignment]

    # Cross-field validation: end must be after start.
    if slot == "end":
        start = datetime.fromisoformat(session.data["start"])
        end = datetime.fromisoformat(session.data["end"])
        if end <= start:
            del session.data["end"]
            return IngestResult(reply="The end time must be after the start time. Please re-enter it.")

    next_slot = session.next_slot()
    if next_slot is not None:
        return IngestResult(reply=PROMPTS[next_slot])

    # All slots filled — finalise.
    session.completed = True
    session.active = False
    if store is not None:
        session.reservation_id = store.create_reservation(
            first_name=session.data["first_name"],
            last_name=session.data["last_name"],
            car_number=session.data["car_number"],
            start_ts=session.data["start"],
            end_ts=session.data["end"],
        )
    return IngestResult(reply=confirmation(session), done=True, reservation_ready=True)


def confirmation(session: ReservationSession) -> str:
    d = session.data
    ref = f" Your reference is #{session.reservation_id}." if session.reservation_id else ""
    return (
        "Here's your reservation request:\n"
        f"  Name:  {d['first_name']} {d['last_name']}\n"
        f"  Plate: {d['car_number']}\n"
        f"  From:  {d['start']}\n"
        f"  To:    {d['end']}\n"
        f"Status: pending administrator confirmation.{ref}\n"
        "An administrator will review and confirm it shortly."
    )
