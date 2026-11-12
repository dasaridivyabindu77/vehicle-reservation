"""Start the MCP server for Stage 3.

This script launches the MCP server that handles writing confirmed
reservations to persistent storage.

Usage:
    python start_mcp_server.py
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path so we can import mcp_server
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

if __name__ == "__main__":
    import uvicorn
    from mcp_server.server import app

    print("=" * 60)
    print("CityPark MCP Server - Stage 3")
    print("=" * 60)
    print("Starting MCP server on http://127.0.0.1:8001")
    print("Confirmed reservations will be written to: confirmed_reservations.txt")
    print("=" * 60)

    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
