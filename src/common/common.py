from lib.BMSmqtt import *
from common.logger import Logger
import ujson as json   # faster & smaller than json on MicroPython

# ==============================================================
# Base helper for all config classes (eliminates duplication)
# ==============================================================
class BaseConfig:
    def __init__(self, section_name):
        self.config = config()
        self._section_name = section_name
        self.log = Logger()
        self.mqtt_enable = False
        self._mqtt_map = {}  # internal name -> MQTT entity

    def _load_from_config(self, defaults: dict):
        section = self.config.get_section(self._section_name, {})
        for key, default in defaults.items():
            setattr(self, key, section.get(key, default))

    def save(self):
        data = {k: getattr(self, k) for k in self._mqtt_map.keys()}
        self.config.set_section(self._section_name, data)
        self.config.save()
        self.log.info(f"{self._section_name} saved")

    def update(self):
        if self.mqtt_enable:
            """Called automatically by MQTT Number callbacks"""
            for attr, entity in self._mqtt_map.items():
                setattr(self, attr, entity.get_state_value())
            if hasattr(self, "_post_update"):
                self._post_update()
            self.save()
# ==============================================================
# bms_config
# ==============================================================
class bms_config(BaseConfig):
    def __init__(self):
        super().__init__("bms_config")
        defaults = {
            "number_exp_slaves": 0, #if 0 BMS will autodiscover slaves
        }
        for k, v in defaults.items():
            setattr(self, k, v)
        self._load_from_config(defaults)
    def init_mqtt_entities(self):
        mqtt = get_BMSmqtt()
        self._mqtt_map = {
            "number_exp_slaves": Number("BMS number of expected Slaves", 0, 16, 1, self.number_exp_slaves, cb=self.update),
        }
        for e in self._mqtt_map.values():
            mqtt.add_entity(e)
# ==============================================================
# can_config
# ==============================================================
class can_config(BaseConfig):
    def __init__(self):
        super().__init__("can_config")
        self.can_tx_pin = 40
        self.can_rx_pin = 39
        self.update_interval = 1.0
        self.baudrate = 125000
        self._load_from_config({"baudrate": 125000})

    def init_mqtt_entities(self):
        options = ["125000", "250000", "500000", "1000000"]
        self._baudrate_select = Select(
            name="CAN Baudrate",
            options=options,
            default=str(self.baudrate)
        )
        get_BMSmqtt().add_entity(self._baudrate_select)
        self._baudrate_select.set_value(str(self.baudrate))
        self._mqtt_map["baudrate"] = self._baudrate_select
        self.mqtt_enable = True

    def _post_update(self):
        try:
            self.baudrate = int(self._baudrate_select.get_state_value())
        except (ValueError, TypeError):
            pass


# ==============================================================
# power_config
# ==============================================================
class power_config(BaseConfig):
    def __init__(self):
        super().__init__("power_config")
        defaults = {
            "max_current": 25.0,
            "under_voltage_cell": 2.7,
            "over_voltage_cell": 3.65,
            "charge_settle_time": 600,
            "soc_low_cutoff": 10.0,
            "max_temp": 50.0,
        }
        for k, v in defaults.items():
            setattr(self, k, v)
        self._load_from_config(defaults)
        self.charge_current_table = []
        self._update_charge_current_table()

    def init_mqtt_entities(self):
        mqtt = get_BMSmqtt()
        self._mqtt_map = {
            "max_current":        Number("Max Charge Current",       0, 100, 0.5, self.max_current,        "A",  cb=self.update),
            "under_voltage_cell": Number("Under Voltage Cell",       2.0, 3.0, 0.1, self.under_voltage_cell, "V",  cb=self.update),
            "over_voltage_cell":  Number("Over Voltage Cell",        3.0, 4.5, 0.1, self.over_voltage_cell,  "V",  cb=self.update),
            "charge_settle_time": Number("Charge Settle Time",       10, 3600, 10, self.charge_settle_time,  "s",  cb=self.update),
            "soc_low_cutoff":     Number("SOC Low Cutoff",           0, 100, 1,   self.soc_low_cutoff,     "%",  cb=self.update),
            "max_temp":           Number("Max Temperature",          0, 100, 1,   self.max_temp,           "°C", cb=self.update),
        }
        for e in self._mqtt_map.values():
            mqtt.add_entity(e)
        self.mqtt_enable = True

    def _update_charge_current_table(self):
        self.charge_current_table = [
            (0, 2.0),
            (10, self.max_current),
            (90, self.max_current),
            (95, 10.0),
            (98, 5.0),
            (99, 2.0),
            (100, 2.0)
        ]

    def _post_update(self):
        self._update_charge_current_table()


# ==============================================================
# protection_config
# ==============================================================
class protection_config(BaseConfig):
    def __init__(self):
        super().__init__("protection_config")
        defaults = {
            "prot_rel_trigger_delay": 30.0,
            "prot_max_inv_vol": 1000.0,
            "prot_min_inv_vol": 0.0,
            "prot_max_current": 28.0,
            "prot_min_current": -28.0,
            "prot_max_temp": 60.0,
            "prot_max_pack_vol": 1000.0,
            "prot_min_pack_vol": 30.0,
            "prot_max_str_vol": 120.0,
            "prot_min_str_vol": 30.0,
            "prot_max_cell_vol": 4.2,
            "prot_min_cell_vol": 2.5,
            "prot_stable_delay_seconds" : 20,       # seconds to wait for measurements to stabilise
            "prot_precharge_vinv_threshold": 50.0,  # if vinv < this → do pre-charge
            "prot_connect_delta_warn": 80.0,        # warn if |vinv - vpack| > this
            "prot_connect_delta_critical": 150.0,   # refuse connection if delta > this
        }
        for k, v in defaults.items():
            setattr(self, k, v)
        self._load_from_config(defaults)

    def init_mqtt_entities(self):
        mqtt = get_BMSmqtt()
        self._mqtt_map = {
            "prot_rel_trigger_delay": Number("Protection Relay Trigger Delay", 5, 300, 1, self.prot_rel_trigger_delay, "s", cb=self.update),
            "prot_max_inv_vol":       Number("Protection Max Inverter Voltage", 200, 1500, 10, self.prot_max_inv_vol, "V", cb=self.update),
            "prot_min_inv_vol":       Number("Protection Min Inverter Voltage", 100, 800, 10, self.prot_min_inv_vol, "V", cb=self.update),
            "prot_max_current":       Number("Protection Max Current", 10, 400, 1, self.prot_max_current, "A", cb=self.update),
            "prot_min_current":       Number("Protection Min Current", -400, 10, 1, self.prot_min_current, "A", cb=self.update),
            "prot_max_temp":          Number("Protection Max Temperature", 40, 100, 1, self.prot_max_temp, "°C", cb=self.update),
            "prot_max_pack_vol":      Number("Protection Max Pack Voltage", 200, 1500, 10, self.prot_max_pack_vol, "V", cb=self.update),
            "prot_min_pack_vol":      Number("Protection Min Pack Voltage", 100, 800, 10, self.prot_min_pack_vol, "V", cb=self.update),
            "prot_max_str_vol":       Number("Protection Max String Voltage", 80, 200, 10, self.prot_max_str_vol, "V", cb=self.update),
            "prot_min_str_vol":       Number("Protection Min String Voltage", 20, 80, 10, self.prot_min_str_vol, "V", cb=self.update),
            "prot_max_cell_vol":      Number("Protection Max Cell Voltage", 3.4, 4.25, 0.05, self.prot_max_cell_vol, "V", cb=self.update),
            "prot_min_cell_vol":      Number("Protection Min Cell Voltage", 2.3, 3.0, 0.05, self.prot_min_cell_vol, "V", cb=self.update),
            "prot_stable_delay_seconds":        Number("Protection Mesurements stable delay", 1, 100, 1, self.prot_stable_delay_seconds, "s", cb=self.update),
            "prot_precharge_vinv_threshold":    Number("Protection Inverter voltage threshold for precharge", 0.0, 100.0, 5.0, self.prot_precharge_vinv_threshold, "V", cb=self.update),
            "prot_connect_delta_warn":          Number("Protection Inverter Contact delta Waring threshold", 0.0, 100.0, 5.0, self.prot_connect_delta_warn, "V", cb=self.update),
            "prot_connect_delta_critical":      Number("Protection Inverter Contact refuse threshold", 50.0, 500.0, 5.0, self.prot_connect_delta_critical, "V", cb=self.update),
        }
        for e in self._mqtt_map.values():
            mqtt.add_entity(e)


# ==============================================================
# soc_config (with scaled values handling)
# ==============================================================
class soc_config(BaseConfig):
    """
    Initialize the SOC estimator with battery and algorithm parameters.
    Args:
        config (dict): Configuration dictionary. Required keys:
            - 'capacity_ah': Battery capacity in Amp-hours
            - 'num_cells': Number of cells in series
            - 'cell_ir': Cell internal resistance in Ohms (at ref temp)
            Optional keys:
            - 'initial_soc': Starting SOC (%) [default: 50.0]
            - 'initial_temp': Starting temperature (°C) [default: 25.0]
            - 'ir_ref_temp': Reference temperature for IR (°C) [default: 25.0]
            - 'ir_temp_coeff': IR temp coefficient (%/°C) [default: 0.004]
            - 'current_threshold': Current below which battery is "relaxed" (A)
            - 'voltage_stable_threshold': Max voltage change for stability (V)
            - 'relaxed_hold_time': Time to confirm relaxed state (s)
            - 'per_cell_voltage_soc_table': Custom voltage-SOC curve
    Raises:
        ValueError: If num_cells or capacity_ah are invalid.
    """
    def __init__(self):
        super().__init__("soc_config")
        defaults = {
            "capacity_ah": 100.0,
            "initial_soc": 80.0,
            "cell_ir": 0.004,
            "ir_ref_temp": 25.0,
            "ir_temp_coeff": 0.004,
            "current_threshold": 1.0,
            "voltage_stable_threshold": 0.01,
            "relaxed_hold_time": 30.0,
            "sampling_interval": 2.0,
            "charge_efficiency": 0.97,          # 97% typical for LiFePO4
            "discharge_efficiency": 1.0,        # 100%
            "design_cycle_life": 4000,          # for SoH calculation (LFP = 3000-6000) 
        }
        for k, v in defaults.items():
            setattr(self, k, v)
        self._load_from_config(defaults)

    def init_mqtt_entities(self):
        mqtt = get_BMSmqtt()
        self._mqtt_map = {
            "capacity_ah":                Number("Battery Capacity (Ah)", 10.0, 1000.0, 10.0, self.capacity_ah, "Ah", cb=self.update),
            "initial_soc":                Number("Initial SOC (%)", 0.0, 100.0, 1.0, self.initial_soc, "%", cb=self.update),
            "cell_ir":                    Number("Cell Internal Resistance (mΩ)", 1, 10, 1, self.cell_ir*1000, "mΩ", cb=self.update),
            "ir_ref_temp":                Number("IR Reference Temperature (°C)", 15.0, 35.0, 1.0, self.ir_ref_temp, "°C", cb=self.update),
            "ir_temp_coeff":              Number("IR Temperature Coefficient (%/°C)", 0.0, 2, 0.1, self.ir_temp_coeff*100, "%/°C", cb=self.update),
            "current_threshold":          Number("Current Threshold (A)", 0.0, 2.0, 0.1, self.current_threshold, "A", cb=self.update),
            "voltage_stable_threshold":   Number("Voltage Stable Threshold (V)", 0.001, 0.05, 0.001, self.voltage_stable_threshold, "V", cb=self.update),
            "relaxed_hold_time":          Number("Relaxed Hold Time (s)", 10.0, 200.0, 10.0, self.relaxed_hold_time, "s", cb=self.update),
            "sampling_interval":          Number("Sampling Interval (s)", 0.5, 100.0, 0.5, self.sampling_interval, "s", cb=self.update),
            "charge_efficiency":          Number("Charge Efficiency", 0.90, 1.0, 0.01, self.charge_efficiency, mode="slider", unit="%", cb=self.update),
            "discharge_efficiency":       Number("Discharge Efficiency", 0.95, 1.0, 0.01, self.discharge_efficiency, mode="slider", unit="%", cb=self.update),
            "design_cycle_life":          Number("Design Cycle Life", 500, 8000, 100, self.design_cycle_life, mode="slider", unit="cycles", cb=self.update)
        }
        for e in self._mqtt_map.values():
            mqtt.add_entity(e)
        self.mqtt_enable = True

    def _post_update(self):
        self.cell_ir = self._mqtt_map["cell_ir"].get_state_value() / 1000
        self.ir_temp_coeff = self._mqtt_map["ir_temp_coeff"].get_state_value() / 100


# ==============================================================
# Config manager
# ==============================================================
class Config:
    def __init__(self, filename="config.json", indent=2):
        self._filename = filename
        self._indent = indent
        self.log = Logger()
        self._sections = {}
        self._load()

    def _load(self):
        try:
            with open(self._filename, 'r') as f:
                self._sections = json.load(f)
            self.log.info(f"Config loaded from {self._filename}")
        except Exception as e:
            self.log.error(f"Config load error: {e}")

    def save(self):
        try:
            with open(self._filename, 'w') as f:
                json.dump(self._sections, f, indent=self._indent)
            self.log.info(f"Config saved to {self._filename}")
        except Exception as e:
            self.log.error(f"Config save error: {e}")

    def get_section(self, section_name, default=None):
        return self._sections.get(section_name, default or {})

    def set_section(self, section_name, data: dict):
        self._sections[section_name] = data

    def get(self, section_name, key, default=None):
        return self.get_section(section_name).get(key, default)

    def set(self, section_name, key, value):
        if section_name not in self._sections:
            self._sections[section_name] = {}
        self._sections[section_name][key] = value


# Singleton
_instance = None

def init_config(filename="config.json", indent=2):
    global _instance
    if _instance is None:
        _instance = Config(filename=filename, indent=indent)
    return _instance

def config() -> Config:
    global _instance
    if _instance is None:
        init_config()
    return _instance


# ==============================================================
# Remaining classes (master_data, battery, etc.)
# ==============================================================
class master_data:
    def __init__(self):
        self.current = 0.0
        self.vpack = 0.0
        self.tpack = 0.0
        self.tadc = 0.0
        self.vinv = 0.0
        self.soc = 0.0
        self.soh = 0.0
        self.cycle_cnt = 0
        self.mqtt_enable = False

    def init_mqtt_entities(self):
        mqtt = get_BMSmqtt()
        self._current = Sensor("Pack Current", unit="A", device_class="current")
        self._vpack   = Sensor("Pack Voltage", unit="V", device_class="voltage")
        self._tpack   = Sensor("Pack Temperature", unit="°C", device_class="temperature")
        self._tadc    = Sensor("ADC Temperature", unit="°C", device_class="temperature")
        self._vinv    = Sensor("Inverter Voltage", unit="V", device_class="voltage")
        self._soc     = Sensor("State of Charge", unit="%", device_class="battery")
        self._soh     = Sensor("State of Health", unit="%", device_class="battery")
        self._cycle_cnt = Sensor("Cycle Count", unit="cycles")
        for e in (self._current, self._vpack, self._tpack, self._tadc, self._vinv, self._soc, self._soh, self._cycle_cnt):
            mqtt.add_entity(e)
        self.mqtt_enable = True

    def update_current(self, value: float): 
        self.current = float(value)
        if self.mqtt_enable: 
            self._current.set_value(self.current)
    def update_vpack(self, value: float):
        self.vpack = float(value)
        if self.mqtt_enable:
            self._vpack.set_value(self.vpack)
    def update_tpack(self, value: float):
        self.tpack = float(value)
        if self.mqtt_enable:
            self._tpack.set_value(self.tpack)
    def update_tadc(self, value: float):
        self.tadc = float(value)
        if self.mqtt_enable:
            self._tadc.set_value(self.tadc)
    def update_vinv(self, value: float):
        self.vinv = float(value)
        if self.mqtt_enable:
            self._vinv.set_value(self.vinv)
    def update_soc(self, value: float):
        self.soc = float(value)
        if self.mqtt_enable:
            self._soc.set_value(self.soc)
    def update_soh(self, value: float):
        self.soh = float(value)
        if self.mqtt_enable:
            self._soh.set_value(self.soh)
    def update_cycle_cnt(self, value: float): 
        self.cycle_cnt = float(value)
        if self.mqtt_enable:
            self._cycle_cnt.set_value(self.cycle_cnt)

    def update_all(self, current=0.0, vpack=0.0, tpack=0.0, tadc=0.0, vinv=0.0, soc=0.0, soh=0.0, cycle_cnt=0.0):
        self.update_current(current)
        self.update_vpack(vpack)
        self.update_tpack(tpack)
        self.update_tadc(tadc)
        self.update_vinv(vinv)
        self.update_soc(soc)
        self.update_soh(soh)
        self.update_cycle_cnt(cycle_cnt)

class battery:
    def __init__(self):
        self.info  = info_data()
        self.conf  = slave_config()
        self.meas  = meas_data()
        self.state = status_data()   # will be per-slave in real code
        self.mqtt_enable = False

    def init_mqtt_entities(self):
        self.info.init_mqtt_entities(self.info.addr)
        self.conf.init_mqtt_entities(self.info.addr)
        if self.meas != None:
            self.meas.init_mqtt_entities(self.info.addr)
        self.mqtt_enable = True
        # meas will be initialized after info is set (needs ncell/ntemp)

    def is_data_stable(self):
        if self.meas is None:
            return False
        return all(2.0 < v < 4.5 for v in self.meas.vcell)

class status_data:
    def __init__(self):
        self.channel_found = False
        self.com_active = False
        self.synced = False
        self.stable = False
        self.ttl = 0
        self.mqtt_enable = False

    def init_mqtt_entities(self, addr: int):
        sub = {"name": f"Slave {addr}", "id": f"slave_{addr}"}
        self._channel_found = BinarySensor("Channel Found", sub_device=sub)
        self._com_active    = BinarySensor("Communication Active", sub_device=sub)
        self._synced        = BinarySensor("Data Synced", sub_device=sub)
        self._stable        = BinarySensor("Data Stable", sub_device=sub)
        self._ttl           = Sensor("Data TTL",unit="s", sub_device=sub)
        mqtt = get_BMSmqtt()
        for e in (self._channel_found, self._com_active, self._synced, self._stable, self._ttl):
            mqtt.add_entity(e)
        self.mqtt_enable = True

    def update_channel_found(self, value: bool):
        self.channel_found = bool(value)
        if self.mqtt_enable:
            self._channel_found.set_value(self.channel_found)

    def update_com_active(self, value: bool):
        self.com_active = bool(value)
        if self.mqtt_enable:
            self._com_active.set_value(self.com_active)
    def update_synced(self, value: bool):
        self.synced = bool(value)
        if self.mqtt_enable:
            self._synced.set_value(self.synced)
    def update_stable(self, value: bool):
        self.stable = bool(value)
        if self.mqtt_enable:
            self._stable.set_value(self.stable)
    def update_ttl(self, value: int):
        self.ttl = int(value)
        if self.mqtt_enable:
            self._ttl.set_value(self.ttl)
    def update_all(self, channel_found: bool, com_active: bool, synced: bool, stable: bool, ttl: int):
        self.update_channel_found(channel_found)
        self.update_com_active(com_active)
        self.update_synced(synced)
        self.update_stable(stable)
        self.update_ttl(ttl)

class info_data:
    def __init__(self):
        self.mac = b''
        self.master_mac = b''
        self.addr = 0
        self.ncell = 0
        self.ntemp = 0
        self.fw_ver = "0.0.0.0"
        self.hw_ver = "0.0.0.0"
        self.mqtt_enable = False

    def init_mqtt_entities(self, addr: int = None):
        if addr is not None:
            self.addr = addr
        sub = {"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"}
        self._mac        = Text("MAC", default=self.mac.hex(), sub_device=sub)
        self._master_mac = Text("Master MAC", default=self.master_mac.hex(), sub_device=sub)
        self._addr       = Text("Address", default=str(self.addr), sub_device=sub)
        self._ncell      = Text("Number of Cells", default=str(self.ncell), sub_device=sub)
        self._ntemp      = Text("Number of Temps", default=str(self.ntemp), sub_device=sub)
        self._fw_ver     = Text("Firmware Version", default=self.fw_ver, sub_device=sub)
        self._hw_ver     = Text("Hardware Version", default=self.hw_ver, sub_device=sub)
        mqtt = get_BMSmqtt()
        for e in (self._mac, self._master_mac, self._addr, self._ncell, self._ntemp, self._fw_ver, self._hw_ver):
            mqtt.add_entity(e)
        self.mqtt_enable = True

    def update_mac(self, mac: bytearray):
        self.mac = mac
        if self.mqtt_enable:
            self._mac.set_value(self.mac.hex())

    def update_master_mac(self, master_mac: bytearray):
        self.master_mac = master_mac
        if self.mqtt_enable:
            self._master_mac.set_value(self.master_mac.hex())

    def update_addr(self, addr: int):
        self.addr = addr
        if self.mqtt_enable:
            self._addr.set_value(str(self.addr))

    def update_ncell(self, ncell: int):
        self.ncell = ncell
        if self.mqtt_enable:
            self._ncell.set_value(str(self.ncell))

    def update_ntemp(self, ntemp: int):
        self.ntemp = ntemp
        if self.mqtt_enable:
            self._ntemp.set_value(str(self.ntemp))

    def update_fw_ver(self, fw_ver: str):
        self.fw_ver = fw_ver
        if self.mqtt_enable:
            self._fw_ver.set_value(self.fw_ver)

    def update_hw_ver(self, hw_ver: str):
        self.hw_ver = hw_ver
        if self.mqtt_enable:
            self._hw_ver.set_value(self.hw_ver)
        
    def update_all(self, mac: bytearray, master_mac: bytearray, addr: int, ncell: int, ntemp: int, fw_ver: str, hw_ver: str):
        self.update_mac(mac)
        self.update_master_mac(master_mac)
        self.update_addr(addr)
        self.update_ncell(ncell)
        self.update_ntemp(ntemp)
        self.update_fw_ver(fw_ver)
        self.update_hw_ver(hw_ver)

    def set(self, other: 'info_data'):
        if isinstance(other, info_data):
            self.mac = other.mac
            self.master_mac = other.master_mac
            self.addr = other.addr
            self.ncell = other.ncell
            self.ntemp = other.ntemp
            self.fw_ver = other.fw_ver
            self.hw_ver = other.hw_ver

class meas_data:
    def __init__(self, bat: battery, max_cells = 32, max_temps = 16):
        #self.vcell = [0.0] * bat.info.ncell
        self.vcell: list[float] = [-1.0] * max_cells
        self._ncell = 0
        self.vstr = 0.0
        #self.temps = [0.0] * bat.info.ntemp
        self.temps : list[float] = [-1.0] * max_temps
        self._ntemp = 0
        #mqtt
        self.mqtt_enable = False
        self._vcell = [] 
        self._temps = []
        self._vstr = None

    def init_mqtt_entities(self, addr: int):
        sub = {"name": f"Slave {addr}", "id": f"slave_{addr}"}
        mqtt = get_BMSmqtt()
        for i in range(self.get_nr_of_cells()):
            e = Sensor(f"Cell {i+1} Voltage", unit="V", sub_device=sub)
            mqtt.add_entity(e)
            self._vcell.append(e)
        self._vstr = Sensor("String Voltage", unit="V", sub_device=sub)
        mqtt.add_entity(self._vstr)
        for i in range(self.get_nr_of_temps()):
            e = Sensor(f"Temp {i+1}", unit="°C", sub_device=sub)
            mqtt.add_entity(e)
            self._temps.append(e)
        self.mqtt_enable = True
    
    def update_mqtt_entities(self):
        if self.mqtt_enable:
            for i, v in enumerate(self.vcell):
                self._vcell[i].set_value(v)
            self._vstr.set_value(self.vstr)
            for i, t in enumerate(self.temps):
                self._temps[i].set_value(t)

    def get_nr_of_cells(self) -> int:
        return sum(1 for v in self.vcell if v is not None and v > 1.0)
    
    def get_nr_of_temps(self) -> int:
        return sum(1 for t in self.temps if t is not None and t > 1.0)

    def set_vcell(self, index: int, voltage: float) -> bool:
        if not 0 <= index < len(self.vcell) or not isinstance(voltage, (int, float)) or voltage < 0:
            return False
        self.vcell[index] = float(voltage)
        return True

    def set_all_vcells(self, voltages: list) -> bool:
        if len(voltages) != len(self.vcell) or not all(isinstance(v, (int, float)) and v >= 0 for v in voltages):
            return False
        self.vcell = [float(v) for v in voltages]
        return True

    def set_vstr(self, voltage: float) -> bool:
        if not isinstance(voltage, (int, float)) or voltage < 0:
            return False
        self.vstr = float(voltage)
        return True

    def set_temp(self, index: int, temp: float) -> bool:
        if not 0 <= index < len(self.temps) or not isinstance(temp, (int, float)):
            return False
        self.temps[index] = float(temp)
        return True

    def set_all_temps(self, temps: list) -> bool:
        if len(temps) != len(self.temps) or not all(isinstance(t, (int, float)) for t in temps):
            return False
        self.temps = [float(t) for t in temps]
        return True

    def update(self, vcells=None, vstr=None, temps=None):
        success = True
        if vcells is not None: success &= self.set_all_vcells(vcells)
        if vstr is not None:   success &= self.set_vstr(vstr)
        if temps is not None:  success &= self.set_all_temps(temps)
        return success


class slave_config (BaseConfig):
    def __init__(self):
        super().__init__("Slave_config")
        defaults = {
            "bal_start_vol": 3.4,
            "bal_threshold": 0.01,
            "bal_en": True,
            "bal_ext_en": False,
            "ttl": 10
        }
        for k, v in defaults.items():
            setattr(self, k, v)
        self._load_from_config(defaults)

    def init_mqtt_entities(self, addr: int = None):
        mqtt = get_BMSmqtt()
        sub = {"name": f"Slave {addr}", "id": f"slave_{addr}"} if addr is not None else None
        self._mqtt_map = {
            "bal_start_vol":    Number("Balance Start Voltage", 2.8, 3.8, 0.01, self.bal_start_vol, sub_device=sub, unit = "V", cb=self.update),
            "bal_threshold":    Number("Balance Threshold", 0.005, 0.100, 0.005, self.bal_threshold, sub_device=sub, unit = "V", cb=self.update),
            "bal_en":           Number("Balancing Enabled", 0, 1, 1, int(self.bal_en), sub_device=sub, cb=self.update),
            "bal_ext_en":       Number("External Balancing Enabled", 0, 1, 1, int(self.bal_ext_en), sub_device=sub, cb=self.update),
            "ttl":              Number("Data TTL", 0, 300, 10, self.ttl, sub_device=sub, unit = "s", cb=self.update),
        }
        for e in self._mqtt_map.values():
            mqtt.add_entity(e)
        self.mqtt_enable = True