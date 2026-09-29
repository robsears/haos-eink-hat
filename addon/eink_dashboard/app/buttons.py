"""Reads the 4 e-paper HAT buttons via libgpiod (character-device GPIO,
the modern replacement for the deprecated /sys/class/gpio sysfs interface).

Uses the gpiod v2 API (gpiod.request_lines / LineSettings) -- the pip
package `gpiod` is the v2 rewrite, not the older chip.get_line()/line.request()
API that some still-circulating examples online show.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import gpiod  # type: ignore[import-not-found]
from gpiod.line import Bias, Direction, Edge

log = logging.getLogger(__name__)

# BCM pin numbers, KEY1-KEY4 per Waveshare's published pinout for this HAT.
# Verify against the silkscreen on the actual board -- revisions exist.
BUTTON_PINS = {1: 5, 2: 6, 3: 13, 4: 19}

GPIO_CHIP_PATH = "/dev/gpiochip0"  # confirm with `ls /dev/gpiochip*` on the real
                                    # Pi; this can vary (e.g. gpiochip4) by
                                    # kernel/board rev -- gpiochip0 confirmed on
                                    # this project's Pi 4.

# on_press (via main.py's redraw()) is synchronous and blocks this thread for
# the full duration of a display refresh (multiple seconds). Any edges that
# arrive during that window queue up in the kernel and would otherwise all
# get drained and processed as separate presses the moment we come back
# around -- triggering another refresh, queuing more edges, cascading
# indefinitely. Confirmed on real hardware: a single tap could cascade 20+
# refresh cycles. Fix: a hard cooldown spanning the whole redraw, dropping
# every queued event during it rather than processing each one.
COOLDOWN_SECONDS = 1.5


class ButtonWatcher:
    def __init__(self, on_press: Callable[[int], None]) -> None:
        self._on_press = on_press
        self._offset_to_button = {pin: btn for btn, pin in BUTTON_PINS.items()}
        settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            edge_detection=Edge.FALLING,
            bias=Bias.PULL_UP,
        )
        config = {pin: settings for pin in BUTTON_PINS.values()}
        self._request = gpiod.request_lines(
            GPIO_CHIP_PATH, consumer="eink-dashboard", config=config
        )

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="buttons").start()

    def _run(self) -> None:
        log.info("watching buttons on %s", BUTTON_PINS)
        ignore_until = 0.0
        while True:
            if self._request.wait_edge_events(timeout=0.2):
                events = self._request.read_edge_events()
                now = time.monotonic()
                if now < ignore_until:
                    continue  # discard the whole backlog, still cooling down
                btn = self._offset_to_button[events[0].line_offset]
                log.debug("button %d pressed", btn)
                self._on_press(btn)
                ignore_until = time.monotonic() + COOLDOWN_SECONDS
