import logging
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_registry import async_entries_for_device
from homeassistant.const import(
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_BATTERY,
    TEMP_CELSIUS,
    PERCENTAGE,
)
from .const import DOMAIN, CONF_SERIALNO, UPDATES, REMOVES, DEVICES, ADD_CB

_LOGGER = logging.getLogger(__name__)

MRG_SENSORS = {
    "remoter": {
        "icon": "hass:remote",
        "key_path": ["device"],
    },
    "temperature": {
        "name": "Temperature",
        "device_class": DEVICE_CLASS_TEMPERATURE,
        "key_path": ["status", "temperature"],
        "unit": TEMP_CELSIUS
    },
    "humidity": {
        "name": "Humidity",
        "device_class": DEVICE_CLASS_HUMIDITY,
        "key_path": ["status", "humidity"],
        "unit": PERCENTAGE
    },
    "battery": {
        "name": "Battery",
        "device_class": DEVICE_CLASS_BATTERY,
        "key_path": ["status", "battery"],
        "unit": PERCENTAGE
    },
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    serialno = config_entry.data[CONF_SERIALNO]
    hass.data[DOMAIN][DEVICES][serialno][ADD_CB] = async_add_entities


class MRGSensor(Entity):
    def __init__(self, hass, sensor_type, serialno, init_data):
        self._hass = hass
        self._real_address = init_data["device"]
        self._address = self._real_address.replace(":", "").lower()
        self._base_info = MRG_SENSORS[sensor_type]
        self._device_info = {
            "identifiers": {(DOMAIN, self._address)},
            "manufacturer": init_data["status"]["manufacturer"],
            "model": init_data["status"]["model"],
            "sw_version": init_data["status"]["fireware"],
            "name": f"MEIZU Remoter {self._real_address}"
        }
        self._state = self._get_state(init_data)
        self._unique_id = f"{DOMAIN}.{serialno}_{self._address}_{sensor_type}"
        self.entity_id = self._unique_id
        self._available = True
        if self._real_address not in self._hass.data[DOMAIN][DEVICES][serialno][UPDATES]:
            self._hass.data[DOMAIN][DEVICES][serialno][UPDATES][self._real_address] = []
        if self._real_address not in self._hass.data[DOMAIN][DEVICES][serialno][REMOVES]:
            self._hass.data[DOMAIN][DEVICES][serialno][REMOVES][self._real_address] = []
        self._hass.data[DOMAIN][DEVICES][serialno][UPDATES][self._real_address].append(self.update_data)
        self._hass.data[DOMAIN][DEVICES][serialno][REMOVES][self._real_address].append(self.remove_entity)

    @property
    def name(self):
        if self._base_info.get('name') is not None:
            return f"MEIZU Remoter {self._real_address} {self._base_info.get('name')}"
        else:
            return f"MEIZU Remoter {self._real_address}"

    @property
    def icon(self):
        return self._base_info.get('icon')

    @property
    def device_class(self):
        return self._base_info.get('device_class')

    @property
    def state(self):
        return self._state

    @property
    def device_info(self):
        return self._device_info

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._available

    @property
    def unit_of_measurement(self):
        return self._base_info.get('unit')

    def _get_state(self, device_data):
        value = device_data
        for key in self._base_info["key_path"]:
            if value is None:
                break
            value = value.get(key)
        return value

    def update_data(self, statu_dict):
        self._state = self._get_state(statu_dict)
        self._available = (statu_dict["available"] == 1)
        self.schedule_update_ha_state()

    def remove_entity(self):
        self._hass.async_create_task(self.async_remove_entity())

    async def async_remove_entity(self):
        entity_registry = await self._hass.helpers.entity_registry.async_get_registry()
        entity_entry = entity_registry.async_get(self.entity_id)
        if not entity_entry:
            await self.async_remove(force_remove=True)
            return
        device_registry = await self._hass.helpers.device_registry.async_get_registry()
        device_entry = device_registry.async_get(entity_entry.device_id)
        if not device_entry:
            entity_registry.async_remove(self.entity_id)
            return
        if (
                len(
                    async_entries_for_device(
                        entity_registry,
                        entity_entry.device_id,
                        include_disabled_entities=True,
                    )
                )
                == 1):
            device_registry.async_remove_device(device_entry.id)
            return
        entity_registry.async_remove(self.entity_id)



