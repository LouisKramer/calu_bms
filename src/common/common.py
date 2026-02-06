

config_can = {
    'can_tx_pin': 40,      # ESP32 GPIO
    'can_rx_pin': 39,
    'baudrate': 125000,    # 125 kbps
    'update_interval': 1.0
}
class power_config:
    def __init__(self):
        self.max_charge_current = 25.0      #do not go over this at charge and discharge
        self.under_voltage_cell = 2.7       #if lower, set discharge current to 0A only allow charge
        self.over_voltage_cell = 3.65       #if higher set charge current to 0 A and settle
        self.charge_settle_time = 600       #settle time in s, 
        self.soc_low_cutoff = 10.0          #if lower, reduce discharge current to 0 A only allow charge
        self.max_temp = 50.0                #if any temp is greater than this, reduce charge/discharge current
        self.charge_current_table = [       #charge current depending on soc
        (0, 2.0),
        (10, self.max_charge_current),
        (90, self.max_charge_current),
        (95, 10.0),
        (98, 5.0),
        (99, 2.0),
        (100, 2.0)# still charging possible TODO: to be tested
    ]
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
        self.vcell = [0] * bat.info.ncell
        self.vstr = 0
        self.temps = [0] * bat.info.ntemp

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