"""The cert_expiry component."""
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_CA_CERT, DEFAULT_PORT, DOMAIN
from .errors import TemporaryFailure, ValidationFailure
from .helper import get_cert_expiry_timestamp

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=12)


async def async_setup(hass, config):
    """Platform setup, do nothing."""
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Load the saved entities."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    ca_cert = entry.data.get(CONF_CA_CERT, None)

    coordinator = CertExpiryDataUpdateCoordinator(hass, host, port, ca_cert)
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    if entry.unique_id is None:
        hass.config_entries.async_update_entry(entry, unique_id=f"{host}:{port}")

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")


class CertExpiryDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Cert Expiry data from single endpoint."""

    def __init__(self, hass, host, port, ca_cert):
        """Initialize global Cert Expiry data updater."""
        self.host = host
        self.port = port
        self.ca_cert = ca_cert
        self.cert_error = None
        self.is_cert_valid = False

        display_port = f":{port}" if port != DEFAULT_PORT else ""
        name = f"{self.host}{display_port}"

        super().__init__(
            hass, _LOGGER, name=name, update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch certificate."""
        try:
            timestamp = await get_cert_expiry_timestamp(
                self.hass, self.host, self.port, self.ca_cert
            )
        except TemporaryFailure as err:
            raise UpdateFailed(err.args[0])
        except ValidationFailure as err:
            self.cert_error = err
            self.is_cert_valid = False
            _LOGGER.error("Certificate validation error: %s [%s]", self.host, err)
            return None

        self.cert_error = None
        self.is_cert_valid = True
        return timestamp
