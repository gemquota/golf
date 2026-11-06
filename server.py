"""FastAPI web server with auth, validation, and WebSocket broadcasting."""
import asyncio
import json
import queue
import os
import secrets
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
from pydantic import BaseModel

import config

web_app = FastAPI(title="Golf Scraper API")
security = HTTPBasic(auto_error=False)
conns = []
_ws_ticket_lock = threading.Lock()
_ws_tickets: dict[str, float] = {}
_WS_TICKET_TTL = 30.0
event_queue: "queue.Queue[dict]" = queue.Queue()
PAUSED = False
STOPPED = False
IS_RUNNING = False


class ConfigData(BaseModel):
    SETTINGS: dict | None = None


def broadcast_event(data: dict):
    """Thread-safe entry point for worker threads to emit dashboard updates."""
    event_queue.put(dict(data))


async def _broadcast_pump():
    """Drain events queued by worker threads and fan out to WebSocket clients."""
    while True:
        try:
            payload = event_queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.2)
            continue
        text = json.dumps(payload)
        for ws in list(conns):
            try:
                await ws.send_text(text)
            except Exception:
                if ws in conns:
                    conns.remove(ws)


@web_app.on_event("startup")
async def _start_pump():
    asyncio.create_task(_broadcast_pump())


def verify_auth(credentials: HTTPBasicCredentials | None = Depends(security)):
    """Fail closed when credentials are absent or incorrect."""
    if not config.UI_PASS:
        raise HTTPException(status_code=503, detail="Dashboard authentication is not configured")
    if (
        credentials is None
        or not secrets.compare_digest(credentials.username.encode("utf-8"), str(config.UI_USER or "").encode("utf-8"))
        or not secrets.compare_digest(credentials.password.encode("utf-8"), str(config.UI_PASS).encode("utf-8"))
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid dashboard credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


def issue_ws_ticket() -> str:
    """Issue a one-use WebSocket ticket after HTTP Basic authentication."""
    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _ws_ticket_lock:
        expired = [key for key, expiry in _ws_tickets.items() if expiry <= now]
        for key in expired:
            _ws_tickets.pop(key, None)
        _ws_tickets[ticket] = now + _WS_TICKET_TTL
    return ticket


def consume_ws_ticket(ticket: str) -> bool:
    """Consume a WebSocket ticket exactly once."""
    now = time.monotonic()
    with _ws_ticket_lock:
        expiry = _ws_tickets.pop(ticket, None)
    return expiry is not None and expiry > now


@web_app.post("/api/ws-ticket")
async def create_ws_ticket(auth=Depends(verify_auth)):
    return {"ticket": issue_ws_ticket()}


@web_app.websocket("/ws")
async def ws(ws: WebSocket):
    offered = [part.strip() for part in ws.headers.get("sec-websocket-protocol", "").split(",")]
    ticket_protocol = next((part for part in offered if part.startswith("golf-ticket.")), "")
    ticket = ticket_protocol.removeprefix("golf-ticket.")
    if not ticket or not consume_ws_ticket(ticket):
        await ws.close(code=4401)
        return
    await ws.accept(subprotocol="golf")
    conns.append(ws)
    try:
        while True:
            d = await ws.receive_text()
            if d == "ping": await ws.send_text("pong")
    except WebSocketDisconnect: pass
    finally:
        if ws in conns: conns.remove(ws)

@web_app.get("/api/config")
async def get_config(auth=Depends(verify_auth)):
    settings = config.load_config_dict().get("SETTINGS", {})
    # Never return account sections, passwords, API keys, or proxy credentials.
    return {"SETTINGS": {key: settings.get(key, "") for key in ("min_delay", "max_delay")}}


@web_app.post("/api/config")
async def post_config(data: ConfigData, auth=Depends(verify_auth)):
    if data.SETTINGS:
        allowed = {"min_delay", "max_delay"}
        if set(data.SETTINGS) - allowed:
            raise HTTPException(status_code=422, detail="Only min_delay and max_delay may be changed here")
        try:
            minimum = float(data.SETTINGS.get("min_delay", config.MIN_DELAY))
            maximum = float(data.SETTINGS.get("max_delay", config.MAX_DELAY))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Delays must be numeric")
        if not (0.1 <= minimum <= 60 and 0.1 <= maximum <= 120 and maximum >= minimum):
            raise HTTPException(status_code=422, detail="Delay range is invalid")
        config.save_config_dict({"SETTINGS": {"min_delay": minimum, "max_delay": maximum}})
    return {"status": "ok"}


@web_app.get("/api/status")
async def get_status(auth=Depends(verify_auth)):
    return {"paused": PAUSED, "stopped": STOPPED, "is_running": IS_RUNNING}

VALID_ACTIONS = {"pause", "resume", "stop"}

@web_app.post("/api/control/{action}")
async def control(action: str, auth=Depends(verify_auth)):
    global PAUSED, STOPPED
    if action not in VALID_ACTIONS:
        raise HTTPException(400, f"Invalid action: {action}. Use: pause, resume, stop")
    if action == "pause": PAUSED = True
    elif action == "resume": PAUSED = False
    elif action == "stop": STOPPED, PAUSED = True, False
    status_map = {"pause": "paused", "resume": "resumed", "stop": "stopped"}
    return {"status": status_map[action]}

@web_app.get("/")
async def root():
    return HTMLResponse(Path("templates/index.html").read_text())

def start_server():
    uvicorn.run(web_app, host=os.environ.get("GOLF_BIND_HOST", "127.0.0.1"), port=8000, log_level="error")
