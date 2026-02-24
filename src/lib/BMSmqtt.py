from common.credentials import *
from common.logger import Logger
import asyncio
import machine 
import utime
import ubinascii
import ujson as json 
from umqtt.robust import MQTTClient

# ───────────────────────────────────────────────
#          Base Entity Class
# ───────────────────────────────────────────────
class Entity:
    def __init__(self, name, entity_id=None):
        self.name = name
        self.entity_id = entity_id or name.lower().replace(" ", "_")
        self.unique_id = None
        self.state_topic = None
        self.device_info = None
        self.bmsmqtt_dev = get_BMSmqtt()
        
        # NEW: Flag to prevent state publishing until discovery config has been sent
        # This avoids HA receiving state JSON keys for entities it doesn't know about yet
        self.discovered = False

    def get_discovery_payload(self):
        raise NotImplementedError

    def get_discovery_topic(self, component):
        return f"homeassistant/{component}/{self.unique_id}/config"

    def get_state_value(self):
        return None


# ───────────────────────────────────────────────
#          Sensor
# ───────────────────────────────────────────────
class Sensor(Entity):
    def __init__(self, name, unit=None, device_class=None, icon=None, sub_device=None):
        super().__init__(name)
        self.unit = unit
        self.device_class = device_class
        self.icon = icon
        self.value = 0.0
        self.sub_device = sub_device # e.g.{"name": "Slave", "id": "slave_x"}
    
    def get_discovery_payload(self):
        payload = {
            "name": f"{self.device_info['name']} {self.name}",
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "value_template": f"{{{{ value_json.{self.entity_id} }}}}"
        }
        if self.unit:
            payload["unit_of_measurement"] = self.unit
        if self.device_class:
            payload["device_class"] = self.device_class
        if self.icon:
            payload["icon"] = self.icon

        if self.sub_device:
            payload["device"] = {
                "name": self.sub_device["name"],
                "identifiers": [f"{self.bmsmqtt_dev.device_id}_{self.sub_device['id']}"],
                "via_device": self.bmsmqtt_dev.device_id,
                "model": "BMS Submodule",
                "manufacturer": "DIY",
            }
        else:
            payload["device"] = self.device_info

        return payload
    
    def get_state_value(self):
        return self.value
    
    def set_value(self, val):
        self.value = val


# ───────────────────────────────────────────────
#          Number
# ───────────────────────────────────────────────
class Number(Entity):
    def __init__(self, name, min_val=0, max_val=100, step=1, default=None, unit=None,
                 mode="slider", sub_device=None, cb=None):
        super().__init__(name)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.unit = unit
        self.mode = mode
        self.value = default if default is not None else (min_val + max_val) / 2
        self.command_topic = None
        self.sub_device = sub_device
        self.cb = cb
    
    def get_discovery_payload(self):
        payload = {
            "name": f"{self.device_info['name']} {self.name}",
            "unique_id": self.unique_id,
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "value_template": f"{{{{ value_json.{self.entity_id} }}}}",
            "min": self.min_val,
            "max": self.max_val,
            "step": self.step,
            "mode": self.mode
        }
        if self.unit:
            payload["unit_of_measurement"] = self.unit

        if self.sub_device:
            payload["device"] = {
                "name": self.sub_device["name"],
                "identifiers": [f"{self.bmsmqtt_dev.device_id}_{self.sub_device['id']}"],
                "via_device": self.bmsmqtt_dev.device_id,
                "model": "BMS Submodule",
                "manufacturer": "DIY",
            }
        else:
            payload["device"] = self.device_info

        return payload
    
    def get_state_value(self):
        return self.value
    
    def set_value(self, val):
        try:
            v = float(val)
            self.value = max(self.min_val, min(self.max_val, v))
            if self.cb:
                self.cb(self.value)    
        except (ValueError, TypeError):
            pass


# ───────────────────────────────────────────────
#          Switch
# ───────────────────────────────────────────────
class Switch(Entity):
    """Home Assistant Switch entity (controllable ON/OFF)"""
    
    def __init__(self, name):
        super().__init__(name)
        self.value = False
        self.command_topic = None
    
    def get_discovery_payload(self):
        payload = {
            "name": f"{self.device_info['name']} {self.name}",
            "unique_id": self.unique_id,
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "value_template": f"{{{{ value_json.{self.entity_id} }}}}",
            "payload_on": "ON",
            "payload_off": "OFF",
            "state_on": "ON",
            "state_off": "OFF",
            "device": self.device_info
        }
        return payload
    
    def get_state_value(self):
        return "ON" if self.value else "OFF"
    
    def set_value(self, val):
        if isinstance(val, str):
            val = val.upper()
            self.value = (val == "ON" or val == "TRUE" or val == "1")
        elif isinstance(val, (int, float)):
            self.value = bool(val)
        else:
            self.value = bool(val)


# ───────────────────────────────────────────────
#          BinarySensor
# ───────────────────────────────────────────────
class BinarySensor(Entity):
    """Home Assistant Binary Sensor (read-only ON/OFF state)"""
    
    def __init__(self, name, device_class=None, icon=None, sub_device=None):
        super().__init__(name)
        self.value = False
        self.device_class = device_class
        self.icon = icon
        self.sub_device = sub_device
    
    def get_discovery_payload(self):
        payload = {
            "name": f"{self.device_info['name']} {self.name}",
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "value_template": f"{{{{ value_json.{self.entity_id} }}}}",
            "payload_on": "ON",
            "payload_off": "OFF",
        }
        if self.device_class:
            payload["device_class"] = self.device_class
        if self.icon:
            payload["icon"] = self.icon

        if self.sub_device:
            payload["device"] = {
                "name": self.sub_device["name"],
                "identifiers": [f"{self.bmsmqtt_dev.device_id}_{self.sub_device['id']}"],
                "via_device": self.bmsmqtt_dev.device_id,
                "model": "BMS Submodule",
                "manufacturer": "DIY",
            }
        else:
            payload["device"] = self.device_info
        return payload
    
    def get_state_value(self):
        return "ON" if self.value else "OFF"
    
    def set_value(self, val):
        if isinstance(val, str):
            val = val.upper()
            self.value = (val == "ON" or val == "TRUE" or val == "1")
        else:
            self.value = bool(val)


# ───────────────────────────────────────────────
#          Select
# ───────────────────────────────────────────────
class Select(Entity):
    """Home Assistant Select entity (dropdown with options)"""
    
    def __init__(self, name, options, default=None):
        super().__init__(name)
        self.options = options
        self.value = default if default in options else options[0]
        self.command_topic = None
    
    def get_discovery_payload(self):
        payload = {
            "name": f"{self.device_info['name']} {self.name}",
            "unique_id": self.unique_id,
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "value_template": f"{{{{ value_json.{self.entity_id} }}}}",
            "options": self.options,
            "device": self.device_info
        }
        return payload
    
    def get_state_value(self):
        return self.value
    
    def get_numeric_value(self):
        try:
            return int(self.value)
        except ValueError:
            return None
    def set_numeric_value(self, val:int):
        if str(val) in self.options:
            self.value = str(val)
        else: 
            pass

    def set_value(self, val):
        if val in self.options:
            self.value = val
        else:
            pass


# ───────────────────────────────────────────────
#          Text 
# ───────────────────────────────────────────────
class Text(Entity):
    """
    Home Assistant Text entity (free-form text input/output)
    """
    
    def __init__(self, name, default="", max_length=255, sub_device=None):
        super().__init__(name)
        self.value = default
        self.max_length = max_length
        self.command_topic = None
        self.sub_device = sub_device
    
    def get_discovery_payload(self):
        payload = {
            "name": f"{self.device_info['name']} {self.name}",
            "unique_id": self.unique_id,
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "value_template": f"{{{{ value_json.{self.entity_id} }}}}",
            "max": self.max_length,
            "mode": "text",
        }
        if self.sub_device:
            payload["device"] = {
                "name": self.sub_device["name"],
                "identifiers": [f"{self.bmsmqtt_dev.device_id}_{self.sub_device['id']}"],
                "via_device": self.bmsmqtt_dev.device_id,
                "model": "BMS Submodule",
                "manufacturer": "DIY",
            }
        else:
            payload["device"] = self.device_info
        return payload
    
    def get_state_value(self):
        return self.value
    
    def set_value(self, val):
        if isinstance(val, str):
            self.value = val[:self.max_length]
        else:
            self.value = str(val) if val is not None else ""


# ───────────────────────────────────────────────
#          BMSmqtt
# ───────────────────────────────────────────────
class BMSmqtt:
    def __init__(self,
                 device_name=MQTT_DEVICE_NAME,
                 device_id=MQTT_DEVICE_ID,
                 mqtt_broker=MQTT_BROKER,
                 mqtt_port=MQTT_PORT,
                 mqtt_user=MQTT_USER,
                 mqtt_password=MQTT_PASSWORD,
                 base_topic=None,
                 update_interval=60,
                 discovery_scan_interval=30):   # ← NEW configurable (default 30s)

        self.log = Logger()
        self.device_name = device_name
        self.device_id = device_id
        self.base_topic = base_topic or f"homeassistant/{device_id}"
        self.update_interval = update_interval
        self.discovery_scan_interval = discovery_scan_interval   # seconds
        self.availability_topic = f"{self.base_topic}/status"

        self.entities = []
        self.state_topic = f"{self.base_topic}/state"

        self.device_info = {
            "identifiers": [device_id],
            "name": device_name,
            "manufacturer": "DIY",
            "model": "ESP32 MicroPython"
        }

        self.mqtt_client = None
        self.mqtt_broker = mqtt_broker
        self.mqttport = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.client_id = ubinascii.hexlify(machine.unique_id())
        self.connected = False

        self.has_undiscovered_entities = True
        self.last_discovery_scan = 0

    def _connect_mqtt(self):
        self.mqtt_client = MQTTClient(
            self.client_id, self.mqtt_broker, port=self.mqttport,
            user=self.mqtt_user or None, password=self.mqtt_password or None, keepalive=60)
        self.mqtt_client.set_last_will(self.availability_topic, b"offline", retain=True, qos=0)
        self.mqtt_client.set_callback(self._on_message)

        self.log.info("Connecting MQTT...")
        try:
            self.mqtt_client.connect(clean_session=False)
            self.log.info("MQTT connected")
            self.mqtt_client.publish(self.availability_topic, b"online", retain=True, qos=0)
            self._subscribe_all_commands()
            self.connected = True
        except Exception as e:
            self.log.warn(f"MQTT connect failed: {e}")

    def _subscribe_all_commands(self):
        if not self.mqtt_client: return
        for entity in self.entities:
            if hasattr(entity, "command_topic") and entity.command_topic:
                try:
                    self.mqtt_client.subscribe(entity.command_topic, qos=0)
                except Exception as e:
                    self.log.warn(f"Subscribe failed: {e}")

    def add_entity(self, entity: Entity):
        entity.unique_id = f"{self.device_id}_{entity.entity_id}"
        entity.state_topic = self.state_topic
        entity.device_info = self.device_info

        if hasattr(entity, "command_topic") and getattr(entity, "command_topic", None) is None:
            entity.command_topic = f"{self.base_topic}/set/{entity.entity_id}"

        self.entities.append(entity)
        self.has_undiscovered_entities = True 
        self.log.info(f"Entity added: {entity.name} (auto-discovery enabled)")
        return entity

    def _publish_discovery(self, entity, component):
        topic = entity.get_discovery_topic(component)
        payload = json.dumps(entity.get_discovery_payload())
        self.mqtt_client.publish(topic, payload, retain=True, qos=1)
        entity.discovered = True
        self.log.info(f"Discovery published: {entity.name}")

    def publish_discovery(self):
        self.log.info(f"Initial discovery for {len(self.entities)} entities...")
        for entity in self.entities:
            if   isinstance(entity, Sensor):       component = "sensor"
            elif isinstance(entity, Number):       component = "number"
            elif isinstance(entity, Switch):       component = "switch"
            elif isinstance(entity, BinarySensor): component = "binary_sensor"
            elif isinstance(entity, Select):       component = "select"
            elif isinstance(entity, Text):         component = "text"
            else: continue
            self._publish_discovery(entity, component)

    def publish_pending_discoveries(self):
        pending = [e for e in self.entities if not e.discovered]
        if not pending:
            self.has_undiscovered_entities = False
            return 0

        self.log.info(f"Publishing {len(pending)} undiscovered entities")
        count = 0
        for entity in pending:
            if   isinstance(entity, Sensor):       component = "sensor"
            elif isinstance(entity, Number):       component = "number"
            elif isinstance(entity, Switch):       component = "switch"
            elif isinstance(entity, BinarySensor): component = "binary_sensor"
            elif isinstance(entity, Select):       component = "select"
            elif isinstance(entity, Text):         component = "text"
            else: continue
            self._publish_discovery(entity, component)
            count += 1

        self.has_undiscovered_entities = any(not e.discovered for e in self.entities)
        return count

    def publish_runtime_entity(self, entity: Entity):
        if isinstance(entity, Sensor):       component = "sensor"
        elif isinstance(entity, Number):     component = "number"
        elif isinstance(entity, Switch):     component = "switch"
        elif isinstance(entity, BinarySensor): component = "binary_sensor"
        elif isinstance(entity, Select):     component = "select"
        elif isinstance(entity, Text):       component = "text"
        else: return
        self._publish_discovery(entity, component)
        self.publish_state()

    def _on_message(self, topic, msg):
        topic_str = topic.decode()
        msg_str = msg.decode(errors='ignore')
        self.log.info(f"← {topic_str} = {msg_str}")

        for entity in self.entities:
            if hasattr(entity, "command_topic") and topic_str == entity.command_topic:
                entity.set_value(msg_str)
                self.publish_state()
                return

    def publish_state(self):
        state_dict = {e.entity_id: e.get_state_value() for e in self.entities if e.discovered}
        if not state_dict:
            return
        payload = json.dumps(state_dict)
        self.mqtt_client.publish(self.state_topic, payload, qos=0)
        self.log.info(f"State published ({len(state_dict)} entities)")

    async def run(self):
        """Optimized main loop – decoupled timers + smart flag"""
        while True:
            if self.connected:
                self._subscribe_all_commands()
                await asyncio.sleep(2)
                self.publish_discovery()
                await asyncio.sleep(2)
                self.publish_state()
                await asyncio.sleep(1)

                # Initialize independent timers
                self.last_discovery_scan = utime.ticks_ms()
                self.has_undiscovered_entities = False   # initial discovery complete

                while True:
                    try:
                        self.mqtt_client.check_msg()

                        now = utime.ticks_ms()

                        # ───── OPTIMIZED DISCOVERY SCAN (exactly every 30s when needed) ─────
                        if (self.has_undiscovered_entities and
                            utime.ticks_diff(now, self.last_discovery_scan) >= self.discovery_scan_interval * 1000):
                            count = self.publish_pending_discoveries()
                            if count > 0:
                                await asyncio.sleep(2)      # HA needs to process new config
                                self.publish_state()
                            self.last_discovery_scan = now
                        # ────────────────────────────────────────────────────────────────

                        self.publish_state()
                        await asyncio.sleep(2)   # short sleep = responsive MQTT + accurate timers

                    except Exception as e:
                        self.log.error(f"MQTT loop error: {e}")
                        await asyncio.sleep(30)
            else:
                self._connect_mqtt()
            await asyncio.sleep(60)

BMSmqtt_dev = None

def get_BMSmqtt() -> BMSmqtt:
    global BMSmqtt_dev
    if BMSmqtt_dev is None:
        BMSmqtt_dev = BMSmqtt()
    return BMSmqtt_dev