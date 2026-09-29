from __future__ import annotations

import json
import logging
import threading
import time

from buttons import ButtonWatcher
from display import Display
from ha_client import HAClient
from views import DashboardState, build_views

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


def _read_options() -> dict:
    with open("/data/options.json") as f:
        return json.load(f)


CLOCK_VIEW = 0
TICK_SECONDS = 5


def main() -> None:
    options = _read_options()
    weather_entity = options["weather_entity"]
    temp_view_seconds = options["temp_view_seconds"]

    client = HAClient()
    state = DashboardState()
    views = build_views(client, weather_entity)
    display = Display()

    redraw_lock = threading.Lock()
    current_view = CLOCK_VIEW
    view_revert_at: float | None = None

    def redraw() -> None:
        with redraw_lock:
            image = views[current_view].render(state)
            display.show(image)

    # Seed initial state via REST for every entity any view cares about,
    # before the websocket subscription (which only delivers *changes*)
    # comes up.
    wanted_entities = {eid for view in views.values() for eid in view.entity_ids}
    for entity_id in wanted_entities:
        try:
            snapshot = client.get_state(entity_id)
            if snapshot is not None:
                state.update_entity(entity_id, snapshot)
        except Exception:
            log.exception("failed to seed state for %s", entity_id)

    def on_state_changed(entity_id: str, new_state: dict) -> None:
        state.update_entity(entity_id, new_state)
        if entity_id in views[current_view].entity_ids or entity_id.startswith(
            ("update.", "persistent_notification.")
        ):
            redraw()

    client.subscribe_state_changed(on_state_changed)

    def on_button(button: int) -> None:
        nonlocal current_view, view_revert_at
        current_view = button
        view_revert_at = time.monotonic() + temp_view_seconds
        redraw()
        try:
            client.fire_event("eink_button_pressed", {"button": button})
        except Exception:
            log.exception("failed to fire eink_button_pressed event")

    ButtonWatcher(on_button).start()

    redraw()

    last_rendered_minute = time.localtime().tm_min
    while True:
        time.sleep(TICK_SECONDS)
        now = time.monotonic()

        if view_revert_at is not None and current_view != CLOCK_VIEW and now >= view_revert_at:
            current_view = CLOCK_VIEW
            view_revert_at = None
            redraw()
            continue

        if current_view == CLOCK_VIEW:
            minute = time.localtime().tm_min
            if minute != last_rendered_minute:
                last_rendered_minute = minute
                redraw()


if __name__ == "__main__":
    main()
