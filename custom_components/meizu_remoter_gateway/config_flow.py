import voluptuous as vol
import logging
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.typing import DiscoveryInfoType
from .const import (
    DOMAIN, DEFAULT_PORT, DEVICES,
    REQUIRED_FIRMWARE_VERSION,
    CONF_UPDATE_INTERVAL,
    CONF_SERIALNO
)
from . import DeviceManager

_LOGGER = logging.getLogger(__name__)

ALREADY_IN_PROGRESS = "already_in_progress"


def version_check(version: str, required_version: str):
    len1 = len(version.split('.'))
    len2 = len(required_version.split('.'))
    version = version + '.0' * (len2-len1)
    required_version = required_version + '.0' * (len1-len2)
    for n in range(max(len1, len2)):
        if int(required_version.split('.')[n]) > int(version.split('.')[n]):
            return False
        elif int(version.split('.')[n]) > int(required_version.split('.')[n]):
            return True
        else:
            if n == max(len1, len2) - 1:
                return True


class MRGFlowHandler(ConfigFlow, domain=DOMAIN):
    def __init__(self):
        self._host: str | None = None
        self._port: int | None = None
        self._serialno: str | None = None

    async def async_step_user(self, user_input=None, error=None):
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input[CONF_PORT]
            manager = DeviceManager(self.hass, self._host, self._port)
            config_info = manager.open(False)
            manager.close()
            if config_info is not None:
                self._serialno = config_info["serialno"]
                version = config_info["version"]
                update_interval = config_info["update_interval"]
                if DOMAIN in self.hass.data and DEVICES in self.hass.data[DOMAIN] and \
                        self._serialno in self.hass.data[DOMAIN][DEVICES]:
                    return await self.async_step_user(error="already_configured")
                if not version_check(version, REQUIRED_FIRMWARE_VERSION):
                    return self.async_step_user(error="version_required")
                else:
                    return self.async_create_entry(
                        title=self._serialno,
                        data={
                            CONF_HOST: self._host,
                            CONF_PORT: self._port,
                            CONF_SERIALNO: self._serialno
                        },
                        options={
                            CONF_UPDATE_INTERVAL: update_interval
                        }
                    )
            else:
                return await self.async_step_user(error="connection_error")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self._host or vol.UNDEFINED): str,
                vol.Required(CONF_PORT, default=self._port or DEFAULT_PORT): vol.Coerce(int)
            }),
            errors={"base": error} if error else None,
            description_placeholders={"serialno": self._serialno}
        )

    async def async_step_discovery_confirm(self, user_input = None):
        if user_input is not None:
            manager = DeviceManager(self.hass, self._host, self._port)
            config_info = manager.open(False)
            manager.close()
            if config_info is not None:
                update_interval = config_info["update_interval"]
                return self.async_create_entry(
                    title=self._serialno,
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_SERIALNO: self._serialno
                    },
                    options={
                        CONF_UPDATE_INTERVAL: update_interval
                    }
                )
            else:
                return await self.async_step_user(error="connection_error")
        return self.async_show_form(
            step_id="discovery_confirm", description_placeholders={"serialno": self._serialno}
        )

    async def async_step_zeroconf(self, discovery_info: DiscoveryInfoType):
        host = discovery_info["host"]
        serialno = discovery_info["properties"]["serialno"]
        if DOMAIN in self.hass.data and DEVICES in self.hass.data[DOMAIN] and \
                serialno in self.hass.data[DOMAIN][DEVICES]:
            return self.async_abort(reason="already_configured")
        if DOMAIN in self.hass.data and ALREADY_IN_PROGRESS in self.hass.data[DOMAIN] and \
                serialno in self.hass.data[DOMAIN][ALREADY_IN_PROGRESS]:
            return self.async_abort(reason="already_in_progress")
        version = discovery_info["properties"]["version"]
        if not version_check(version, REQUIRED_FIRMWARE_VERSION):
            return self.async_abort(reason="version_required")
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        if ALREADY_IN_PROGRESS not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][ALREADY_IN_PROGRESS] = []
        self.hass.data[DOMAIN][ALREADY_IN_PROGRESS].append(serialno)
        port = discovery_info["port"]
        self._host = host
        self._port = port
        self._serialno = serialno
        return await self.async_step_discovery_confirm()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        update_interval = self.config_entry.options.get(CONF_UPDATE_INTERVAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=update_interval,
                ): vol.All(vol.Coerce(int)),
            }),
        )