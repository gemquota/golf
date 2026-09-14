"""FastAPI web server with auth, validation, and WebSocket broadcasting."""
import asyncio
import json
import queue
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
    """Optional auth — skip if no UI password configured, else validate."""
    if not config.UI_PASS:
        return True  # no auth configured
    if not credentials:
        raise HTTPException(status_code=401, detail="Auth required")
    return credentials.username == config.UI_USER and credentials.password == config.UI_PASS


@web_app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept(); conns.append(ws)
    try:
        while True:
            d = await ws.receive_text()
            if d == "ping": await ws.send_text("pong")
    except WebSocketDisconnect: pass
    finally:
        if ws in conns: conns.remove(ws)

@web_app.get("/api/config")
async def get_config(auth=Depends(verify_auth)):
    return config.load_config_dict()

@web_app.post("/api/config")
async def post_config(data: ConfigData, auth=Depends(verify_auth)):
    if data.SETTINGS:
        config.save_config_dict({"SETTINGS": data.SETTINGS})
    return {"status": "ok"}

@web_app.get("/api/status")
async def get_status():
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
    uvicorn.run(web_app, host="0.0.0.0", port=8000, log_level="error")
