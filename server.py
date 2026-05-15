"""Lightweight HTTP server for the Risk Engine dashboard.

Serves the static dashboard files and exposes a JSON API endpoint
for the real-time state polling.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


# Global reference to the engine state (set by main.py)
_engine_state: dict = {}
_order_log: list[dict] = []
_lock = threading.Lock()


def update_state(state: dict):
    global _engine_state
    with _lock:
        _engine_state = state


def add_order_event(event: dict):
    with _lock:
        _order_log.append(event)
        # Keep last 200
        if len(_order_log) > 200:
            _order_log.pop(0)


def get_state() -> dict:
    with _lock:
        return {**_engine_state, "order_log": list(_order_log)}


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serves dashboard files + JSON API."""

    def __init__(self, *args, dashboard_dir: str = "", **kwargs):
        self._dashboard_dir = dashboard_dir
        super().__init__(*args, directory=dashboard_dir, **kwargs)

    def do_GET(self):
        if self.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = get_state()
            self.wfile.write(json.dumps(data, default=str).encode())
        elif self.path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with _lock:
                events = _engine_state.get("events", [])
            self.wfile.write(json.dumps(events, default=str).encode())
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


def start_server(port: int = 8765, dashboard_dir: str = "dashboard") -> HTTPServer:
    """Start the dashboard server in a background thread."""
    dashboard_path = str(Path(dashboard_dir).resolve())

    def handler(*args, **kwargs):
        return DashboardHandler(*args, dashboard_dir=dashboard_path, **kwargs)

    server = HTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
