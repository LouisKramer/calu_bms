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
        #self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
                "via_device": self.bmsmqtt_dev.device_id,  # ← this creates the sub-device link
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
        self.command_topic = None          # will be set in add_entity
        self.sub_device = sub_device
        self.cb = cb
        #self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
                "via_device": self.bmsmqtt_dev.device_id,  # ← this creates the sub-device link
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
        self.value = False              # internal state (bool)
        self.command_topic = None
        #self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
        self.value = False              # internal state (bool)
        self.device_class = device_class
        self.icon = icon
        self.sub_device = sub_device # e.g.{"name": "Slave", "id": "slave_x"}
        #self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
                "via_device": self.bmsmqtt_dev.device_id,  # ← this creates the sub-device link
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
        self.options = options          # list of strings
        self.value = default if default in options else options[0]
        self.command_topic = None
        #self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
            pass  # invalid option → keep current

# ───────────────────────────────────────────────
#          Text 
# ───────────────────────────────────────────────
class Text(Entity):
    """
    Home Assistant Text entity (free-form text input/output)
    Can be used for strings, custom labels, debug info, etc.
    """
    
    def __init__(self, name, default="", max_length=255, sub_device=None):
        super().__init__(name)
        self.value = default
        self.max_length = max_length
        self.command_topic = None
        self.sub_device = sub_device # e.g.{"name": "Slave", "id": "slave_x"}
        #self.bmsmqtt_dev.add_entity(self)  # Auto-register with singleton
    
    def get_discovery_payload(self):
        payload = {
            "name": f"{self.device_info['name']} {self.name}",
            "unique_id": self.unique_id,
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "value_template": f"{{{{ value_json.{self.entity_id} }}}}",
            "max": self.max_length,
            "mode": "text",  # can also be "password" if needed
        }
        if self.sub_device:
            payload["device"] = {
                "name": self.sub_device["name"],
                "identifiers": [f"{self.bmsmqtt_dev.device_id}_{self.sub_device['id']}"],
                "via_device": self.bmsmqtt_dev.device_id,  # ← this creates the sub-device link
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
            self.value = val[:self.max_length]  # enforce max length
        else:
            self.value = str(val) if val is not None else ""
# ───────────────────────────────────────────────
#          BMSmqtt – updated to support new types
# ───────────────────────────────────────────────
class BMSmqtt:
    def __init__(self,
                 device_name=MQTT_DEVICE_NAME,
                 device_id=MQTT_DEVICE_ID,
                 mqtt_broker=MQTT_BROKER,
                 mqtt_user=MQTT_USER,
                 mqtt_password=MQTT_PASSWORD,
                 base_topic=None,
                 update_interval=60):

        self.log = Logger()
        self.device_name = device_name
        self.device_id = device_id
        self.base_topic = base_topic or f"homeassistant/{device_id}"
        self.update_interval = update_interval
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
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.client_id = ubinascii.hexlify(machine.unique_id())

        self._connect_mqtt()

    def _connect_mqtt(self):
        self.mqtt_client = MQTTClient(
            self.client_id,
            self.mqtt_broker,
            user=self.mqtt_user or None,
            password=self.mqtt_password or None,
            keepalive=120)
        
        self.mqtt_client.set_last_will(self.availability_topic, b"offline", retain=True, qos=1)
        self.mqtt_client.set_callback(self._on_message)

        self.log.info("Connecting MQTT...")
        try:
            self.mqtt_client.connect()
            self.log.info("MQTT connected")
            self.mqtt_client.publish(self.availability_topic, b"online", retain=True, qos=1)
            self.log.info("MQTT availability published: online")
            # ← NEW: subscribe to all commands once we are really online
            self._subscribe_all_commands()
            
        except Exception as e:
            self.log.warn(f"MQTT connect failed: {e}")
   
    def _subscribe_all_commands(self):
        """Subscribe to all command topics. Safe to call multiple times."""
        if not self.mqtt_client:
            return
        for entity in self.entities:
            if hasattr(entity, "command_topic") and entity.command_topic:
                try:
                    self.mqtt_client.subscribe(entity.command_topic)
                    self.log.info(f"Subscribed: {entity.command_topic}")
                except Exception as e:
                    self.log.warn(f"Subscribe failed for {entity.command_topic}: {e}")

    def add_entity(self, entity: Entity):
        """Add entity and prepare command topic, but DO NOT subscribe yet."""
        entity.unique_id = f"{self.device_id}_{entity.entity_id}"
        entity.state_topic = self.state_topic
        entity.device_info = self.device_info

        # Only prepare command topic — subscribe later when connected
        if hasattr(entity, "command_topic") and getattr(entity, "command_topic", None) is None:
            entity.command_topic = f"{self.base_topic}/set/{entity.entity_id}"

        self.entities.append(entity)
        self.log.info(f"Entity added: {entity.name} (command_topic prepared)")
        return entity

    def _publish_discovery(self, entity, component):
        topic = entity.get_discovery_topic(component)
        payload_dict = entity.get_discovery_payload()
        payload = json.dumps(payload_dict)          # FIXED: proper JSON
        self.mqtt_client.publish(topic, payload, retain=True, qos=0)

    def publish_discovery(self):
        print(f"Publishing discovery for all entities...{self.entities}")
        for entity in self.entities:
            if isinstance(entity, Sensor):
                component = "sensor"
            elif isinstance(entity, Number):
                component = "number"
            elif isinstance(entity, Switch):
                component = "switch"
            elif isinstance(entity, BinarySensor):
                component = "binary_sensor"
            elif isinstance(entity, Select):
                component = "select"
            elif isinstance(entity, Text):
                component = "text"
            else:
                self.log.warn(f"Cannot publish discovery: unknown entity type {type(entity)}")
                continue

            self._publish_discovery(entity, component)
            self.log.info(f"Discovery published: {entity.name}")

    def publish_runtime_entity(self, entity: Entity):       
        if isinstance(entity, Sensor):
            component = "sensor"
        elif isinstance(entity, Number):
            component = "number"
        elif isinstance(entity, Switch):
            component = "switch"
        elif isinstance(entity, BinarySensor):
            component = "binary_sensor"
        elif isinstance(entity, Select):
            component = "select"
        elif isinstance(entity, Text):
            component = "text"
        else:
            self.log.warn(f"Cannot publish runtime discovery: unknown entity type {type(entity)}")
            return

        self._publish_discovery(entity, component)
        self.mqtt_client.publish(self.availability_topic, b"online", retain=True, qos=0)
        self.publish_state()                    # refresh full JSON state
        self.log.info(f"Runtime entity discovery published: {entity.name}")

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
        state_dict = {e.entity_id: e.get_state_value() for e in self.entities}
        payload = json.dumps(state_dict)                # FIXED: proper JSON
        self.mqtt_client.publish(self.state_topic, payload, qos=0)
        self.log.info(f"State published: {payload}")

    async def run(self):
        """Main MQTT loop – fixed timing for all MicroPython ports"""
        #self._subscribe_all_commands()
        self.publish_discovery()
        self.publish_state()
        while True:
            try:
                self.mqtt_client.check_msg()            # robust handles reconnect internally
                self.publish_state()
                await asyncio.sleep(30)

            except Exception as e:
                self.log.error(f"MQTT loop error: {e}")
                await asyncio.sleep(30)

BMSmqtt_dev = None

def get_BMSmqtt() -> BMSmqtt:
    """Get or create the singleton instance"""
    global BMSmqtt_dev
    if BMSmqtt_dev is None:
        BMSmqtt_dev = BMSmqtt()
    return BMSmqtt_dev
# ───────────────────────────────────────────────
#          Example usage
# ───────────────────────────────────────────────

#if __name__ == "__main__":
#    bms = BMSmqtt(
#        device_name = MQTT_DEVICE_NAME,
#        device_id   = MQTT_DEVICE_ID,
#        mqtt_broker = MQTT_BROKER,
#        mqtt_user   = MQTT_USER,
#        mqtt_password = MQTT_PASSWORD,
#        update_interval=30
#    )
#
#    # Sensors
#    bms.add_entity(Sensor("Voltage",       unit="V",   device_class="voltage"))
#    bms.add_entity(Sensor("Current",       unit="A",   device_class="current"))
#    bms.add_entity(Sensor("Temperature",   unit="°C",  device_class="temperature"))
#
#    # Controllable
#    bms.add_entity(Number("Charge Limit",  min_val=0, max_val=30, step=0.5, unit="A"))
#    bms.add_entity(Switch("Balancing"))
#    bms.add_entity(Select("Operation Mode", options=["Idle", "Charge", "Discharge", "Auto"]))
#
#    # Status / alarms (read-only)
#    bms.add_entity(BinarySensor("Charging",    device_class="battery_charging"))
#    bms.add_entity(BinarySensor("Fault",       device_class="problem"))
#    bms.add_entity(BinarySensor("Low Voltage", device_class="problem"))
#
#    # Start the loop
#    asyncio.run(bms.run())