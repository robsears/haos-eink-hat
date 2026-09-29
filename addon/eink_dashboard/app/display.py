"""Wraps the vendored Waveshare epd2in7 driver.

Note: the epd2in7 driver drives its own control lines (RST/DC/BUSY/PWR) via
app/waveshare_epd/epdconfig.py, which this repo overwrites at build time to
use gpiod v2 directly against /dev/gpiochip0 -- see that file's docstring for
why (Waveshare's default gpiozero-based layer was unworkable on Alpine).

This exact panel (epd2in7, the plain non-"V2" model) has no partial-refresh
support in its driver at all -- confirmed by reading the vendored source,
which only exposes display()/Clear()/display_4Gray(), no display_Partial.
Every redraw is therefore a full flash (black/white/content), which is
slower and more visually disruptive than partial refresh would be; this
matters for main.py's clock-view tick cadence (see its TICK_SECONDS/minute
comparison), since it means literally every visible minute change flashes
the whole panel.
"""

from __future__ import annotations

import logging

from PIL import Image
from waveshare_epd import epd2in7  # type: ignore[import-not-found]

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 264, 176


class Display:
    def __init__(self) -> None:
        self._epd = epd2in7.EPD()
        self._epd.init()
        self._epd.Clear(0xFF)

    def show(self, image: Image.Image) -> None:
        self._epd.display(self._epd.getbuffer(image))

    def sleep(self) -> None:
        self._epd.sleep()
