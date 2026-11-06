# Dashboard server

## Authentication model

The dashboard API requires HTTP Basic credentials. Authentication fails closed when GOLF_UI_PASS or SETTINGS.ui_pass is missing, and incorrect credentials receive HTTP 401. Comparisons use constant-time byte comparison.

The config endpoint returns only min_delay and max_delay. It never exposes account sections, proxy credentials, API keys, or passwords. Config writes accept only those two delay settings and validate their ranges.

WebSocket clients first obtain a short-lived, single-use ticket through the authenticated POST /api/ws-ticket endpoint. The ticket is sent as a WebSocket subprotocol; direct unauthenticated connections are rejected.

## Routes

| Method | Path | Access |
|---|---|---|
| GET | / | Static dashboard page |
| GET | /api/config | Authenticated |
| POST | /api/config | Authenticated |
| GET | /api/status | Authenticated |
| POST | /api/control/{action} | Authenticated |
| POST | /api/ws-ticket | Authenticated |
| WebSocket | /ws | One-use ticket required |

## Network binding

The server binds to 127.0.0.1 by default. GOLF_BIND_HOST can explicitly override the bind address; only do so for a trusted deployment with suitable network and transport protections.

## Runtime behavior

Scraper worker threads enqueue progress events. The asynchronous broadcast pump fans events out to authenticated WebSocket clients. The dashboard uses the current page protocol to select ws or wss.
