# Dashboard server API

`server.py` exposes the local FastAPI dashboard, receives control requests, and broadcasts scraper progress to connected WebSocket clients.

## Main responsibilities

- Serve the dashboard page.
- Expose configuration, status, and pause/resume/stop endpoints.
- Queue events emitted by scraper worker threads and broadcast them asynchronously.
- Keep UI transport concerns separate from scraper execution.

Authentication and network exposure are security-sensitive. Review the current implementation before exposing the server beyond localhost; do not assume that a dashboard running on a private device is automatically protected.

See [server.py](../../server.py) and [the dashboard template](../../templates/index.html).
