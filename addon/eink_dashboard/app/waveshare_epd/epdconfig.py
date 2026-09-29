"""Replaces the vendored waveshare_epd/epdconfig.py hardware layer.
"""

from __future__ import annotations

import time

import gpiod
import spidev
from gpiod.line import Direction, Value

RST_PIN = 17
DC_PIN = 25
BUSY_PIN = 24
PWR_PIN = 18
CS_PIN = 8  # stored by epd2in7.EPD.__init__ but never toggled -- SPI hardware
            # chip-select (spidev bus=0, device=0) handles this instead.

_GPIO_CHIP_PATH = "/dev/gpiochip0"

# Only these are actually requested as gpiod lines. CS_PIN (BCM 8) is the
# hardware SPI0 CE0 pin -- spidev toggles it automatically during transfers,
# so epd2in7.py's digital_write(cs_pin, ...) calls must be silently ignored
# here, exactly like Waveshare's original epdconfig.py does (its digital_write
# has no case for CS_PIN either -- confirmed by reading their source). Trying
# to actually act on a pin outside this set raises ValueError from gpiod,
# which is what happened before this guard was added.
_OUTPUT_PINS = (RST_PIN, DC_PIN, PWR_PIN)
_INPUT_PINS = (BUSY_PIN,)

_spi = spidev.SpiDev()
_request: gpiod.LineRequest | None = None


def _lines() -> gpiod.LineRequest:
    global _request
    if _request is None:
        out = gpiod.LineSettings(direction=Direction.OUTPUT)
        inp = gpiod.LineSettings(direction=Direction.INPUT)
        config = {pin: out for pin in _OUTPUT_PINS}
        config.update({pin: inp for pin in _INPUT_PINS})
        _request = gpiod.request_lines(_GPIO_CHIP_PATH, consumer="eink-display", config=config)
    return _request


def digital_write(pin: int, value: int) -> None:
    if pin not in _OUTPUT_PINS:
        return
    _lines().set_value(pin, Value.ACTIVE if value else Value.INACTIVE)


def digital_read(pin: int) -> int:
    if pin not in _INPUT_PINS:
        return 0
    return 1 if _lines().get_value(pin) == Value.ACTIVE else 0


def delay_ms(delaytime: int) -> None:
    time.sleep(delaytime / 1000.0)


def spi_writebyte(data) -> None:
    _spi.writebytes(data)


def spi_writebyte2(data) -> None:
    _spi.writebytes2(data)


def module_init(cleanup: bool = False) -> int:
    _lines()
    digital_write(PWR_PIN, 1)
    _spi.open(0, 0)
    _spi.max_speed_hz = 4000000
    _spi.mode = 0b00
    return 0


def module_exit(cleanup: bool = False) -> None:
    _spi.close()
    digital_write(RST_PIN, 0)
    digital_write(DC_PIN, 0)
    digital_write(PWR_PIN, 0)
    if cleanup and _request is not None:
        _request.release()
