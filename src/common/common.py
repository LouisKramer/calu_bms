from lib.BMSmqtt import Number, Select, Sensor, BinarySensor, Text
from common.logger import Logger
import json

class can_config:
    def __init__(self):
        self.baudrate = Select("baudrate", options=[125000, 250000, 500000, 1000000], initial=125000)
        self.can_tx_pin = 40      # ESP32 GPIO
        self.can_rx_pin = 39
        self.baudrate = 125000    # 125 kbps
        self.update_interval = 1.0
# file: config.py

import json
from common.logger import Logger

class Config:
    """
    Generic configuration manager (singleton).
    Handles loading/saving sections from/to JSON.
    """

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
        except FileNotFoundError:
            self.log.info(f"Config file {self._filename} not found → using defaults")
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


# ───────────────────────────────────────────────
# Singleton instance & access functions
# ───────────────────────────────────────────────
_instance = None

def init_config(filename="config.json", indent=2):
    """Initialize the global config singleton (call once at startup)"""
    global _instance
    if _instance is not None:
        return _instance
    _instance = Config(filename=filename, indent=indent)
    return _instance

def config() -> Config:
    """Get the global config instance"""
    global _instance
    if _instance is None:
        init_config()
    return _instance

class power_config():
    def __init__(self):
        self.config = config()
        self._section_name = "power_config"
        self.max_current = 25.0
        self.under_voltage_cell = 2.7       #if lower, set discharge current to 0A only allow charge
        self.over_voltage_cell = 3.65       #if higher set charge current to 0 A and settle
        self.charge_settle_time = 600       #settle time in s, 
        self.soc_low_cutoff = 10.0          #if lower, reduce discharge current to 0 A only allow charge
        self.max_temp = 50.0                #if any temp is greater than this, reduce charge/discharge current

        self._max_current = Number("Max Charge Current", min_val=0.0, max_val=100.0, step=0.5, mode="slider", default=self.max_current, unit="A", cb=self.update)
        self._under_voltage_cell = Number("Under Voltage Cell", min_val=2.0, max_val=3.0, step=0.1, mode="slider", default=self.under_voltage_cell, unit="V", cb=self.update)
        self._over_voltage_cell = Number("Over Voltage Cell", min_val=3.0, max_val=4.5, step=0.1, mode="slider", default=self.over_voltage_cell, unit="V", cb=self.update)
        self._charge_settle_time = Number("Charge Settle Time", min_val=10, max_val=3600, step=10, mode="slider", default=self.charge_settle_time, unit="s", cb=self.update)
        self._soc_low_cutoff = Number("SOC Low Cutoff", min_val=0, max_val=100, step=1, mode="slider", default=self.soc_low_cutoff, unit="%", cb=self.update)
        self._max_temp = Number("Max Temperature", min_val=0, max_val=100, step=1, mode="slider", default=self.max_temp, unit="°C", cb=self.update)
        self.charge_current_table = []
        self._load_from_config()
        self._update_charge_current_table()

    def _update_charge_current_table(self):
        self.charge_current_table = [       #charge current depending on soc
        (0, 2.0),
        (10, self.max_current),
        (90, self.max_current),
        (95, 10.0),
        (98, 5.0),
        (99, 2.0),
        (100, 2.0)# still charging possible TODO: to be tested
        ]

    def _load_from_config(self):
        section = self.config.get_section(self._section_name, {})
        self.max_current            = section.get("max_current",            self.max_current)
        self.under_voltage_cell     = section.get("under_voltage_cell",     self.under_voltage_cell)
        self.over_voltage_cell      = section.get("over_voltage_cell",      self.over_voltage_cell)
        self.charge_settle_time     = section.get("charge_settle_time",     self.charge_settle_time)
        self.soc_low_cutoff         = section.get("soc_low_cutoff",         self.soc_low_cutoff)
        self.max_temp               = section.get("max_temp",               self.max_temp)
        
        self._max_current.set_value(self.max_current)
        self._under_voltage_cell.set_value(self.under_voltage_cell)
        self._over_voltage_cell.set_value(self.over_voltage_cell)
        self._charge_settle_time.set_value(self.charge_settle_time)
        self._soc_low_cutoff.set_value(self.soc_low_cutoff)
        self._max_temp.set_value(self.max_temp)

    def save(self):
        data = {
            "max_current":          self.max_current,
            "under_voltage_cell":   self.under_voltage_cell,
            "over_voltage_cell":    self.over_voltage_cell,
            "charge_settle_time":   self.charge_settle_time,
            "soc_low_cutoff":       self.soc_low_cutoff,
            "max_temp":             self.max_temp
        }
        self.config.set_section(self._section_name, data)
        self.config.save()

    def update(self):
        """Call this to update config values from the Number entities (e.g. after user changes in Home Assistant)"""
        self.max_current = self._max_current.get_state_value()
        self.under_voltage_cell = self._under_voltage_cell.get_state_value()
        self.over_voltage_cell = self._over_voltage_cell.get_state_value()
        self.charge_settle_time = self._charge_settle_time.get_state_value()
        self.soc_low_cutoff = self._soc_low_cutoff.get_state_value()
        self.max_temp = self._max_temp.get_state_value()
        self._update_charge_current_table()
        self.save()

class protection_config:
    def __init__(self):
        self.config = config()
        self._section_name = "protection_config"
        self.prot_rel_trigger_delay = 30.0    # time from SiC stage to relay stage if conditions did not improve
        self.prot_max_inv_vol       = 1000.0
        self.prot_min_inv_vol       = 0.0
        self.prot_max_current       = 28.0
        self.prot_min_current       = -28.0
        self.prot_max_temp          = 60.0
        self.prot_max_pack_vol      = 1000.0
        self.prot_min_pack_vol      = 30.0
        self.prot_max_str_vol       = 120.0
        self.prot_min_str_vol       = 30.0
        self.prot_max_cell_vol      = 4.2
        self.prot_min_cell_vol      = 2.5

        self._prot_rel_trigger_delay = Number("Protection Relay Trigger Delay", min_val=5, max_val=300, step=1, mode="slider", default=self.prot_rel_trigger_delay, unit="s", cb=self.update)
        self._prot_max_inv_vol = Number("Protection Max Inverter Voltage", min_val=200, max_val=1500, step=10, mode="slider", default=self.prot_max_inv_vol, unit="V", cb=self.update)
        self._prot_min_inv_vol = Number("Protection Min Inverter Voltage", min_val=100, max_val=800, step=10, mode="slider", default=self.prot_min_inv_vol, unit="V", cb=self.update)
        self._prot_max_current = Number("Protection Max Current", min_val=10, max_val=400, step=1, mode="slider", default=self.prot_max_current, unit="A", cb=self.update)
        self._prot_min_current = Number("Protection Min Current", min_val=-400, max_val=10, step=1, mode="slider", default=self.prot_min_current, unit="A", cb=self.update)
        self._prot_max_temp = Number("Protection Max Temperature", min_val=40, max_val=100, step=1, mode="slider", default=self.prot_max_temp, unit="°C", cb=self.update)
        self._prot_max_pack_vol = Number("Protection Max Pack Voltage", min_val=200, max_val=1500, step=10, mode="slider", default=self.prot_max_pack_vol, unit="V", cb=self.update)
        self._prot_min_pack_vol = Number("Protection Min Pack Voltage", min_val=100, max_val=800, step=10, mode="slider", default=self.prot_min_pack_vol, unit="V", cb=self.update)
        self._prot_max_str_vol = Number("Protection Max String Voltage", min_val=80, max_val=200, step=10, mode="slider", default=self.prot_max_str_vol, unit="V", cb=self.update)
        self._prot_min_str_vol = Number("Protection Min String Voltage", min_val=20, max_val=80, step=10, mode="slider", default=self.prot_min_str_vol, unit="V", cb=self.update)
        self._prot_max_cell_vol = Number("Protection Max Cell Voltage", min_val=3.4, max_val=4.25, step=0.05, mode="slider", default=self.prot_max_cell_vol, unit="V", cb=self.update)
        self._prot_min_cell_vol = Number("Protection Min Cell Voltage", min_val=2.3, max_val=3.0, step=0.05, mode="slider", default=self.prot_min_cell_vol, unit="V", cb=self.update)

        self._load_from_config()

    def _load_from_config(self):
        section = self.config.get_section(self._section_name, {})
        self.prot_rel_trigger_delay = section.get("prot_rel_trigger_delay", self.prot_rel_trigger_delay)
        self.prot_max_inv_vol = section.get("prot_max_inv_vol", self.prot_max_inv_vol)
        self.prot_min_inv_vol = section.get("prot_min_inv_vol", self.prot_min_inv_vol)
        self.prot_max_current = section.get("prot_max_current", self.prot_max_current)
        self.prot_min_current = section.get("prot_min_current", self.prot_min_current)
        self.prot_max_temp = section.get("prot_max_temp", self.prot_max_temp)
        self.prot_max_pack_vol = section.get("prot_max_pack_vol", self.prot_max_pack_vol)
        self.prot_min_pack_vol = section.get("prot_min_pack_vol", self.prot_min_pack_vol)
        self.prot_max_str_vol = section.get("prot_max_str_vol", self.prot_max_str_vol)
        self.prot_min_str_vol = section.get("prot_min_str_vol", self.prot_min_str_vol)
        self.prot_max_cell_vol = section.get("prot_max_cell_vol", self.prot_max_cell_vol)
        self.prot_min_cell_vol = section.get("prot_min_cell_vol", self.prot_min_cell_vol)

        self._prot_rel_trigger_delay.set_value(self.prot_rel_trigger_delay)
        self._prot_max_inv_vol.set_value(self.prot_max_inv_vol)
        self._prot_min_inv_vol.set_value(self.prot_min_inv_vol)
        self._prot_max_current.set_value(self.prot_max_current)
        self._prot_min_current.set_value(self.prot_min_current)
        self._prot_max_temp.set_value(self.prot_max_temp)
        self._prot_max_pack_vol.set_value(self.prot_max_pack_vol)
        self._prot_min_pack_vol.set_value(self.prot_min_pack_vol)
        self._prot_max_str_vol.set_value(self.prot_max_str_vol)
        self._prot_min_str_vol.set_value(self.prot_min_str_vol)
        self._prot_max_cell_vol.set_value(self.prot_max_cell_vol)
        self._prot_min_cell_vol.set_value(self.prot_min_cell_vol)

    def save(self):
        data = {
            "prot_rel_trigger_delay": self.prot_rel_trigger_delay,
            "prot_max_inv_vol": self.prot_max_inv_vol,
            "prot_min_inv_vol": self.prot_min_inv_vol,
            "prot_max_current": self.prot_max_current,
            "prot_min_current": self.prot_min_current,
            "prot_max_temp": self.prot_max_temp,
            "prot_max_pack_vol": self.prot_max_pack_vol,
            "prot_min_pack_vol": self.prot_min_pack_vol,
            "prot_max_str_vol": self.prot_max_str_vol,
            "prot_min_str_vol": self.prot_min_str_vol,
            "prot_max_cell_vol": self.prot_max_cell_vol,
            "prot_min_cell_vol": self.prot_min_cell_vol
            }
        self.config.set_section(self._section_name, data)
        self.config.save()

    def update(self):
        """Call this to update config values from the Number entities (e.g. after user changes in Home Assistant)"""
        self.prot_rel_trigger_delay = self._prot_rel_trigger_delay.get_state_value()
        self.prot_max_inv_vol = self._prot_max_inv_vol.get_state_value()
        self.prot_min_inv_vol = self._prot_min_inv_vol.get_state_value()
        self.prot_max_current = self._prot_max_current.get_state_value()
        self.prot_min_current = self._prot_min_current.get_state_value()
        self.prot_max_temp = self._prot_max_temp.get_state_value()
        self.prot_max_pack_vol = self._prot_max_pack_vol.get_state_value()
        self.prot_min_pack_vol = self._prot_min_pack_vol.get_state_value()
        self.prot_max_str_vol = self._prot_max_str_vol.get_state_value()
        self.prot_min_str_vol = self._prot_min_str_vol.get_state_value()
        self.prot_max_cell_vol = self._prot_max_cell_vol.get_state_value()
        self.prot_min_cell_vol = self._prot_min_cell_vol.get_state_value()
        self.save()
class soc_config:
    def __init__(self):
        self.config = config()
        self._section_name = "soc_config"
        self.capacity_ah                = 100.0     # 10-1000Ah
        self.initial_soc                = 80.0      # 0-100%
        self.cell_ir                    = 0.004     # 2-8 mΩ at 25°C
        self.ir_ref_temp                = 25.0      # 15-20 °C
        self.ir_temp_coeff              = 0.004     # 0.4%/°C
        self.current_threshold          = 1.0       # 0-2A
        self.voltage_stable_threshold   = 0.01      # 0-0.05V
        self.relaxed_hold_time          = 30.0      # 10 -200s
        self.sampling_interval          = 2.0       # 0.5 - 100s

        self._capacity_ah = Number("Battery Capacity (Ah)", min_val=10.0, max_val=1000.0, step=10.0, mode="slider", default=self.capacity_ah, unit="Ah", cb=self.update)
        self._initial_soc = Number("Initial SOC (%)", min_val=0.0, max_val=100.0, step=1.0, mode="slider", default=self.initial_soc, unit="%", cb=self.update)
        self._cell_ir = Number("Cell Internal Resistance (mΩ)", min_val=1, max_val=10, step=1, mode="slider", default=self.cell_ir*1000, unit="mΩ", cb=self.update)
        self._ir_ref_temp = Number("IR Reference Temperature (°C)", min_val=15.0, max_val=35.0, step=1.0, mode="slider", default=self.ir_ref_temp, unit="°C", cb=self.update)
        self._ir_temp_coeff = Number("IR Temperature Coefficient (%/°C)", min_val=0.0, max_val=2, step=0.1, mode="slider", default=self.ir_temp_coeff*100, unit="%/°C", cb=self.update)
        self._current_threshold = Number("Current Threshold (A)", min_val=0.0, max_val=2.0, step=0.1, mode="slider", default=self.current_threshold, unit="A", cb=self.update)
        self._voltage_stable_threshold = Number("Voltage Stable Threshold (V)", min_val=0.001, max_val=0.05, step=0.001, mode="slider", default=self.voltage_stable_threshold, unit="V", cb=self.update)
        self._relaxed_hold_time = Number("Relaxed Hold Time (s)", min_val=10.0, max_val=200.0, step=10.0, mode="slider", default=self.relaxed_hold_time, unit="s", cb=self.update)
        self._sampling_interval = Number("Sampling Interval (s)", min_val=0.5, max_val=100.0, step=0.5, mode="slider", default=self.sampling_interval, unit="s", cb=self.update)
        self._load_from_config()

    def _load_from_config(self):
        section = self.config.get_section(self._section_name, {})
        self.capacity_ah = section.get("capacity_ah", self.capacity_ah)
        self.initial_soc = section.get("initial_soc", self.initial_soc)
        self.cell_ir = section.get("cell_ir", self.cell_ir)
        self.ir_ref_temp = section.get("ir_ref_temp", self.ir_ref_temp)
        self.ir_temp_coeff = section.get("ir_temp_coeff", self.ir_temp_coeff)
        self.current_threshold = section.get("current_threshold", self.current_threshold)
        self.voltage_stable_threshold = section.get("voltage_stable_threshold", self.voltage_stable_threshold)
        self.relaxed_hold_time = section.get("relaxed_hold_time", self.relaxed_hold_time)
        self.sampling_interval = section.get("sampling_interval", self.sampling_interval)

        self._capacity_ah.set_value(self.capacity_ah)
        self._initial_soc.set_value(self.initial_soc)
        self._cell_ir.set_value(self.cell_ir*1000)
        self._ir_ref_temp.set_value(self.ir_ref_temp)
        self._ir_temp_coeff.set_value(self.ir_temp_coeff*100)
        self._current_threshold.set_value(self.current_threshold)
        self._voltage_stable_threshold.set_value(self.voltage_stable_threshold)
        self._relaxed_hold_time.set_value(self.relaxed_hold_time)
        self._sampling_interval.set_value(self.sampling_interval)
    
    def save(self):
        data = {
            "capacity_ah": self.capacity_ah,
            "initial_soc": self.initial_soc,
            "cell_ir": self.cell_ir,
            "ir_ref_temp": self.ir_ref_temp,
            "ir_temp_coeff": self.ir_temp_coeff,
            "current_threshold": self.current_threshold,
            "voltage_stable_threshold": self.voltage_stable_threshold,
            "relaxed_hold_time": self.relaxed_hold_time,
            "sampling_interval": self.sampling_interval
        }
        self.config.set_section(self._section_name, data)
        self.config.save()
    def update(self):
        """Call this to update config values from the Number entities (e.g. after user changes in Home Assistant)"""
        self.capacity_ah = self._capacity_ah.get_state_value()
        self.initial_soc = self._initial_soc.get_state_value()
        self.cell_ir = self._cell_ir.get_state_value() / 1000
        self.ir_ref_temp = self._ir_ref_temp.get_state_value()
        self.ir_temp_coeff = self._ir_temp_coeff.get_state_value() / 100
        self.current_threshold = self._current_threshold.get_state_value()
        self.voltage_stable_threshold = self._voltage_stable_threshold.get_state_value()
        self.relaxed_hold_time = self._relaxed_hold_time.get_state_value()
        self.sampling_interval = self._sampling_interval.get_state_value()
        self.save()
class master_data:
    def __init__(self):
        self.current = 0.0
        self.vpack = 0.0
        self.tpack = 0.0
        self.tadc = 0.0
        self.vinv = 0.0

        self._current = Sensor("Pack Current", unit = "A", device_class="current")
        self._vpack = Sensor("Pack Voltage", unit = "V", device_class="voltage")
        self._tpack = Sensor("Pack Temperature", unit = "°C", device_class="temperature")
        self._tadc = Sensor("ADC Temperature", unit = "°C", device_class="temperature")
        self._vinv = Sensor("Inverter Voltage", unit = "V", device_class="voltage")

    def update_current(self, value: float):
        """Update pack current and sync with HA sensor"""
        self.current = float(value)
        self._current.set_value(self.current)

    def update_vpack(self, value: float):
        """Update pack voltage and sync with HA sensor"""
        self.vpack = float(value)
        self._vpack.set_value(self.vpack)

    def update_tpack(self, value: float):
        """Update pack temperature and sync with HA sensor"""
        self.tpack = float(value)
        self._tpack.set_value(self.tpack)

    def update_tadc(self, value: float):
        """Update ADC temperature and sync with HA sensor"""
        self.tadc = float(value)
        self._tadc.set_value(self.tadc)

    def update_vinv(self, value: float):
        """Update inverter voltage and sync with HA sensor"""
        self.vinv = float(value)
        self._vinv.set_value(self.vinv)

    # Optional: one method to update everything at once (convenient when reading from BMS)
    def update_all(self, current=0.0, vpack=0.0, tpack=0.0, tadc=0.0, vinv=0.0):
        """Update all master values and sensors in one call"""
        self.update_current(current)
        self.update_vpack(vpack)
        self.update_tpack(tpack)
        self.update_tadc(tadc)
        self.update_vinv(vinv)

class battery:
    def __init__(self):
        self.info    = info_data()
        self.conf    = conf_data()
        self.meas    = None
        self.state   = status_data()
        self.info.init_mqtt_entities()
    def create_measurements(self):
        """Call this after you know ncell & ntemp"""
        self.meas = meas_data(self) 
    def is_data_stable(self):
        """Check if all cell voltages are above 2.5V and below 4.5V"""
        if self.meas is None:
            return False
        for v in self.meas.vcell:
            if not (2.0 < v < 4.5):
                return False
        return True

        
class status_data:
    def __init__(self):
        self.channel_found = False
        self.com_active = False
        self.synced = False
        self.stable = False
        self.ttl = 0
class info_data:
    def __init__(self):
        self.mac        = b''
        self.master_mac = b''
        self.addr       = 0
        self.ncell      = 0
        self.ntemp      = 0
        self.fw_ver     = "0.0.0.0"
        self.hw_ver     = "0.0.0.0"
    
    def init_mqtt_entities(self):
        self._mac = Text(name = f"MAC", default=self.mac.hex(), sub_device={"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"})
        self._master_mac = Text(name = f"Master MAC", default=self.master_mac.hex(), sub_device={"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"})
        self._addr = Text(name = f"Address", default=str(self.addr), sub_device={"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"})
        self._ncell = Text(name = f"Number of Cells", default=str(self.ncell), sub_device={"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"})
        self._ntemp = Text(name = f"Number of Temps", default=str(self.ntemp), sub_device={"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"})
        self._fw_ver = Text(name = f"Firmware Version", default=self.fw_ver, sub_device={"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"})
        self._hw_ver = Text(name = f"Hardware Version", default=self.hw_ver, sub_device={"name": f"Slave {self.addr}", "id": f"slave_{self.addr}"})

    def update_mqtt_entities(self):
        self._mac.set_value(self.mac.hex())
        self._master_mac.set_value(self.master_mac.hex())
        self._addr.set_value(str(self.addr))
        self._ncell.set_value(str(self.ncell))
        self._ntemp.set_value(str(self.ntemp))
        self._fw_ver.set_value(self.fw_ver)
        self._hw_ver.set_value(self.hw_ver)

    def set(self, other: 'info_data'):
        if isinstance(other, info_data):
            self.mac        =    other.mac        
            self.master_mac =    other.master_mac 
            self.addr       =    other.addr       
            self.ncell      =    other.ncell      
            self.ntemp      =    other.ntemp      
            self.fw_ver     =    other.fw_ver     
            self.hw_ver     =    other.hw_ver        
            self.update_mqtt_entities()  

class meas_data:
    def __init__(self, bat: battery):
        self.vcell = [0.0] * bat.info.ncell      # cell voltages in V
        self.vstr = 0.0                           # string / total pack voltage in V
        self.temps = [0.0] * bat.info.ntemp      # temperatures in °C

    # ────────────────────────────────────────────────
    # Cell voltage setters
    # ────────────────────────────────────────────────
    def set_vcell(self, index: int, voltage: float) -> bool:
        """Set voltage for one specific cell.
        Returns True if accepted, False if invalid."""
        if not isinstance(index, int) or not 0 <= index < len(self.vcell):
            return False
        if not isinstance(voltage, (int, float)) or voltage < 0:
            return False
        self.vcell[index] = float(voltage)
        return True

    def set_all_vcells(self, voltages: list[float]) -> bool:
        """Set all cell voltages at once.
        Returns True if list length matches and all values are valid, False otherwise."""
        if not isinstance(voltages, list) or len(voltages) != len(self.vcell):
            return False
        
        # Check all values are non-negative numbers
        if not all(isinstance(v, (int, float)) and v >= 0 for v in voltages):
            return False
        
        self.vcell = [float(v) for v in voltages]
        return True

    # ────────────────────────────────────────────────
    # String voltage setter
    # ────────────────────────────────────────────────
    def set_vstr(self, voltage: float) -> bool:
        """Set string voltage.
        Returns True if accepted, False if invalid."""
        if not isinstance(voltage, (int, float)) or voltage < 0:
            return False
        self.vstr = float(voltage)
        return True

    # ────────────────────────────────────────────────
    # Temperature setters
    # ────────────────────────────────────────────────
    def set_temp(self, index: int, temp: float) -> bool:
        """Set one temperature value.
        Returns True if accepted, False if invalid index."""
        if not isinstance(index, int) or not 0 <= index < len(self.temps):
            return False
        # Temperatures can be negative (e.g. -20°C), so only check type
        if not isinstance(temp, (int, float)):
            return False
        self.temps[index] = float(temp)
        return True

    def set_all_temps(self, temps: list[float]) -> bool:
        """Set all temperatures at once.
        Returns True if length matches and values are valid numbers."""
        if not isinstance(temps, list) or len(temps) != len(self.temps):
            return False
        
        if not all(isinstance(t, (int, float)) for t in temps):
            return False
        self.temps = [float(t) for t in temps]
        print(f"Updated temps: {self.temps}")
        return True

    # ────────────────────────────────────────────────
    # Convenience method for bulk update (common in comms)
    # ────────────────────────────────────────────────
    def update(self,
               vcells: list[float] | None = None,
               vstr: float | None = None,
               temps: list[float] | None = None) -> bool:
        """
        Update multiple fields at once.
        Returns True only if ALL provided values were successfully set.
        """
        success = True
        if vcells is not None:
            success = success and self.set_all_vcells(vcells)
        
        if vstr is not None:
            success = success and self.set_vstr(vstr)
        
        if temps is not None:
            success = success and self.set_all_temps(temps)
        
        return success

    # Optional helper: check if string voltage roughly matches sum of cells
    def is_vstr_consistent(self, max_diff: float = 0.3) -> bool:
        """Check if measured vstr is close to sum of cell voltages."""
        if not self.vcell:
            return True  # no cells → can't check
        calculated_sum = sum(self.vcell)
        return abs(self.vstr - calculated_sum) <= max_diff

class conf_data:
    def __init__(self):
        self.bal_start_vol     = 3.4
        self.bal_threshold     = 0.01      # 10 mV
        self.bal_en            = True
        self.bal_ext_en        = False
        self.ttl               = 10     # 10*30s
    def set(self, other: 'conf_data'):
        if not isinstance(other, conf_data):
            return
        # Voltage: only accept reasonable values
        if isinstance(other.bal_start_vol, (int, float)):
            if 2.8 <= other.bal_start_vol <= 3.8:  
                self.bal_start_vol = float(other.bal_start_vol)
        # Threshold: usually 5–50 mV
        if isinstance(other.bal_threshold, (int, float)):
            if 0.005 <= other.bal_threshold <= 0.100:
                self.bal_threshold = float(other.bal_threshold)
        # Booleans: accept anything truthy/falsy
        if other.bal_en is not None:
            self.bal_en = bool(other.bal_en)
        if other.bal_ext_en is not None:
            self.bal_ext_en = bool(other.bal_ext_en)