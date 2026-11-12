"""MCP Server for writing confirmed reservations to file.

This server implements the Model Context Protocol (MCP) to provide a secure
interface for writing reservation data to persistent storage. It exposes
tools that can be called by the administrator agent when a reservation is
confirmed.

Stage 3 requirement: Write confirmed reservation details to a text file in
the format: Name | Car Number | Reservation Period | Approval Time
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Security: Token-based authentication
MCP_SERVER_TOKEN = os.getenv("MCP_SERVER_TOKEN", "")
RESERVATIONS_FILE = Path("confirmed_reservations.txt")

app = FastAPI(
    title="CityPark MCP Server",
    description="MCP server for processing and storing confirmed vehicle reservations",
    version="1.0.0",
)


class ReservationData(BaseModel):
    """Reservation data model for confirmed bookings."""

    reservation_id: int = Field(..., description="Unique reservation ID")
    first_name: str = Field(..., description="Customer first name")
    last_name: str = Field(..., description="Customer last name")
    car_number: str = Field(..., description="Vehicle license plate number")
    start_ts: str = Field(..., description="Reservation start timestamp")
    end_ts: str = Field(..., description="Reservation end timestamp")
    approved_by: str = Field(default="admin", description="Administrator who approved")
    approval_time: Optional[str] = Field(
        default=None, description="Approval timestamp (ISO format)"
    )


class WriteResult(BaseModel):
    """Result of write operation."""

    success: bool
    message: str
    file_path: str
    entry_count: int


def verify_token(x_mcp_token: str = Header(None)) -> bool:
    """Verify MCP server token for authentication.

    Security requirement: Ensure the server is resistant to unauthorized access.
    """
    if not MCP_SERVER_TOKEN:
        # If no token is configured, allow access (development mode)
        logger.warning("MCP_SERVER_TOKEN not configured - running in insecure mode")
        return True

    if x_mcp_token != MCP_SERVER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing MCP token")
    return True


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "citypark-mcp-server",
        "version": "1.0.0",
        "file_path": str(RESERVATIONS_FILE.absolute()),
        "file_exists": RESERVATIONS_FILE.exists(),
    }


@app.get("/tools/list")
async def list_tools(authorized: bool = Depends(verify_token)):
    """MCP protocol: List available tools.

    Returns the tool definitions that can be invoked by the administrator agent.
    """
    return {
        "tools": [
            {
                "name": "write_confirmed_reservation",
                "description": "Write a confirmed reservation to persistent storage",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reservation_id": {"type": "integer"},
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "car_number": {"type": "string"},
                        "start_ts": {"type": "string"},
                        "end_ts": {"type": "string"},
                        "approved_by": {"type": "string"},
                        "approval_time": {"type": "string"},
                    },
                    "required": [
                        "reservation_id",
                        "first_name",
                        "last_name",
                        "car_number",
                        "start_ts",
                        "end_ts",
                    ],
                },
            },
            {
                "name": "read_confirmed_reservations",
                "description": "Read all confirmed reservations from storage",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]
    }


@app.post("/tools/call/write_confirmed_reservation")
async def write_confirmed_reservation(
    data: ReservationData, authorized: bool = Depends(verify_token)
) -> WriteResult:
    """MCP tool: Write a confirmed reservation to file.

    Format: Name | Car Number | Reservation Period | Approval Time

    This tool is called by the escalation service after the administrator
    approves a reservation.
    """
    try:
        # Set approval time if not provided
        approval_time = data.approval_time or datetime.now(timezone.utc).isoformat()

        # Format: Name | Car Number | Reservation Period | Approval Time
        full_name = f"{data.first_name} {data.last_name}"
        reservation_period = f"{data.start_ts} to {data.end_ts}"
        entry = f"{full_name} | {data.car_number} | {reservation_period} | {approval_time}\n"

        # Append to file (create if doesn't exist)
        with RESERVATIONS_FILE.open("a", encoding="utf-8") as f:
            f.write(entry)

        # Count total entries
        with RESERVATIONS_FILE.open("r", encoding="utf-8") as f:
            entry_count = len(f.readlines())

        logger.info(
            "Wrote confirmed reservation #%s to %s",
            data.reservation_id,
            RESERVATIONS_FILE,
        )

        return WriteResult(
            success=True,
            message=f"Reservation #{data.reservation_id} written successfully",
            file_path=str(RESERVATIONS_FILE.absolute()),
            entry_count=entry_count,
        )

    except Exception as e:
        logger.error("Failed to write reservation: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to write reservation: {str(e)}"
        )


@app.post("/tools/call/read_confirmed_reservations")
async def read_confirmed_reservations(authorized: bool = Depends(verify_token)):
    """MCP tool: Read all confirmed reservations.

    Returns the contents of the confirmed reservations file.
    """
    try:
        if not RESERVATIONS_FILE.exists():
            return {
                "success": True,
                "entries": [],
                "count": 0,
                "message": "No confirmed reservations yet",
            }

        with RESERVATIONS_FILE.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        entries = [line.strip() for line in lines if line.strip()]

        return {
            "success": True,
            "entries": entries,
            "count": len(entries),
            "file_path": str(RESERVATIONS_FILE.absolute()),
        }

    except Exception as e:
        logger.error("Failed to read reservations: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to read reservations: {str(e)}"
        )


@app.get("/reservations")
async def get_reservations_summary(authorized: bool = Depends(verify_token)):
    """Get a summary of all confirmed reservations."""
    try:
        if not RESERVATIONS_FILE.exists():
            return {"count": 0, "file_exists": False, "entries": []}

        with RESERVATIONS_FILE.open("r", encoding="utf-8") as f:
            entries = [line.strip() for line in f if line.strip()]

        return {
            "count": len(entries),
            "file_exists": True,
            "file_path": str(RESERVATIONS_FILE.absolute()),
            "entries": entries[-10:],  # Last 10 entries
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
