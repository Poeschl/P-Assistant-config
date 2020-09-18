"""
A sensor platform which detects underruns and capped status from the official Raspberry Pi Kernel.
Minimal Kernel needed is 4.14+
"""
__version__ = '0.2.1'

import logging
import os

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_PROBLEM,
    BinarySensorEntity,
)

_LOGGER = logging.getLogger(__name__)

SYSFILE = "/sys/class/hwmon/hwmon0/in0_lcrit_alarm"
SYSFILE_LEGACY = "/sys/devices/platform/soc/soc:firmware/get_throttled"

UNDERVOLTAGE_STICKY_BIT = 1 << 16

DESCRIPTION_NORMALIZED = "Voltage normalized. Everything is working as intended."
DESCRIPTION_UNDER_VOLTAGE = "Under-voltage was detected. Consider getting a uninterruptible power supply for your Raspberry Pi."


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform."""
    if discovery_info is None:
        return

    if os.path.isfile(SYSFILE):
        under_voltage = UnderVoltage()
    elif os.path.isfile(SYSFILE_LEGACY):  # support older kernel
        under_voltage = UnderVoltage(legacy=True)
    else:
        _LOGGER.error(
            "Can't find the system class needed for this component, make sure that your kernel is recent and the hardware is supported."
        )
        return

    add_entities([RaspberryChargerBinarySensor(under_voltage)])


class RaspberryChargerBinarySensor(BinarySensorEntity):
    """Binary sensor representing the rpi power status."""

    def __init__(self, under_voltage):
        """Initialize the binary sensor."""
        self._under_voltage = under_voltage
        self._is_on = None
        self._last_is_on = False

    def update(self):
        """Update the state."""
        self._is_on = self._under_voltage.get()
        if self._is_on != self._last_is_on:
            if self._is_on:
                _LOGGER.warning(DESCRIPTION_UNDER_VOLTAGE)
            else:
                _LOGGER.warning(DESCRIPTION_NORMALIZED)
            self._last_is_on = self._is_on

    @property
    def name(self):
        """Return the name of the sensor."""
        return "RPi Power status"

    @property
    def is_on(self):
        """Return if there is a problem detected."""
        return self._is_on

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:raspberry-pi"

    @property
    def device_class(self):
        """Return the class of this device."""
        return DEVICE_CLASS_PROBLEM


class UnderVoltage:
    """Read under voltage status."""

    def __init__(self, legacy=False):
        """Initialize the under voltage bit reader."""
        self._legacy = legacy

    def get(self):
        """Get under voltage status."""
        # Using legacy get_throttled entry
        if self._legacy:
            throttled = open(SYSFILE_LEGACY).read()[:-1]
            _LOGGER.debug("Get throttled value: %s", throttled)
            return (
                int(throttled, base=16) & UNDERVOLTAGE_STICKY_BIT
                == UNDERVOLTAGE_STICKY_BIT
            )

        # Use new hwmon entry
        bit = open(SYSFILE).read()[:-1]
        _LOGGER.debug("Get under voltage status: %s", bit)
        return bit == "1"
