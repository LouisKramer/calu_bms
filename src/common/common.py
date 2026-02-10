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

        self._max_current = Number("Max Charge Current", min_val=0.0, max_val=100.0, step=0.5, mode="slider", default=25.0, unit="A", cb=self.update)
        self._under_voltage_cell = Number("Under Voltage Cell", min_val=2.0, max_val=3.0, step=0.1, mode="slider", default=2.7, unit="V", cb=self.update)
        self._over_voltage_cell = Number("Over Voltage Cell", min_val=3.0, max_val=4.5, step=0.1, mode="slider", default=3.65, unit="V", cb=self.update)
        self._charge_settle_time = Number("Charge Settle Time", min_val=10, max_val=3600, step=10, mode="slider", default=600, unit="s", cb=self.update)
        self._soc_low_cutoff = Number("SOC Low Cutoff", min_val=0, max_val=100, step=1, mode="slider", default=10, unit="%", cb=self.update)
        self._max_temp = Number("Max Temperature", min_val=0, max_val=100, step=1, mode="slider", default=50, unit="°C", cb=self.update)
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

    def set(self, other: 'protection_config'):
        if not isinstance(other, protection_config):
            raise TypeError("Expected protection_config instance")

        # Format: (min, max, value, attribute_name, description)
        checks = [
            (  5.0,   300.0, other.prot_rel_trigger_delay, "prot_rel_trigger_delay", "5–300 seconds"),
            (200.0,  1500.0, other.prot_max_inv_vol,       "prot_max_inv_vol",       "inverter max voltage (V)"),
            (100.0,   800.0, other.prot_min_inv_vol,       "prot_min_inv_vol",       "inverter min voltage (V)"),
            ( 10.0,   400.0, other.prot_max_current,       "prot_max_current",       "max current (A)"),
            (-400.0,   10.0, other.prot_min_current,       "prot_min_current",       "min current (A) — discharge limit"),
            ( 40.0,   100.0, other.prot_max_temp,          "prot_max_temp",          "max temperature (°C)"),
            (200.0,  1500.0, other.prot_max_pack_vol,      "prot_max_pack_vol",      "pack max voltage (V)"),
            (100.0,   800.0, other.prot_min_pack_vol,      "prot_min_pack_vol",      "pack min voltage (V)"),
            ( 80.0,   200.0, other.prot_max_str_vol,       "prot_max_str_vol",       "string max voltage (V)"),
            ( 20.0,    80.0, other.prot_min_str_vol,       "prot_min_str_vol",       "string min voltage (V)"),
            ( 3.40,   4.25,  other.prot_max_cell_vol,      "prot_max_cell_vol",      "cell max voltage (V)"),
            ( 2.30,   3.00,  other.prot_min_cell_vol,      "prot_min_cell_vol",      "cell min voltage (V)"),
        ]

        for minv, maxv, value, name, desc in checks:
            if not (minv <= value <= maxv):
                raise ValueError(
                    f"protection_config.{name} must be between {minv} and {maxv} ({desc}), "
                    f"got {value}"
                )

        # If all checks pass → copy all attributes
        self.__dict__.update(other.__dict__)


class soc_config:
    def __init__(self):
        self.capacity_ah                = 100.0     # 10-1000Ah
        self.initial_soc                = 80.0      # 0-100%
        self.cell_ir                    = 0.004     # 2-8 mΩ at 25°C
        self.ir_ref_temp                = 25.0      # 15-20 °C
        self.ir_temp_coeff              = 0.004     # 0.4%/°C
        self.current_threshold          = 1.0       # 0-2A
        self.voltage_stable_threshold   = 0.01      # 0-0.05V
        self.relaxed_hold_time          = 30.0      # 10 -200s
        self.sampling_interval          = 2.0       # 0.5 - 100s

    def set(self, other: 'soc_config'):
        if not isinstance(other, soc_config):
            raise TypeError("Expected soc_config instance")

        checks = [
            (10.0, 1000.0, other.capacity_ah,             "capacity_ah",                "10-1000 Ah"),
            (0.0,  100.0,  other.initial_soc,             "initial_soc",                "0-100 %"),
            (0.002,0.008,  other.cell_ir,                 "cell_ir",                    "2-8 mΩ"),
            (15.0, 30.0,   other.ir_ref_temp,             "ir_ref_temp",                "15-30 °C"),
            (0.002,0.007,  other.ir_temp_coeff,           "ir_temp_coeff",              "0.2-0.7 %/°C"),
            (0.0,  2.0,    other.current_threshold,       "current_threshold",          "0-2 A"),
            (0.0,  0.05,   other.voltage_stable_threshold,"voltage_stable_threshold",   "0-0.05 V"),
            (10.0, 200.0,  other.relaxed_hold_time,       "relaxed_hold_time",          "10-200 s"),
            (0.5,  100.0,  other.sampling_interval,       "sampling_interval",          "0.5-100 s"),
        ]

        for minv, maxv, value, name, desc in checks:
            if not (minv <= value <= maxv):
                raise ValueError(f"{name} must be between {minv} and {maxv} ({desc})")

        # assign
        self.__dict__.update(other.__dict__)

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
     
    def set(self, other: 'info_data'):
        if isinstance(other, info_data):
            self.mac        =    other.mac        
            self.master_mac =    other.master_mac 
            self.addr       =    other.addr       
            self.ncell      =    other.ncell      
            self.ntemp      =    other.ntemp      
            self.fw_ver     =    other.fw_ver     
            self.hw_ver     =    other.hw_ver          

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