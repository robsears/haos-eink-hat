"""Talks to Home Assistant Core through the Supervisor's API proxy.

Add-ons with `homeassistant_api: true` in config.yaml get a SUPERVISOR_TOKEN
env var and can reach Core at http://supervisor/core/api (REST) and
ws://supervisor/core/websocket (events), without the user ever pasting a
long-lived access token anywhere.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable

import requests
import websockets
from websockets.sync.client import connect as ws_connect

log = logging.getLogger(__name__)

_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
_REST_BASE = "http://supervisor/core/api"
_SUPERVISOR_BASE = "http://supervisor"  # Supervisor's own API, needs hassio_api: true
_WS_URL = "ws://supervisor/core/websocket"


class HAClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": "application/json",
        }

    def get_state(self, entity_id: str) -> dict | None:
        resp = requests.get(f"{_REST_BASE}/states/{entity_id}", headers=self._headers, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_all_states(self) -> list[dict]:
        resp = requests.get(f"{_REST_BASE}/states", headers=self._headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_supervisor_json(self, path: str) -> dict:
        """path e.g. 'info', 'core/info', 'os/info', 'addons'."""
        resp = requests.get(f"{_SUPERVISOR_BASE}/{path}", headers=self._headers, timeout=10)
        resp.raise_for_status()
        return resp.json()["data"]

    def fire_event(self, event_type: str, data: dict) -> None:
        resp = requests.post(
            f"{_REST_BASE}/events/{event_type}", headers=self._headers, json=data, timeout=10
        )
        resp.raise_for_status()

    def subscribe_state_changed(self, on_change: Callable[[str, dict], None]) -> None:
        """Runs forever (call from a background thread) delivering every
        state_changed event to on_change(entity_id, new_state_dict)."""

        def _run() -> None:
            while True:
                try:
                    self._subscribe_once(on_change)
                except (
                    websockets.exceptions.ConnectionClosed,
                    ConnectionError,
                    OSError,
                ) as exc:
                    log.warning("websocket dropped (%s), reconnecting", exc)

        threading.Thread(target=_run, daemon=True, name="ha-ws").start()

    def _subscribe_once(self, on_change: Callable[[str, dict], None]) -> None:
        with ws_connect(_WS_URL) as ws:
            hello = json.loads(ws.recv())
            assert hello["type"] == "auth_required", hello

            ws.send(json.dumps({"type": "auth", "access_token": _TOKEN}))
            auth_result = json.loads(ws.recv())
            if auth_result["type"] != "auth_ok":
                raise RuntimeError(f"HA websocket auth failed: {auth_result}")

            ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed"}))
            ack = json.loads(ws.recv())
            if not ack.get("success", False):
                raise RuntimeError(f"subscribe_events failed: {ack}")

            log.info("subscribed to state_changed events")
            for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") != "event":
                    continue
                event_data = msg["event"]["data"]
                new_state = event_data.get("new_state")
                if new_state is not None:
                    on_change(event_data["entity_id"], new_state)
