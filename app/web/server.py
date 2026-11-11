"""FastAPI web app: a chat endpoint plus a minimal browser UI.

Run with::

    uvicorn app.web.server:app --reload

``GET /``        serves the chat page.
``POST /chat``   {"message": str, "session_id": str} -> chat response.
``GET /health``  liveness + backend info.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..chatbot import Chatbot

app = FastAPI(title="CityPark Assistant", version="0.1.0")
_bot: Chatbot | None = None
_INDEX = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


def get_bot() -> Chatbot:
    global _bot
    if _bot is None:
        _bot = Chatbot()
    return _bot


class ChatRequest(BaseModel):
    message: str
    session_id: str = "web"


class ChatReply(BaseModel):
    reply: str
    intent: str
    refused: bool
    blocked: bool
    in_reservation: bool
    sources: list
    latency_ms: float


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX


@app.get("/health")
def health() -> dict:
    bot = get_bot()
    return {
        "status": "ok",
        "vector_backend": bot.backend,
        "llm": "dial" if bot.settings.llm_configured else "offline",
    }


@app.post("/chat", response_model=ChatReply)
def chat(req: ChatRequest) -> ChatReply:
    bot = get_bot()
    resp = bot.chat(req.message, session_id=req.session_id)
    return ChatReply(
        reply=resp.reply,
        intent=resp.intent,
        refused=resp.refused,
        blocked=resp.blocked,
        in_reservation=resp.in_reservation,
        sources=resp.sources,
        latency_ms=resp.latency_ms,
    )
