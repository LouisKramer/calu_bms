from common.credentials import *
from common.logger import Logger
import time
import asyncio
import machine
import ubinascii
from umqtt.robust import MQTTClient


# ───────────────────────────────────────────────
#          Base Entity Class (Abstract)
# ───────────────────────────────────────────────
class Entity:
    """Base class for all Home Assistant entities"""
    
    def __init__(self, name, entity_id=None):
        self.name = name
        self.entity_id = entity_id or name.lower().replace(" ", "_")
        self.unique_id = None # will be set by BMSmqtt when entity is registered
        self.state_topic = None # will be set by BMSmqtt when entity is registered
        self.device_info = None # will be set by BMSmqtt when entity is registered
        self.bmsmqtt_dev = get_BMSmqtt()  # Get the singleton instance of BMSmqtt
    
    def get_discovery_payload(self):
        raise NotImplementedError("Subclasses must implement get_discovery_payload()")
    
    def get_discovery_topic(self, component):
        return f"homeassistant/{component}/{self.unique_id}/config"
    
    def get_state_value(self):
        return None


# ───────────────────────────────────────────────
#          Sensor (unchanged)
# ───────────────────────────────────────────────
class Sensor(Entity):
    def __init__(self, name, unit=None, device_class=None, icon=None, sub_device=None):
        super().__init__(name)
        self.unit = unit
        self.device_class = device_class
        self.icon = icon
        self.value = 0.0
        self.sub_device = sub_device # e.g.{"name": "Slave", "id": "slave_x"}
        self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
    def __init__(self, name, min_val=0, max_val=100, step=1, default = None ,unit=None, mode="slider", sub_device=None, cb:callable = None):
        super().__init__(name)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.unit = unit
        self.mode = mode
        self.value = default if default is not None else (self.min_val + self.max_val) / 2
        self.command_topic = None
        self.sub_device = sub_device # e.g.{"name": "Slave", "id": "slave_x"}
        self.cb = cb
        self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
            self.cb() if self.cb else None
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
        self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
        self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
        self.bmsmqtt_dev.add_entity(self)  # Register this entity with BMSmqtt
    
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
        self.bmsmqtt_dev.add_entity(self)  # Auto-register with singleton
    
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
                 device_name = MQTT_DEVICE_NAME,
                 device_id = MQTT_DEVICE_ID,
                 mqtt_broker = MQTT_BROKER,
                 mqtt_user= MQTT_USER,
                 mqtt_password= MQTT_PASSWORD,
                 base_topic=None,
                 update_interval=60,
                 availability_topic=None):

        self.log = Logger()
        self.device_name = device_name
        self.device_id = device_id
        self.base_topic = base_topic or f"home/{device_id}"
        self.update_interval = update_interval
        self.availability_topic = availability_topic or f"{self.base_topic}/status"

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
            keepalive=120
        )
        self.mqtt_client.set_callback(self._on_message)
        
        self.log.info("Connecting MQTT...")
        try:
            self.mqtt_client.connect()
            self.mqtt_client.publish(self.availability_topic, "online", retain=True)
            self.log.info("MQTT connected")
        except Exception as e:
            self.log.warn(f"MQTT connection failed: {e}")
            time.sleep(10)

    def add_entity(self, entity: Entity):
        entity.unique_id = f"{self.device_id}_{entity.entity_id}"
        entity.state_topic = self.state_topic
        entity.device_info = self.device_info
        
        # Subscribe to command topics for controllable entities
        if hasattr(entity, "command_topic") and entity.command_topic:
            entity.command_topic = f"{self.base_topic}/set/{entity.entity_id}"
            self.mqtt_client.subscribe(entity.command_topic)
        
        self.entities.append(entity)
        return entity

    def publish_discovery(self):
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
                self.log.warn(f"Skipping unknown entity type: {entity.__class__.__name__}")
                continue
                
            topic = entity.get_discovery_topic(component)
            payload_dict = entity.get_discovery_payload()
            payload = str(payload_dict).replace("'", '"')
            self.mqtt_client.publish(topic, payload, retain=True)
            self.log.info(f"Discovery published: {topic}")

    def publish_runtime_entity(self, entity: Entity):
        if entity not in self.entities:
            self.log.warn(f"Entity not registered, cannot publish: {entity.name}")
            return
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
            self.log.warn(f"Cannot publish unknown entity type: {entity.__class__.__name__}")
            return

        topic = entity.get_discovery_topic(component)
        payload_dict = entity.get_discovery_payload()
        payload = str(payload_dict).replace("'", '"')
        self.mqtt_client.publish(topic, payload, retain=True, qos=1)
        self.log.info(f"Runtime discovery published: {topic}")

        # re-announce availability (helps if HA missed previous online msg)
        self.mqtt_client.publish(self.availability_topic, "online", retain=True, qos=1)

        # send current state immediately
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
        parts = []
        for entity in self.entities:
            val = entity.get_state_value()
            # Quote string values, leave numbers unquoted
            if isinstance(val, str):
                parts.append(f'"{entity.entity_id}": "{val}"')
            else:
                parts.append(f'"{entity.entity_id}": {val}')
        
        payload = "{" + ", ".join(parts) + "}"
        self.mqtt_client.publish(self.state_topic, payload)
        self.log.info(f"State published: {payload}")

    def set_value(self, entity_id, value):
        for entity in self.entities:
            if entity.entity_id == entity_id:
                entity.set_value(value)
                self.publish_state()
                return
        self.log.warn(f"Entity not found: {entity_id}")

    async def run(self):
        self.publish_discovery()
        self.publish_state()
        
        last_update = time.time()
        
        while True:
            try:
                self.mqtt_client.check_msg()
                
                now = time.time()
                if now - last_update >= self.update_interval:
                    self.publish_state()
                    last_update = now
                
                await asyncio.sleep(1)
                
            except Exception as e:
                self.log.error(f"Error: {e}")
                await asyncio.sleep(5)

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