import logging

import asyncio
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.fan import (
    FanEntity, PLATFORM_SCHEMA, SPEED_OFF, SUPPORT_SET_SPEED, SUPPORT_OSCILLATE, SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH)
from homeassistant.const import (
    CONF_NAME, STATE_ON)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.percentage import ordered_list_item_to_percentage, percentage_to_ordered_list_item
from .const import DEFAULT_NAME, CONF_REMOTE_ENTITY, CONF_COMMAND_ON_OFF, CONF_COMMAND_SPEED, CONF_COMMAND_OSCILLATE, CONF_COMMAND_DEVICE, \
    DEFAULT_DELAY

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_REMOTE_ENTITY): cv.string,
    vol.Required(CONF_COMMAND_DEVICE): cv.string,
    vol.Required(CONF_COMMAND_ON_OFF): cv.string,
    vol.Required(CONF_COMMAND_SPEED): cv.string,
    vol.Required(CONF_COMMAND_OSCILLATE): cv.string,
})

FAN_SPEEDS = [SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH]


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IR Fan platform."""
    async_add_entities([IrFan(hass, config)])


class IrFan(FanEntity, RestoreEntity):

    def __init__(self, hass, config):
        self.hass = hass

        self._name = config.get(CONF_NAME)
        self._remote_entity = config.get(CONF_REMOTE_ENTITY)

        self._unique_id = f"{self._remote_entity}_{self._name}"

        self._device_name = config.get(CONF_COMMAND_DEVICE)
        self._commands = {
            CONF_COMMAND_ON_OFF: config.get(CONF_COMMAND_ON_OFF),
            CONF_COMMAND_SPEED: config.get(CONF_COMMAND_SPEED),
            CONF_COMMAND_OSCILLATE: config.get(CONF_COMMAND_OSCILLATE),
        }

        self._speed = SPEED_LOW
        self._last_on_speed = SPEED_LOW
        self._oscillating = False

        self._current_speed = SPEED_OFF
        self._current_oscillating = True
        self._current_on = self.is_on

        self._temp_lock = asyncio.Lock()

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()

        if last_state is not None:
            if 'speed' in last_state.attributes:
                self._speed = last_state.attributes['speed']

            if 'last_on_speed' in last_state.attributes:
                self._last_on_speed = last_state.attributes['last_on_speed']
                self._current_speed = self._last_on_speed

            if 'oscillating' in last_state.attributes:
                self._oscillating = last_state.attributes['oscillating']
                self._current_oscillating = self._oscillating

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def supported_features(self):
        return SUPPORT_SET_SPEED + SUPPORT_OSCILLATE

    @property
    def available(self) -> bool:
        return self.hass.states.get(self._remote_entity) is not None and self.hass.states.get(self._remote_entity).state == STATE_ON

    @property
    def is_on(self):
        return self._current_speed != SPEED_OFF

    @property
    def percentage(self):
        if self._current_speed == SPEED_OFF:
            return 0
        else:
            return ordered_list_item_to_percentage(FAN_SPEEDS, self._current_speed)

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return len(FAN_SPEEDS)

    @property
    def oscillating(self):
        return self._current_oscillating

    @property
    def last_on_speed(self):
        return self._last_on_speed

    @property
    def device_state_attributes(self) -> dict:
        """Platform specific attributes."""
        return {
            'last_on_speed': self._last_on_speed,
            'remote_entity': self._remote_entity,
        }

    async def async_set_percentage(self, percentage: int):
        """Set the speed of the fan."""
        speed = percentage_to_ordered_list_item(FAN_SPEEDS, percentage)

        if percentage > 0:
            self._last_on_speed = speed
            self._speed = speed
        else:
            self._speed = SPEED_OFF

        await self.send_command()
        await self.async_update_ha_state()

    async def async_oscillate(self, oscillating: bool) -> None:
        """Set oscillation of the fan."""
        self._oscillating = oscillating

        await self.send_command()
        await self.async_update_ha_state()

    async def async_turn_on(self, speed: str = None, **kwargs):
        """Turn on the fan."""
        if speed is None:
            speed = FAN_SPEEDS[0]

        await self.async_set_percentage(ordered_list_item_to_percentage(FAN_SPEEDS, speed))

    async def async_turn_off(self):
        """Turn off the fan."""
        await self.async_set_percentage(0)

    async def send_command(self):

        async with self._temp_lock:
            speed = self._speed.lower()
            last_speed = self._current_speed
            oscillating = self._oscillating
            last_oscillating = self._current_oscillating

            if speed == SPEED_OFF:
                if self.is_on:
                    await self.__send(self._commands[CONF_COMMAND_ON_OFF])
                    self._last_on_speed = last_speed
                self._current_speed = SPEED_OFF
                return

            else:
                if not self.is_on:
                    await self.__send(self._commands[CONF_COMMAND_ON_OFF])
                    last_speed = self._last_on_speed

                if FAN_SPEEDS.index(speed) > FAN_SPEEDS.index(last_speed):
                    speed_command_times = FAN_SPEEDS.index(speed) - FAN_SPEEDS.index(last_speed)
                elif FAN_SPEEDS.index(speed) < FAN_SPEEDS.index(last_speed):
                    # Go around the speed wheel by adding 3 to the wanted speed
                    speed_command_times = FAN_SPEEDS.index(speed) + 3 - FAN_SPEEDS.index(last_speed)
                else:
                    speed_command_times = 0

                for _ in range(speed_command_times):
                    await self.__send(self._commands[CONF_COMMAND_SPEED])
                self._current_speed = speed

            if self.is_on and oscillating != last_oscillating:
                await self.__send(self._commands[CONF_COMMAND_OSCILLATE])
                self._current_oscillating = oscillating

    async def __send(self, command):
        target = {
            'entity_id': self._remote_entity
        }

        service_data = {
            'delay_secs': DEFAULT_DELAY,
            'device': self._device_name,
            'command': command
        }

        await self.hass.services.async_call(
            'remote', 'send_command', target=target, service_data=service_data)
