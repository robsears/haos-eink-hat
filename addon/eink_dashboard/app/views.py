"""View registry: buttons are direct-access, one button = one view (see
docs/PLAN.md). Adding a 5th view later would mean nothing structural -- just
one more View subclass and one more line in VIEWS.

View 0 is the idle/default Clock view; main.py shows it on startup and
reverts to it a fixed time after the last button press.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

from ha_client import HAClient
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 264, 176
FONT = ImageFont.load_default()

_FONT_DIR = "/usr/share/fonts/dejavu"  # from the `font-dejavu` apk package
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(f"{_FONT_DIR}/{name}", size)
    return _font_cache[key]


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, y: int) -> None:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (right - left)) // 2, y), text, font=font, fill=0)


@dataclass
class DashboardState:
    """Cache of the bits of HA state each view cares about. Populated once
    at startup via REST, then kept current by ha_client's websocket
    subscription calling update_entity() on every relevant state_changed."""

    entities: dict[str, dict] = field(default_factory=dict)

    def update_entity(self, entity_id: str, new_state: dict) -> None:
        self.entities[entity_id] = new_state

    def get(self, entity_id: str) -> dict | None:
        return self.entities.get(entity_id)


def _blank() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("1", (WIDTH, HEIGHT), 255)
    return image, ImageDraw.Draw(image)


class View:
    #: entity_ids this view needs kept warm in DashboardState; used at
    #: startup to know what to seed via REST.
    entity_ids: list[str] = []

    def render(self, state: DashboardState) -> Image.Image:
        raise NotImplementedError


class ClockView(View):
    """Idle/default screen: big time, date, small sunrise/sunset countdown."""

    entity_ids = ["sun.sun"]

    def render(self, state: DashboardState) -> Image.Image:
        image, draw = _blank()
        now = time.localtime()

        _draw_centered(draw, time.strftime("%H:%M", now), _font("DejaVuSans-Bold.ttf", 56), 8)
        _draw_centered(draw, time.strftime("%A, %B %-d", now), _font("DejaVuSans.ttf", 20), 78)
        _draw_centered(draw, _sun_countdown(state.get("sun.sun")), _font("DejaVuSans.ttf", 14), 104)

        return image


def _sun_countdown(sun: dict | None) -> str:
    if sun is None:
        return ""
    attrs = sun.get("attributes", {})
    above_horizon = sun.get("state") == "above_horizon"
    target_iso = attrs.get("next_setting") if above_horizon else attrs.get("next_rising")
    if not target_iso:
        return ""

    target = datetime.fromisoformat(target_iso.replace("Z", "+00:00"))
    seconds_left = max(0, int((target - datetime.now(target.tzinfo)).total_seconds()))
    hours, rem = divmod(seconds_left, 3600)
    minutes = rem // 60
    label = "Sunset" if above_horizon else "Sunrise"
    return f"{label} in {hours}h{minutes:02d}m"


class MainView(View):
    def __init__(self, weather_entity: str) -> None:
        self.weather_entity = weather_entity
        self.entity_ids = [weather_entity]

    def render(self, state: DashboardState) -> Image.Image:
        image, draw = _blank()
        draw.text((4, 4), "Main", font=FONT, fill=0)
        draw.line((4, 16, WIDTH - 4, 16), fill=0)

        draw.text((4, 22), time.strftime("%a %Y-%m-%d %H:%M"), font=FONT, fill=0)
        draw.text((4, 36), f"uptime: {_uptime_str()}", font=FONT, fill=0)

        weather = state.get(self.weather_entity)
        if weather is not None:
            temp = weather.get("attributes", {}).get("temperature", "?")
            draw.text((4, 54), f"weather: {weather['state']} {temp}", font=FONT, fill=0)
        else:
            draw.text((4, 54), "weather: (no data yet)", font=FONT, fill=0)

        pending = sum(
            1 for eid, s in state.entities.items() if eid.startswith("update.") and s["state"] == "on"
        )
        draw.text((4, 70), f"updates pending: {pending}", font=FONT, fill=0)
        return image


class MessagesView(View):
    def render(self, state: DashboardState) -> Image.Image:
        image, draw = _blank()
        draw.text((4, 4), "Messages", font=FONT, fill=0)
        draw.line((4, 16, WIDTH - 4, 16), fill=0)

        notifications = [
            s for eid, s in state.entities.items() if eid.startswith("persistent_notification.")
        ]
        if not notifications:
            draw.text((4, 22), "No active notifications", font=FONT, fill=0)
        else:
            y = 22
            for notif in notifications[:6]:
                title = notif.get("attributes", {}).get("title") or notif.get("entity_id", "?")
                draw.text((4, y), f"- {title}"[:44], font=FONT, fill=0)
                y += 14
        # TODO: HA "Repairs" issues live behind the websocket command
        # repairs/list_issues, not regular entity state -- not wired up yet.
        return image


class DiagnosticsView(View):
    def __init__(self, client: HAClient) -> None:
        self._client = client

    def render(self, state: DashboardState) -> Image.Image:
        image, draw = _blank()
        draw.text((4, 4), "Diagnostics", font=FONT, fill=0)
        draw.line((4, 16, WIDTH - 4, 16), fill=0)

        try:
            core = self._client.get_supervisor_json("core/info")
            supervisor = self._client.get_supervisor_json("info")
            addons = self._client.get_supervisor_json("addons")
        except Exception as exc:  # noqa: BLE001 - render *something* on any failure
            draw.text((4, 22), "supervisor API error:", font=FONT, fill=0)
            draw.text((4, 36), str(exc)[:44], font=FONT, fill=0)
            return image

        draw.text((4, 22), f"core:       {core.get('version', '?')}", font=FONT, fill=0)
        draw.text((4, 36), f"supervisor: {supervisor.get('supervisor', '?')}", font=FONT, fill=0)

        unhealthy = [a["name"] for a in addons.get("addons", []) if a.get("state") != "started"]
        if unhealthy:
            draw.text((4, 50), f"not running: {', '.join(unhealthy)}"[:44], font=FONT, fill=0)
        else:
            draw.text((4, 50), f"add-ons: all {len(addons.get('addons', []))} running", font=FONT, fill=0)
        return image


class PlaceholderView(View):
    """Button 4 -- left undefined per docs/PLAN.md; add a real View subclass
    here when there's content for it."""

    def render(self, state: DashboardState) -> Image.Image:
        image, draw = _blank()
        draw.text((4, 4), "(unassigned)", font=FONT, fill=0)
        draw.line((4, 16, WIDTH - 4, 16), fill=0)
        draw.text((4, 22), "Button 4 has no view yet.", font=FONT, fill=0)
        return image


def build_views(client: HAClient, weather_entity: str) -> dict[int, View]:
    return {
        0: ClockView(),
        1: MainView(weather_entity),
        2: MessagesView(),
        3: DiagnosticsView(client),
        4: PlaceholderView(),
    }


def _uptime_str() -> str:
    with open("/proc/uptime") as f:
        seconds = float(f.read().split()[0])
    hours, rem = divmod(int(seconds), 3600)
    minutes = rem // 60
    return f"{hours}h{minutes:02d}m"
