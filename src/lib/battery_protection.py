import asyncio
import time
from machine import Pin
from lib.virt_slave import *

class Fault_types:
    NO_FAULT = "No fault"
    FAULT_CELL_OV = "Cell Overvoltage"
    FAULT_CELL_UV = "Cell Undervoltage"
    FAULT_CELL_CRIT_OV = "Cell Critical Overvoltage"
    FAULT_CELL_CRIT_UV = "Cell Critical Undervoltage"

    FAULT_STR_OV = "String Overvoltage"
    FAULT_STR_UV = "String Undervoltage"
    FAULT_STR_CRIT_OV = "String Critical Overvoltage"
    FAULT_STR_CRIT_UV = "String Critical Undervoltage"

class Fault_Severity:
    # Fault severity types:
    NOTE        = 0
    INFO        = 1
    WARNING     = 2
    ERROR       = 3
    CRITICAL    = 4
    FALTAL      = 5

    # Optional human-readable names
    SEVERITY_NAMES = {
        NOTE: "NOTE",
        WARNING: "WARNING",
        CRITICAL: "CRITICAL"
    }

class Fault:
    # Class-level list to store all instances
    _registry = []
    def __init__(self, debounce_sec= 2.0, severity = Fault_Severity.NOTE, name = None):
        self.severity = severity
        self.fault_type = Fault_types.NO_FAULT
        self.fault_msg = ""
        self._set_time = 0
        self.active = False
        self.debounce = max(0.1, debounce_sec)  # min 100ms
        self.name = name or "Unnamed"
        self.__class__._registry.append(self)

    def set(self, fault_type, msg=""):
        if fault_type == Fault_types.NO_FAULT:
            self.clear()
            return

        now = time.time()
        if not self.active:
            # First activation
            self.fault_type = fault_type
            self.fault_msg = str(msg)[:64]  # limit string size
            self._set_time = now
            self.active = True
        else:
            # Already active: update time to extend debounce
            self._set_time = now
            if msg:
                self.fault_msg = str(msg)[:64]

    def clear(self):
        self.active = False
        self.fault_type = Fault_types.NO_FAULT
        self.fault_msg = ""
        self._set_time = 0

    def is_debounced(self):
        if not self.active:
            return False
        return (time.time() - self._set_time) >= self.debounce_sec

    def since(self):
        """Return seconds since fault was set, or None"""
        if not self.active:
            return None
        return time.time() - self._set_time
        
# --- Class Methods ---
    @classmethod
    def register(cls, fault_obj):
        if fault_obj not in cls._registry:
            cls._registry.append(fault_obj)

    @classmethod
    def unregister(cls, fault_obj):
        if fault_obj in cls._registry:
            cls._registry.remove(fault_obj)

    @classmethod
    def get_debounced(cls):
        now = time.time()
        result = []
        for f in cls._registry:
            if f.is_debounced():
                result.append({
                    'name': f.name,
                    'type': f.fault_type,
                    'msg': f.fault_msg,
                    'sev': f.severity,
                    'sev_name': Fault_Severity.SEVERITY_NAMES[f.severity],
                    'since': now - f._set_time
                })
        return result

    @classmethod
    def has_critical(cls):
        return any(f.is_debounced() and f.severity == Fault_Severity.CRITICAL for f in cls._registry)
    
    @classmethod
    def has_warning(cls):
        return any(f.is_debounced() and f.severity == Fault_Severity.WARNING for f in cls._registry)

    @classmethod
    def clear_all(cls):
        for f in cls._registry:
            f.clear()

    @classmethod
    def count_active(cls):
        return sum(1 for f in cls._registry if f.active)

class CellProtection:
    def __init__(self, config, vcell, addr, pos):
        self.vcell = vcell
        self.addr = addr
        self.cell_pos = pos
        self.v_cell_max             = config.get('over_voltage_cell', 3.65)
        self.v_cell_critical_max    = config.get('critical_over_voltage_cell', 3.70)
        self.v_cell_min             = config.get('under_voltage_cell', 2.5)
        self.v_cell_critical_min    = config.get('critical_under_voltage_cell', 2.30)
        self.hyst_v                 = config.get('hysteresis_voltage', 0.05)
        self.fault = Fault(debounce_sec=2.0, )

    def check_cell_voltage(self):
        # === Critical Over-Voltage ===
        if self.vcell > self.v_cell_critical_max:
            self.fault.set(Fault.CRITICAL, Fault_types.FAULT_CELL_CRIT_OV)
        elif self.vcell < (self.v_cell_critical_max - self.hyst_v):
            self.fault.clear()
         # === Over-Voltage ===
        if self.vcell > self.v_cell_max:
            self.fault.set(Fault.WARNING, Fault_types.FAULT_CELL_OV)
        elif self.vcell < (self.v_cell_max - self.hyst_v):
            self.fault.clear()

        # === Critical Uncer-Voltage ===
        if self.vcell < self.v_cell_critical_min:
            self.fault.set(Fault.CRITICAL, Fault_types.FAULT_CELL_CRIT_UV)
        elif self.vcell > (self.v_cell_critical_min + self.hyst_v):
            self.fault.clear()
         # === under-Voltage ===
        if self.vcell < self.v_cell_min:
            self.fault.set(Fault.WARNING, Fault_types.FAULT_CELL_UV)
        elif self.vcell > (self.v_cell_min + self.hyst_v):
            self.fault.clear()

class StringProtection:
    def __init__(self, config, slave: virt_slave):
        self.vstr = slave.vstr
        self.addr = slave.string_address
        self.fault = Fault
        self.v_str_max             = config.get('over_voltage_cell', 3.65)           * slave.nr_of_cells    
        self.v_str_critical_max    = config.get('critical_over_voltage_cell', 3.70)  * slave.nr_of_cells    
        self.v_str_min             = config.get('under_voltage_cell', 2.5)           * slave.nr_of_cells    
        self.v_str_critical_min    = config.get('critical_under_voltage_cell', 2.30) * slave.nr_of_cells    
        self.hyst_v                = config.get('hysteresis_voltage', 0.05)          * slave.nr_of_cells  
        self.cells = []
        for i, c in enumerate(slave.vcell):
            self.cells.append(self.CellProtection(config, c, self.addr, i))

    def _check_str_temperatures(self, str_temperatures):
        #TODO: implement
        pass
    def check_string(self):
        for c in self.cells:
            c.check_cell()
        # === Critical Over-Voltage ===
        if self.vstr > self.v_str_critical_max:
            self.fault.set_fault(Fault_types.FAULT_STR_CRIT_OV)
        elif self.vstr < (self.v_str_critical_max - self.hyst_v):
            self.fault.reset_fault()
         # === Over-Voltage ===
        if self.vstr > self.v_str_max:
            self.fault.set_fault(Fault_types.FAULT_STR_OV)
        elif self.vstr < (self.v_str_max - self.hyst_v):
            self.fault.reset_fault()

        # === Critical Uncer-Voltage ===
        if self.vstr < self.v_str_critical_min:
            self.fault.set_fault(Fault_types.FAULT_STR_CRIT_UV)
        elif self.vstr > (self.v_str_critical_min + self.hyst_v):
            self.fault.reset_fault()
         # === under-Voltage ===
        if self.vstr < self.v_str_min:
            self.fault.set_fault(Fault_types.FAULT_STR_UV)
        elif self.vstr > (self.v_str_min + self.hyst_v):
            self.fault.reset_fault()


class PackProtection: 
    def __init__(self, config, current_sensor=None, inverter_en_pin=None, slaves:Slaves = None):
        self.strings = []
        for s in enumerate(slaves): 
            self.strings.append(self.StringProtection(config, s))

    def check_pack(self):
        for s in self.strings:
            s.check_string()

    def check_imbalance(self):
        v_max = max(self.vcell)
        v_min = min(self.vcell)
        if (v_max - v_min) > self.imbalance_thresh:
            self._set_fault('imbalance', True)
        else:
            pass

    def _check_pack_voltage(self, pack_voltage):
        self.last_pack_voltage = pack_voltage
        if pack_voltage > self.v_pack_critical_max:
            self._set_fault('pack_critical_over_voltage', True)
        elif pack_voltage < (self.v_pack_critical_max - self.hyst_v * self.n):
            self._set_fault('pack_critical_over_voltage', False)

        if pack_voltage > self.v_pack_max:
            self._set_fault('pack_over_voltage', True)
        elif pack_voltage < (self.v_pack_max - self.hyst_v * self.n):
            self._set_fault('pack_over_voltage', False)

        if pack_voltage < self.v_pack_critical_min:
            self._set_fault('pack_critical_under_voltage', True)
        elif pack_voltage > (self.v_pack_critical_min + self.hyst_v * self.n):
            self._set_fault('pack_critical_under_voltage', False)

        if pack_voltage < self.v_pack_min:
            self._set_fault('pack_under_voltage', True)
        elif pack_voltage > (self.v_pack_min + self.hyst_v * self.n):
            self._set_fault('pack_under_voltage', False)

    def _check_current(self, current):
        self.last_current = current
        if abs(current) > self.i_max * 1.1:
            self._set_fault('over_current', True)
        elif abs(current) < self.i_max * 0.9:
            self._set_fault('over_current', False)

        if abs(current) > self.i_short:
            self._set_fault('short_circuit', True)

    def _check_temperature(self, temp):
        self.last_temp = temp
        if temp > self.t_max:
            self._set_fault('over_temp', True)
        elif temp < self.t_max - 5:
            self._set_fault('over_temp', False)

        if temp < self.t_min:
            self._set_fault('under_temp', True)
        elif temp > self.t_min + 5:
            self._set_fault('under_temp', False)

    def _check_soc(self, soc):
        self.last_soc = soc
        if soc > 99.9:
            self._set_fault('soc_full', True)
        if soc < self.soc_low:
            self._set_fault('soc_low', True)
        elif soc > self.soc_low + 5:
            self._set_fault('soc_low', False)
        if soc < self.soc_critical:
            self._set_fault('soc_critical', True)

    def check_faults(self):
        faults = Fault.get_all_debounced_faults()


class BatteryProtection:
    """
    Advanced BMS with:
    - Per-cell monitoring
    - SOC-dependent charge current
    - Soft discharge limit (current to 0 A)
    - HARD cut-off on: critical OV/UV, short, over-temp, hardware fault
    - Inverter enable + current request
    """

    def __init__(self, config, current_sensor=None, inverter_en_pin=None, slaves = None):
        """
        config (dict):
            inverter_en_pin             : int (GPIO) - HIGH = enabled
            max_current                 : float (A)
            charge_current_table        : list[(soc, current)]
            over_voltage_cell           : float (V) - soft limit
            critical_over_voltage_cell  : float (V) - HARD cut-off
            under_voltage_cell          : float (V) - soft limit
            critical_under_voltage_cell : float (V) - HARD cut-off
            over_temp                   : float (°C)
            under_temp                  : float (°C)
            soc_low_cutoff              : float (%) - soft
            soc_critical_cutoff         : float (%) - hard
            short_circuit_threshold     : float (A)
            cell_imbalance_threshold    : float (V)
            debounce_time               : float (s)
            hysteresis_voltage          : float (V/cell)
            use_hardware_fault          : bool
        """
        if slaves is None or not slaves.isinstance(Slaves):
            raise ValueError
        self.config = config
        self.n = slaves.get_nr_of_total_cells()
        self.current_sensor = current_sensor
        self.use_hw_fault = config.get('use_hardware_fault', True)

        # --- Inverter Control ---
        self.inverter_en = Pin(inverter_en_pin, Pin.OUT) if inverter_en_pin else None
        if self.inverter_en:
            self.inverter_en.value(1)

        # --- Current Limits ---
        self.i_max = config['max_current']
        self.charge_table = sorted(config.get('charge_current_table', [
            (0, self.i_max),
            (90, self.i_max),
            (95, 10.0),
            (99, 2.0),
            (100, 0.0)
        ]), key=lambda x: x[0])

        # --- Voltage Limits ---
        self.v_cell_max             = config['over_voltage_cell']
        self.v_cell_critical_max    = config.get('critical_over_voltage_cell', 3.70)
        self.v_cell_min             = config['under_voltage_cell']
        self.v_cell_critical_min    = config.get('critical_under_voltage_cell', 2.30)

        self.v_str_max              = self.v_cell_max * self.n
        self.v_str_critical_max     = self.v_cell_critical_max * self.n
        self.v_str_min              = self.v_cell_min * self.n
        self.v_str_critical_min     = self.v_cell_critical_min * self.n

        self.v_pack_max = self.v_cell_max * self.n
        self.v_pack_critical_max = self.v_cell_critical_max * self.n
        self.v_pack_min = self.v_cell_min * self.n
        self.v_pack_critical_min = self.v_cell_critical_min * self.n

        # --- Other Limits ---
        self.t_max = config['over_temp']
        self.t_min = config['under_temp']
        self.soc_low = config['soc_low_cutoff']
        self.soc_critical = config.get('soc_critical_cutoff', 2.0)
        self.i_short = config['short_circuit_threshold']
        self.imbalance_thresh = config.get('cell_imbalance_threshold', 0.08)

        # --- Debounce & Hysteresis ---
        self.debounce = config.get('debounce_time', 2.0)
        self.hyst_v = config.get('hysteresis_voltage', 0.05)

        # --- State ---
        self.fault_active = {}
        self.cell_faults = {}
        self.last_cell_voltages = [0.0] * self.n
        self.last_pack_voltage = 0.0
        self.last_current = 0.0
        self.last_temp = 25.0
        self.last_soc = 50.0
        self.requested_charge_current = self.i_max
        self.requested_discharge_current = self.i_max

        # --- Hardware Fault ---
        if self.use_hw_fault and self.current_sensor is not None:
            try:
                self.current_sensor.set_fault_callback(self._hardware_overcurrent)
                print("Hardware fault callback registered")
            except Exception as e:
                print("Callback failed:", e)
                self.use_hw_fault = False

    # ------------------------------------------------------------------
    # Hardware Over-Current to HARD Cut-Off
    # ------------------------------------------------------------------
    def _hardware_overcurrent(self):
        print("HARDWARE OVER-CURRENT to INVERTER OFF")
        if self.inverter_en:
            self.inverter_en.value(0)
        self._set_fault('hardware_overcurrent', True)

    # ------------------------------------------------------------------
    # Fault Management
    # ------------------------------------------------------------------
    def _set_fault(self, fault_type, active, str_addr = None, cell_idx=None): 
        if cell_idx is not None and str_addr is not None:
            key = f"{fault_type}_{str_addr}_{cell_idx}"
        elif str_addr is not None:
            key = f"{fault_type}_{str_addr}"
        else:
            key = fault_type
        now = time.time()
        if active:
            if key not in self.fault_active:
                self.fault_active[key] = now
        else:
            self.fault_active.pop(key, None)

    def _is_debounced(self, fault_type, str_addr = None, cell_idx=None):
        if cell_idx is not None and str_addr is not None:
            key = f"{fault_type}_{str_addr}_{cell_idx}"
        elif str_addr is not None:
            key = f"{fault_type}_{str_addr}"
        else:
            key = fault_type
        if key not in self.fault_active:
            return False
        return (time.time() - self.fault_active[key]) >= self.debounce

    # ------------------------------------------------------------------
    # Current Limit: SOC-Dependent Charge
    # ------------------------------------------------------------------
    def _get_max_charge_current(self, soc):
        for soc_thresh, curr in self.charge_table:
            if soc <= soc_thresh:
                return curr
        return 0.0

    # ------------------------------------------------------------------
    # Sensor Checks
    # ------------------------------------------------------------------
    def _check_cell_voltages(self, slave):
        self.last_cell_voltages = slave.vcell[:]
        self.cell_faults = {}

        critical_ov = False
        critical_uv = False

        for i, v in enumerate(slave.vcell):
            # === Over-Voltage ===
            if v > self.v_cell_critical_max:
                critical_ov = True
                self._set_fault('critical_over_voltage', True, slave.string_address, i)
                self.cell_faults.setdefault(i, []).append('critical_over_voltage')
            elif v < (self.v_cell_critical_max - self.hyst_v):
                self._set_fault('critical_over_voltage', False, slave.string_address, i)

            if v > self.v_cell_max:
                self._set_fault('over_voltage', True, slave.string_address, i)
                self.cell_faults.setdefault(i, []).append('over_voltage')
            elif v < (self.v_cell_max - self.hyst_v):
                self._set_fault('over_voltage', False, slave.string_address, i)

            # === Under-Voltage ===
            if v < self.v_cell_critical_min:
                critical_uv = True
                self._set_fault('critical_under_voltage', True, slave.string_address, i)
                self.cell_faults.setdefault(i, []).append('critical_under_voltage')
            elif v > (self.v_cell_critical_min + self.hyst_v):
                self._set_fault('critical_under_voltage', False, slave.string_address, i)

            if v < self.v_cell_min:
                self._set_fault('under_voltage', True, slave.string_address, i)
                self.cell_faults.setdefault(i, []).append('under_voltage')
            elif v > (self.v_cell_min + self.hyst_v):
                self._set_fault('under_voltage', False, slave.string_address, i)

        if critical_ov:
            self._set_fault('critical_over_voltage', True)
        if critical_uv:
            self._set_fault('critical_under_voltage', True)

        # Imbalance
        v_max = max(slave.vcell)
        v_min = min(slave.vcell)
        if (v_max - v_min) > self.imbalance_thresh:
            self._set_fault('imbalance', True)
        else:
            self._set_fault('imbalance', False)

    def _check_str_voltage(self, str_voltages):
        #TODO: implement
        pass
    

    def _check_pack_voltage(self, pack_voltage):
        self.last_pack_voltage = pack_voltage
        if pack_voltage > self.v_pack_critical_max:
            self._set_fault('pack_critical_over_voltage', True)
        elif pack_voltage < (self.v_pack_critical_max - self.hyst_v * self.n):
            self._set_fault('pack_critical_over_voltage', False)

        if pack_voltage > self.v_pack_max:
            self._set_fault('pack_over_voltage', True)
        elif pack_voltage < (self.v_pack_max - self.hyst_v * self.n):
            self._set_fault('pack_over_voltage', False)

        if pack_voltage < self.v_pack_critical_min:
            self._set_fault('pack_critical_under_voltage', True)
        elif pack_voltage > (self.v_pack_critical_min + self.hyst_v * self.n):
            self._set_fault('pack_critical_under_voltage', False)

        if pack_voltage < self.v_pack_min:
            self._set_fault('pack_under_voltage', True)
        elif pack_voltage > (self.v_pack_min + self.hyst_v * self.n):
            self._set_fault('pack_under_voltage', False)

    def _check_current(self, current):
        self.last_current = current
        if abs(current) > self.i_max * 1.1:
            self._set_fault('over_current', True)
        elif abs(current) < self.i_max * 0.9:
            self._set_fault('over_current', False)

        if abs(current) > self.i_short:
            self._set_fault('short_circuit', True)

    def _check_temperature(self, temp):
        self.last_temp = temp
        if temp > self.t_max:
            self._set_fault('over_temp', True)
        elif temp < self.t_max - 5:
            self._set_fault('over_temp', False)

        if temp < self.t_min:
            self._set_fault('under_temp', True)
        elif temp > self.t_min + 5:
            self._set_fault('under_temp', False)

    def _check_str_temperatures(self, str_temperatures):
        #TODO: implement
        pass

    def _check_soc(self, soc):
        self.last_soc = soc
        if soc > 99.9:
            self._set_fault('soc_full', True)
        if soc < self.soc_low:
            self._set_fault('soc_low', True)
        elif soc > self.soc_low + 5:
            self._set_fault('soc_low', False)
        if soc < self.soc_critical:
            self._set_fault('soc_critical', True)

    # ------------------------------------------------------------------
    # Current Control Logic
    # ------------------------------------------------------------------
    def _update_current_limits(self):
        charge_curr = self.i_max
        dis_curr = self.i_max

        # === HARD CUT-OFF: Critical faults ===
        hard_fault = (
            self._is_debounced('hardware_overcurrent') or
            self._is_debounced('critical_over_voltage') or
            self._is_debounced('pack_critical_over_voltage') or
            self._is_debounced('critical_under_voltage') or
            self._is_debounced('pack_critical_under_voltage') or
            self._is_debounced('short_circuit') or
            self._is_debounced('over_temp') or
            self._is_debounced('under_temp')
        )
        if hard_fault:
            charge_curr = dis_curr = 0.0
            if self.inverter_en:
                self.inverter_en.value(0)
            self.requested_charge_current = 0.0
            self.requested_discharge_current = 0.0
            return charge_curr, dis_curr

        # === System OK ===
        if self.inverter_en:
            self.inverter_en.value(1)

        # === Charge: SOC table ===
        charge_curr = self._get_max_charge_current(self.last_soc)

        # === Discharge: soft limit ===
        if (any(self._is_debounced('under_voltage', i) for i in range(self.n)) or
            self._is_debounced('soc_low')):
            dis_curr = 0.0
        if self._is_debounced('soc_critical'):
            dis_curr = 0.0

        # === Over-current (software) ===
        if self._is_debounced('over_current'):
            charge_curr = min(charge_curr, 5.0)
            dis_curr = min(dis_curr, 5.0)

        self.requested_charge_current = max(0.0, charge_curr)
        self.requested_discharge_current = max(0.0, dis_curr)
        return charge_curr, dis_curr

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    #FIXME: Pack consists of up to 16 stings with each up to 16 cells each pack pro.
    async def update(self, cell_voltages, pack_voltage, current, temperature, soc_percent, slaves):
        if slaves.isinstance(Slaves):
            for s in slaves:
                if s.isinstance(virt_slave):
                    self._check_cell_voltages(s)
                    self._check_str_voltage(s)
                    self._check_str_temperatures(s.temp)
        self._check_pack_voltage(pack_voltage)
        self._check_current(current)
        self._check_temperature(temperature)
        self._check_soc(soc_percent)
        charge_curr, dis_curr = self._update_current_limits()

        cell_report = {f"cell_{i}": f for i, f in self.cell_faults.items()}
        return {
            'inverter_enabled': self.inverter_en.value() if self.inverter_en else True,
            'charge_current_limit': charge_curr,
            'discharge_current_limit': dis_curr,
            'pack_voltage': pack_voltage,
            'cell_voltages': cell_voltages,
            'current': current,
            'temperature': temperature,
            'soc': soc_percent,
            'faults': {
                'active': list(self.fault_active.keys()),
                'cells': cell_report,
                'imbalance': self._is_debounced('imbalance'),
                'hardware_overcurrent': self._is_debounced('hardware_overcurrent'),
                'critical_over_voltage': self._is_debounced('critical_over_voltage'),
                'critical_under_voltage': self._is_debounced('critical_under_voltage'),
                'critical_shutdown': self.inverter_en.value() == 0 if self.inverter_en else False
            }
        }

    def clear_faults(self):
        self.fault_active.clear()
        self.cell_faults.clear()
        if self.inverter_en:
            self.inverter_en.value(1)

    def force_enable(self):
        if self.inverter_en:
            self.inverter_en.value(1)

    def force_disable(self):
        if self.inverter_en:
            self.inverter_en.value(0)

    def get_status(self):
        return {
            'inverter': 'ON' if (self.inverter_en and self.inverter_en.value()) else 'OFF',
            'charge_limit_A': self.requested_charge_current,
            'discharge_limit_A': self.requested_discharge_current,
            'faults': list(self.fault_active.keys()) or ['none']
        }