"""Delivery channels — how the administrator *receives* an approval request.

Each channel takes a reservation and a human-readable message composed by the
admin agent and delivers it somewhere the administrator will see it. The
dashboard and the admin CLI read pending requests straight from SQLite, so they
need no channel object; these channels cover the *push* notifications:

* :class:`LogChannel` — always on; writes the request to the application log.
* :class:`EmailChannel` — optional SMTP email, active only when SMTP + an admin
  address are configured. Never raises: a delivery failure is logged, not fatal.
* :class:`RecordingChannel` — keeps sent messages in memory (used by tests and
  the ``/admin`` notification feed).

A channel must never break a chat turn, so delivery errors are swallowed and
logged rather than propagated.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import List, Protocol, runtime_checkable

from ..config import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class AdminChannel(Protocol):
    """Anything that can deliver an approval request to the administrator."""

    name: str

    def send(self, reservation: dict, message: str) -> bool:
        """Deliver ``message`` about ``reservation``. Return True on success."""
        ...


class LogChannel:
    """Baseline channel: record the escalation in the application log."""

    name = "log"

    def send(self, reservation: dict, message: str) -> bool:
        logger.info(
            "Admin approval requested for reservation #%s (%s):\n%s",
            reservation.get("id"),
            reservation.get("full_name"),
            message,
        )
        return True


class RecordingChannel:
    """In-memory channel; keeps every delivered notification for inspection."""

    name = "recording"

    def __init__(self) -> None:
        self.sent: List[dict] = []

    def send(self, reservation: dict, message: str) -> bool:
        self.sent.append({"reservation": reservation, "message": message})
        return True


class EmailChannel:
    """Optional SMTP email channel (``e.g. via email server`` from the spec).

    Only delivers when :pyattr:`Settings.email_configured`. All SMTP errors are
    caught and logged so a flaky mail server can never crash a reservation.
    """

    name = "email"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.email_configured

    def send(self, reservation: dict, message: str) -> bool:
        if not self.enabled:
            logger.debug("EmailChannel skipped (SMTP/admin_email not configured)")
            return False

        s = self.settings
        msg = EmailMessage()
        msg["Subject"] = (
            f"[CityPark] Reservation approval #{reservation.get('id')} "
            f"— {reservation.get('full_name')}"
        )
        msg["From"] = s.smtp_from or s.smtp_user
        msg["To"] = s.admin_email
        msg.set_content(message)

        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
                if s.smtp_use_tls:
                    smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
            logger.info("Emailed approval request #%s to %s", reservation.get("id"), s.admin_email)
            return True
        except Exception as exc:  # noqa: BLE001 - delivery must never crash a turn
            logger.warning("EmailChannel delivery failed (%s)", exc)
            return False


def default_channels(settings: Settings) -> List[AdminChannel]:
    """Standard channel set: always log; add email when it's configured."""
    channels: List[AdminChannel] = [LogChannel()]
    email = EmailChannel(settings)
    if email.enabled:
        channels.append(email)
    return channels
