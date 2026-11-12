# Quick Start Guide - Stage 3

This guide walks you through running the complete CityPark system with Stage 3 MCP server.

---

## Prerequisites

- Python 3.10+
- All dependencies installed: `pip install -r requirements.txt`
- `.env` file configured (copy from `.env.example`)

---

## Step 1: Configure Environment

Edit `.env` and set the Stage 3 configuration:

```bash
# Stage 3: MCP server for confirmed reservation persistence
MCP_SERVER_URL=http://127.0.0.1:8001
MCP_SERVER_TOKEN=my-secret-token-here    # Optional but recommended
MCP_ENABLED=True
```

**Note:** If `MCP_SERVER_TOKEN` is left empty, the server runs in insecure mode (dev only).

---

## Step 2: Start the MCP Server

**Terminal 1:**

```bash
python start_mcp_server.py
```

Expected output:
```
============================================================
CityPark MCP Server - Stage 3
============================================================
Starting MCP server on http://127.0.0.1:8001
Confirmed reservations will be written to: confirmed_reservations.txt
============================================================
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://127.0.0.1:8001
```

**Verify the server is running:**

```bash
curl http://127.0.0.1:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "citypark-mcp-server",
  "version": "1.0.0",
  "file_path": "C:\\Users\\...\\confirmed_reservations.txt",
  "file_exists": false
}
```

---

## Step 3: Start the Main Application

**Terminal 2:**

```bash
uvicorn app.web.server:app --reload
```

Expected output:
```
INFO:     Will watch for changes in these directories: ['...']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [67890]
INFO:     Started server process [67891]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

---

## Step 4: Make a Reservation

### Option A: Web Interface

1. Open http://127.0.0.1:8000 in your browser
2. Chat with the bot:
   ```
   You: I'd like to reserve a parking spot
   Bot: Let's book your spot. What's your first name?
   You: Alice
   Bot: Thanks Alice. What's your last name?
   You: Anderson
   Bot: And your car's license plate number?
   You: AAA-111
   Bot: When would you like to start your reservation? (YYYY-MM-DD HH:MM)
   You: 2026-11-20 10:00
   Bot: And when would it end?
   You: 2026-11-20 18:00
   Bot: Here's your reservation request #1: ...
        Status: pending administrator confirmation.
   ```

### Option B: Terminal CLI

```bash
# Terminal 3
python -m app.cli
```

Follow the same conversation flow.

---

## Step 5: Approve the Reservation

### Option A: Web Dashboard

1. Open http://127.0.0.1:8000/admin in your browser
2. You'll see the pending reservation:
   ```
   Reservation #1
   Alice Anderson
   AAA-111
   2026-11-20 10:00:00 to 2026-11-20 18:00:00
   [Approve] [Refuse]
   ```
3. Click **Approve**

### Option B: Admin CLI

```bash
# Terminal 4
python -m app.admin.cli
```

Select the reservation and choose "approve".

---

## Step 6: Verify File Was Written

**Check the file:**

```bash
cat confirmed_reservations.txt
```

Expected content:
```
Alice Anderson | AAA-111 | 2026-11-20T10:00:00 to 2026-11-20T18:00:00 | 2026-11-12T16:30:00Z
```

**Query via MCP server:**

```bash
curl http://127.0.0.1:8001/reservations
```

Expected response:
```json
{
  "count": 1,
  "file_exists": true,
  "file_path": "...",
  "entries": [
    "Alice Anderson | AAA-111 | 2026-11-20T10:00:00 to 2026-11-20T18:00:00 | 2026-11-12T16:30:00Z"
  ]
}
```

---

## Success! 🎉

You now have the complete three-stage system running:

- ✅ **Stage 1:** RAG chatbot collects reservations
- ✅ **Stage 2:** Human administrator approves/refuses
- ✅ **Stage 3:** MCP server persists confirmed reservations to file

---

## Testing Without UI

Run the automated test suite:

```bash
# All tests
pytest

# Stage 3 only
pytest tests/test_mcp_server.py tests/test_stage3_integration.py -v

# End-to-end test
pytest tests/test_stage3_integration.py::test_stage3_end_to_end_with_chatbot -v
```

All 75 tests should pass.

---

## Troubleshooting

### MCP Server Not Starting

**Error:** `Address already in use`

**Solution:** Port 8001 is already in use. Either:
- Kill the process using port 8001
- Change `MCP_SERVER_URL` in `.env` to use a different port
- Update `mcp_server/server.py` to use a different port

### File Not Being Written

**Check:**
1. MCP server is running (http://127.0.0.1:8001/health)
2. `MCP_ENABLED=True` in `.env`
3. Reservation status is "confirmed" (not "refused")
4. Check logs for errors

**View logs:**
```bash
# MCP server logs in Terminal 1
# Main app logs in Terminal 2
```

### Authentication Errors

**Error:** `401 Unauthorized`

**Solution:** Make sure `MCP_SERVER_TOKEN` matches in:
- `.env` file
- MCP server startup
- Any manual API calls (use `-H "X-MCP-Token: your-token"` with curl)

---

## Next Steps

- Configure SMTP for email notifications (Stage 2)
- Set up DIAL API key for real LLM responses (Stages 1+2)
- Deploy to production environment
- Set up monitoring and logging
- Configure backups for confirmed_reservations.txt

---

## Support

- **Documentation:** See README.md and STAGE3-SUMMARY.md
- **Tests:** Check tests/ directory for examples
- **Presentation:** Open docs/Stage3-Presentation.html in browser
