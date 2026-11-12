"""The administrator agent — the second agent, built with LangChain.

Where the Stage 1 chatbot converses with the *user*, this agent works on behalf
of the *human administrator*. It has two language skills plus an orchestration
step:

1. :meth:`AdminAgent.compose_request` — turn a raw reservation row into a clear,
   friendly approval request for the administrator (a LangChain
   ``prompt | model | parser`` chain on DIAL; a deterministic template offline).
2. :meth:`AdminAgent.escalate` — deliver that request through every configured
   channel. When DIAL is available this runs as a genuine LangChain
   tool-calling agent whose single tool hands the message to the channels;
   offline it delivers directly.
3. :meth:`AdminAgent.interpret_decision` — read the administrator's free-text
   reply (``"approve"``, ``"no, the lot is full that day"``) and turn it into a
   structured confirm/refuse + reason (LangChain structured output on DIAL; a
   keyword parser offline).

Every LLM path is wrapped so a model hiccup degrades to the deterministic path
rather than breaking an approval — the same safety contract as Stage 1's
``Chatbot.generate``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from langchain_core.language_models import BaseChatModel

from ..config import Settings
from ..sql_store import STATUS_CONFIRMED, STATUS_REFUSED
from .channels import AdminChannel, default_channels

logger = logging.getLogger(__name__)

_APPROVE_WORDS = {
    "approve", "approved", "approves", "confirm", "confirmed", "accept",
    "accepted", "yes", "ok", "okay", "grant", "granted", "allow", "allowed",
}
_REFUSE_WORDS = {
    "refuse", "refused", "reject", "rejected", "decline", "declined", "deny",
    "denied", "no", "cancel", "cancelled", "unavailable",
}
_REFUSE_PHRASES = ("not available", "no space", "no spaces", "lot is full", "fully booked")


@dataclass
class AdminDecision:
    """Structured outcome of the administrator's reply."""

    approved: bool
    reason: str = ""

    @property
    def status(self) -> str:
        return STATUS_CONFIRMED if self.approved else STATUS_REFUSED


class AdminAgent:
    """LangChain agent that mediates between the system and the human admin."""

    def __init__(
        self,
        settings: Settings,
        chat_model: Optional[BaseChatModel] = None,
        channels: Optional[List[AdminChannel]] = None,
    ) -> None:
        self.settings = settings
        self.chat_model = chat_model
        self.channels = channels if channels is not None else default_channels(settings)

    # --- skill 1: compose the approval request -------------------------------
    def compose_request(self, reservation: dict) -> str:
        """Compose the approval request the administrator will act on."""
        if self.chat_model is not None:
            try:
                return self._compose_with_llm(reservation)
            except Exception as exc:  # noqa: BLE001 - fall back, never crash
                logger.warning("Admin compose LLM failed (%s); using template", exc)
        return self._compose_template(reservation)

    def _compose_with_llm(self, reservation: dict) -> str:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are the assistant to {admin_name} at CityPark parking. "
                    "Write a short, clear approval request asking the administrator "
                    "to CONFIRM or REFUSE a parking reservation. State the reference "
                    "number, customer name, licence plate and the full period. End "
                    "by asking them to reply 'approve' or 'refuse' (with a reason if "
                    "refusing). Plain text, no markdown, under 90 words.",
                ),
                (
                    "human",
                    "Reservation #{id}\nCustomer: {full_name}\nPlate: {car_number}\n"
                    "From: {start_ts}\nTo: {end_ts}",
                ),
            ]
        )
        chain = prompt | self.chat_model | StrOutputParser()
        text = chain.invoke(
            {
                "admin_name": self.settings.admin_name,
                "id": reservation.get("id"),
                "full_name": reservation.get("full_name"),
                "car_number": reservation.get("car_number"),
                "start_ts": reservation.get("start_ts"),
                "end_ts": reservation.get("end_ts"),
            }
        )
        return text.strip()

    def _compose_template(self, reservation: dict) -> str:
        return (
            f"Approval needed — parking reservation #{reservation.get('id')}\n"
            f"  Customer: {reservation.get('full_name')}\n"
            f"  Plate:    {reservation.get('car_number')}\n"
            f"  From:     {reservation.get('start_ts')}\n"
            f"  To:       {reservation.get('end_ts')}\n"
            "Please reply 'approve' to confirm, or 'refuse: <reason>' to decline."
        )

    # --- skill 2: deliver the request to the administrator -------------------
    def escalate(self, reservation: dict) -> str:
        """Compose and deliver an approval request; return the message sent."""
        message = self.compose_request(reservation)

        if self.chat_model is not None:
            try:
                self._deliver_with_agent(reservation, message)
                return message
            except Exception as exc:  # noqa: BLE001 - fall back to direct delivery
                logger.warning("Admin tool-calling agent failed (%s); delivering directly", exc)

        self._deliver(reservation, message)
        return message

    def _deliver(self, reservation: dict, message: str) -> List[str]:
        """Push the message through every channel; return the ones that succeeded."""
        delivered: List[str] = []
        for channel in self.channels:
            try:
                if channel.send(reservation, message):
                    delivered.append(channel.name)
            except Exception as exc:  # noqa: BLE001 - one bad channel can't block others
                logger.warning("Channel %r failed (%s)", getattr(channel, "name", "?"), exc)
        return delivered

    def _deliver_with_agent(self, reservation: dict, message: str) -> None:
        """Run a real LangChain tool-calling agent whose tool is the delivery.

        This demonstrates the second agent as an autonomous LangChain agent: the
        model is given a ``deliver_to_administrator`` tool and instructed to use
        it to send the already-composed request. Imported lazily (DIAL-only path).
        """
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.tools import tool

        delivered: List[str] = []

        @tool
        def deliver_to_administrator(request_text: str) -> str:
            """Deliver the reservation approval request to the human administrator."""
            delivered.extend(self._deliver(reservation, request_text))
            return f"Delivered via: {', '.join(delivered) or 'no channel'}"

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You deliver reservation approval requests to the CityPark "
                    "administrator. Call deliver_to_administrator exactly once with "
                    "the request text, then stop.",
                ),
                ("human", "Deliver this approval request:\n\n{message}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )
        agent = create_tool_calling_agent(self.chat_model, [deliver_to_administrator], prompt)
        executor = AgentExecutor(agent=agent, tools=[deliver_to_administrator], verbose=False)
        executor.invoke({"message": message})
        if not delivered:  # agent didn't call the tool — deliver directly
            self._deliver(reservation, message)

    # --- skill 3: interpret the administrator's reply ------------------------
    def interpret_decision(
        self, raw_decision: str, reason: Optional[str] = None
    ) -> AdminDecision:
        """Parse the administrator's reply into a confirm/refuse + reason."""
        raw = (raw_decision or "").strip()
        if self.chat_model is not None:
            try:
                decision = self._interpret_with_llm(raw)
                if reason:
                    decision.reason = reason
                return decision
            except Exception as exc:  # noqa: BLE001 - fall back to keyword parsing
                logger.warning("Admin decision LLM failed (%s); using keyword parse", exc)
        return self._interpret_keywords(raw, reason)

    def _interpret_with_llm(self, raw: str) -> AdminDecision:
        from pydantic import BaseModel, Field

        class _Schema(BaseModel):
            approved: bool = Field(description="True if the administrator approves the booking")
            reason: str = Field(default="", description="Short reason, especially if refused")

        structured = self.chat_model.with_structured_output(_Schema)
        result = structured.invoke(
            "Decide whether this administrator reply approves or refuses a parking "
            f"reservation, and extract any reason.\n\nReply: {raw!r}"
        )
        return AdminDecision(approved=bool(result.approved), reason=(result.reason or "").strip())

    @staticmethod
    def _interpret_keywords(raw: str, reason: Optional[str]) -> AdminDecision:
        text = raw.lower()
        # Explicit refuse phrases win, then token matching, else default to refuse
        # for safety (never silently confirm an ambiguous reply).
        refused = any(p in text for p in _REFUSE_PHRASES)
        tokens = set(re.findall(r"[a-z']+", text))
        approve_hit = bool(tokens & _APPROVE_WORDS) and not refused
        refuse_hit = refused or bool(tokens & _REFUSE_WORDS)

        approved = approve_hit and not refuse_hit

        if reason:
            clean_reason = reason.strip()
        else:
            # Use the remainder after a "refuse:"/"approve:" prefix as the reason.
            m = re.search(r"[:\-]\s*(.+)$", raw)
            clean_reason = m.group(1).strip() if m else ""

        if not clean_reason:
            clean_reason = "Approved by administrator." if approved else "Declined by administrator."
        return AdminDecision(approved=approved, reason=clean_reason)
