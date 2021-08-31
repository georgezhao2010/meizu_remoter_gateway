import logging
import threading
import time
import socket
import json
from .const import (
    DOMAIN,
    DEVICES,
    CONF_UPDATE_INTERVAL,
    CONF_SERIALNO,
    UPDATES,
    REMOVES,
    ADD_CB
)

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    ATTR_ENTITY_ID
)
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from .sensor import MRG_SENSORS, MRGSensor
from homeassistant.core import HomeAssistant

SERVICE_SEND_IR = "send_ir"
SERVICE_REMOVE_PAIR = "remove_pair"
ATTR_IR_CODE = "ir_code"
UN_SUBDISCRIPT = "un_subscript"
MANAGER = "manager"

SERVICE_SEND_IR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_IR_CODE): str
    }
)

SERVICE_REMOVE_PAIR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id
    }
)

_LOGGER = logging.getLogger(__name__)


async def update_listener(hass, config_entry):
    scan_interval = config_entry.options.get(CONF_UPDATE_INTERVAL)
    dm = hass.data[config_entry.entry_id][MANAGER]
    dm.send_message("setinterval", {"update_interval": scan_interval})


async def async_setup(hass: HomeAssistant, hass_config: dict):
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry):
    config = config_entry.data
    host = config[CONF_HOST]
    port = config[CONF_PORT]
    serialno = config[CONF_SERIALNO]
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if DEVICES not in hass.data[DOMAIN]:
        hass.data[DOMAIN][DEVICES] = {}
    hass.data[DOMAIN][DEVICES][serialno] = {}
    dm = DeviceManager(hass, host, port, config_entry)
    result = dm.open(True)
    if result is None:
        return False
    hass.data[DOMAIN][DEVICES][serialno][UPDATES] = {}
    hass.data[DOMAIN][DEVICES][serialno][REMOVES] = {}
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(config_entry, "sensor"))
    if config_entry.entry_id not in hass.data:
        hass.data[config_entry.entry_id] = {}
    hass.data[config_entry.entry_id][MANAGER] = dm

    options = {CONF_UPDATE_INTERVAL:result["update_interval"]}
    hass.config_entries.async_update_entry(config_entry, options=options)
    hass.data[config_entry.entry_id][UN_SUBDISCRIPT] = config_entry.add_update_listener(update_listener)

    def send_ir_handle(service):
        entity_id = service.data[ATTR_ENTITY_ID]
        ir_code = service.data[ATTR_IR_CODE]
        entity = hass.states.get(entity_id)
        if entity is not None:
            dm.send_message("irsend", {"device": entity.state, "ircode": ir_code})

    def remove_pair_handle(service):
        entity_id = service.data[ATTR_ENTITY_ID]
        entity = hass.states.get(entity_id)
        if entity is not None:
            dm.send_message("removepair", {"device": entity.state})

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_IR,
        send_ir_handle,
        schema=SERVICE_SEND_IR_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_PAIR,
        remove_pair_handle,
        schema=SERVICE_REMOVE_PAIR_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry):
    config = config_entry.data
    serialno = config[CONF_SERIALNO]
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
    unsub = hass.data[config_entry.entry_id][UN_SUBDISCRIPT]
    if unsub is not None:
        unsub()
    dm = hass.data[config_entry.entry_id][MANAGER]
    dm.close()
    hass.data.pop(config_entry.entry_id)
    hass.data[DOMAIN][DEVICES].pop(serialno)
    if len(hass.data[DOMAIN][DEVICES]) == 0:
        hass.data.pop(DOMAIN)
    return True


class DeviceManager(threading.Thread):
    def __init__(self, hass: HomeAssistant, host, port, config_entry=None):
        threading.Thread.__init__(self)
        self._lock = threading.Lock()
        self._socket = None
        self._config_entry = config_entry
        self._hass = hass
        if config_entry is not None:
            self._serialno = self._config_entry.data[CONF_SERIALNO]
        self._host = host
        self._port = port
        self._is_run = False
        self._timeout_counter = 0

    def remoter_callbacks(self, address, cb_type):
        if DEVICES in self._hass.data[DOMAIN] and self._serialno in self._hass.data[DOMAIN][DEVICES] and \
                UPDATES in self._hass.data[DOMAIN][DEVICES][self._serialno] and \
                address in self._hass.data[DOMAIN][DEVICES][self._serialno][cb_type]:
            return self._hass.data[DOMAIN][DEVICES][self._serialno][cb_type][address]
        return None

    def remoter_updates(self, address):
        return self.remoter_callbacks(address, UPDATES)

    def remoter_removes(self, address):
        return self.remoter_callbacks(address, REMOVES)

    def add_sensors(self, init_data):
        async_add_entities = self._hass.data[DOMAIN][DEVICES][self._serialno][ADD_CB]
        sensors = []
        for key in MRG_SENSORS.keys():
            sensors.append(MRGSensor(self._hass, key, self._serialno, init_data))
        async_add_entities(sensors)

    def process_message(self, msg):
        jdata = json.loads(msg.decode("utf-8"))
        if jdata is not None and "type" in jdata:
            if jdata["type"] == "heartbeat":
                self._timeout_counter = 0
            elif jdata["type"] == "update":
                data = jdata["data"]
                updates = self.remoter_updates(data["device"])
                if updates is None:  # not configured
                    if data["available"] == 1:  # availiable
                        self.add_sensors(data)
                else:
                    for update in updates:
                        update(data)
            elif jdata["type"] == "setinterval":
                data = jdata["data"]
                options = {CONF_UPDATE_INTERVAL: data["update_interval"]}
                self._hass.config_entries.async_update_entry(self._config_entry, options=options)
            elif jdata["type"] == "removepair":
                data = jdata["data"]
                removes = self.remoter_removes(data["device"])
                if removes is not None:
                    for remove in removes:
                        remove()
                self._hass.data[DOMAIN][DEVICES][self._serialno][UPDATES].pop(data["device"])
                self._hass.data[DOMAIN][DEVICES][self._serialno][REMOVES].pop(data["device"])
            else:
                _LOGGER.warning(f"Received a unknown message")
        else:
            _LOGGER.warning(f"Received a invalid message")

    def run(self):
        while self._is_run:
            config_info = None
            with self._lock:
                while self._socket is None:
                    _LOGGER.debug("Try to connect to MEIZU remoter gateway at %s:%d", self._host, self._port)
                    config_info = self.open(False)
                    if config_info is None:
                        time.sleep(3)
                    if not self._is_run:
                        if self._socket is not None:
                            self._socket.close()
                        return
            if config_info is not None:
                options = {CONF_UPDATE_INTERVAL: config_info["update_interval"]}
                self._hass.config_entries.async_update_entry(self._config_entry, options=options)
            self.send_message("subscribe")
            self._timeout_counter = 0
            while self._is_run:
                try:
                    msg = self._socket.recv(1024)
                    if not self._is_run:
                        break
                    msg_len = len(msg)
                    if msg_len == 0:
                        raise socket.error
                    _LOGGER.debug(f"Received message {msg}")
                    self.process_message(msg)
                except socket.timeout:
                    self._timeout_counter = self._timeout_counter + 1
                    if self._timeout_counter >= 20:
                        _LOGGER.debug(f"Heartbeat timeout detected, reconnecting")
                        self.close(run=True)
                        break
                    if self._timeout_counter % 2 == 0:
                        self.send_message("heartbeat")
                    pass
                except socket.error:
                    _LOGGER.debug(f"Except socket.error {socket.error.errno} raised in socket.recv()")
                    self.close(run=True)
                    break

    def open(self, start_thread):
        config_info = None
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(10)
            self._socket.connect((self._host, self._port))
            _LOGGER.debug(f"Socket connected")
            self._socket.send("{\"type\":\"config_info\"}".encode("utf-8"))
            msg = self._socket.recv(512)
            _LOGGER.debug(f"config_info Received {msg}")
            result = json.loads(msg.decode("utf-8"))
            if "type" in result and result["type"] == "config_info" and "data" in result:
                config_info = result["data"]
        except socket.timeout:
            _LOGGER.debug(f"Socket connect timeout")
            self._socket.close()
            self._socket = None
        except socket.error:
            _LOGGER.debug(f"Socket connect error {socket.error}")
            self._socket.close()
            self._socket = None
        if start_thread:
            self._is_run = True
            threading.Thread.start(self)
        return config_info

    def close(self, run=False):
        self._is_run = run
        with self._lock:
            if self._socket is not None:
                self._socket.close()
                self._socket = None

    def send_message(self, msg_type, data=None):
        if data is not None:
            msg = "{\"type\":\"" + msg_type + "\",\"data\":" + f"{json.dumps(data)}" + "}"
        else:
            msg = "{\"type\":\"" + msg_type + "\"}"
        with self._lock:
            try:
                _LOGGER.debug(f"Send message {msg}")
                self._socket.send(msg.encode("utf-8"))
            except:
                pass