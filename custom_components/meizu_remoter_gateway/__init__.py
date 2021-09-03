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
SERVICE_BIND = "bind"
SERVICE_REMOVE_BIND = "remove_bind"
ATTR_KEY = "key"
ATTR_IR_CODE = "ir_code"
ATTR_SERIAL_NO = "serial_no"
UN_SUBDISCRIPT = "un_subscript"
MANAGER = "manager"

SERVICE_SEND_IR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_KEY): str,
        vol.Optional(ATTR_IR_CODE): str
    }
)

SERVICE_BIND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SERIAL_NO): str
    }
)

SERVICE_REMOVE_BIND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id
    }
)

_LOGGER = logging.getLogger(__name__)



async def update_listener(hass, config_entry):
    scan_interval = config_entry.options.get(CONF_UPDATE_INTERVAL)
    serialno = config_entry.data.get(CONF_SERIALNO)
    dm = hass.data[DOMAIN][DEVICES][serialno][MANAGER]
    dm.send_message("setinterval", data={"update_interval": scan_interval})


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
    hass.data[DOMAIN][DEVICES][serialno][MANAGER] = dm
    hass.data[DOMAIN][DEVICES][serialno][UN_SUBDISCRIPT] = config_entry.add_update_listener(update_listener)
    options = {CONF_UPDATE_INTERVAL:result["update_interval"]}
    hass.config_entries.async_update_entry(config_entry, options=options)
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(config_entry, "sensor"))

    def get_address_from_entity_id(entity_id):
        serial_no = None
        address = None
        s_entity_id = entity_id.split(".", 1)
        if len(s_entity_id) == 2 and s_entity_id[1] is not None:
            rets = s_entity_id[1].split("_", 3)
            if len(rets) == 3 and rets[2] == "remoter" and len(rets[1]) == 12:
                address = [rets[1][i:i+2] for i in range(0, len(rets[1]), 2)]
                address = ":".join(n for n in address)
                serial_no = rets[0].upper()
        return serial_no, address

    def send_ir_handle(service):
        entity_id = service.data[ATTR_ENTITY_ID]
        key = service.data[ATTR_KEY]
        ir_code = service.data[ATTR_IR_CODE]
        serial_no, address = get_address_from_entity_id(entity_id)
        if address is not None and serial_no in hass.data[DOMAIN][DEVICES]:
            manager = hass.data[DOMAIN][DEVICES][serial_no][MANAGER]
            if ir_code is None:
                manager.send_message("irsend", data={"device": address, "key": key})
            else:
                manager.send_message("irsend", data={"device": address, "key": key, "ircode": ir_code})
        else:
            _LOGGER.error(f"Service called with an invalid entity ID")

    def bind_handle(service):
        serial_no = service.data[ATTR_SERIAL_NO]
        if serial_no in hass.data[DOMAIN][DEVICES]:
            manager = hass.data[DOMAIN][DEVICES][serial_no][MANAGER]
            manager.send_message("bind")
        else:
            _LOGGER.error(f"Service called with an invalid gateway serial number")

    def remove_bind_handle(service):
        entity_id = service.data[ATTR_ENTITY_ID]
        serial_no, address = get_address_from_entity_id(entity_id)
        if address is not None and serial_no in hass.data[DOMAIN][DEVICES]:
            manager = hass.data[DOMAIN][DEVICES][serial_no][MANAGER]
            manager.send_message("removebind", data={"device": address})
        else:
            _LOGGER.error(f"Service called with an invalid entity ID")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_IR,
        send_ir_handle,
        schema=SERVICE_SEND_IR_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BIND,
        bind_handle,
        schema=SERVICE_BIND_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_BIND,
        remove_bind_handle,
        schema=SERVICE_REMOVE_BIND_SCHEMA,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry):
    config = config_entry.data
    serialno = config[CONF_SERIALNO]
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
    unsub = hass.data[DOMAIN][DEVICES][serialno][UN_SUBDISCRIPT]
    if unsub is not None:
        unsub()
    dm = hass.data[DOMAIN][DEVICES][serialno][MANAGER]
    dm.close()
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
        else:
            self._serialno = "none"
        self._host = host
        self._port = port
        self._is_run = False
        self._timeout_counter = 0

    class Bind(Exception):
        def __str__(self):
            return "Can not start bind mode at this time"

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
            elif jdata["type"] == "removebind":
                data = jdata["data"]
                removes = self.remoter_removes(data["device"])
                if removes is not None:
                    for remove in removes:
                        remove()
                if self._serialno in self._hass.data[DOMAIN][DEVICES]:
                    self._hass.data[DOMAIN][DEVICES][self._serialno][UPDATES].pop(data["device"])
                    self._hass.data[DOMAIN][DEVICES][self._serialno][REMOVES].pop(data["device"])
            elif jdata["type"] == "bind":
                data = jdata["data"]
                status = data["status"]
                if status == 0:
                    raise DeviceManager.Bind
            else:
                _LOGGER.warning(f"Gateway[{self._serialno}] received an unknown message")
        else:
            _LOGGER.warning(f"Gateway[{self._serialno}] received an invalid message")

    def run(self):
        while self._is_run:
            config_info = None
            with self._lock:
                while self._socket is None:
                    _LOGGER.debug(f"Gateway[{self._serialno}] attempt to connect to {self._host}:{self._port}")
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
                    _LOGGER.debug(f"Gateway[{self._serialno}] Received message {msg}")
                    self.process_message(msg)
                except socket.timeout:
                    self._timeout_counter = self._timeout_counter + 1
                    if self._timeout_counter >= 20:
                        _LOGGER.debug(f"Gateway[{self._serialno}] Heartbeat timeout detected, reconnecting")
                        self.close(run=self._is_run)
                        break
                    if self._timeout_counter % 2 == 0:
                        self.send_message("heartbeat")
                    pass
                except socket.error:
                    self.close(run=self._is_run)
                    break


    def open(self, start_thread):
        config_info = None
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(10)
            self._socket.connect((self._host, self._port))
            _LOGGER.debug(f"Gateway[{self._serialno}] Socket connected")
            msg = self.send_message("config_info", reply=True);
            result = json.loads(msg.decode("utf-8"))
            if "type" in result and result["type"] == "config_info" and "data" in result:
                config_info = result["data"]
        except socket.timeout:
            _LOGGER.debug(f"Gateway[{self._serialno}] Socket connect timeout")
            self._socket.close()
            self._socket = None
        except socket.error:
            _LOGGER.debug(f"Gateway[{self._serialno}] Socket connect error {socket.error}")
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

    def send_message(self, msg_type, data=None, reply=False):
        reply_msg = None;
        if data is not None:
            msg = "{\"type\":\"" + msg_type + "\",\"data\":" + f"{json.dumps(data)}" + "}"
        else:
            msg = "{\"type\":\"" + msg_type + "\"}"
        with self._lock:
            try:
                _LOGGER.debug(f"Gateway[{self._serialno}] Send message {msg}")
                self._socket.send(msg.encode("utf-8"))
                if reply and not self._is_run:
                    reply_msg = self._socket.recv(512)
            except:
                pass
        return reply_msg
