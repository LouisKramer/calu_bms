import time
from common.common import power_config
from lib.virt_slave import *

class PowerManager:
    def __init__(self, cfg: power_config = None, slaves: Slaves = None):
        self.cfg = cfg or power_config()
        self.settle_end_time = 0  # Timestamp for end of settle period
        self.slaves = slaves

    def get_charge_current_from_table(self, soc):
        table = self.cfg.charge_current_table
        # Assume table is sorted by SOC; clamp to bounds
        if soc <= table[0][0]:
            return table[0][1]
        if soc >= table[-1][0]:
            return table[-1][1]
        # Piecewise linear interpolation
        for i in range(len(table) - 1):
            s1, c1 = table[i]
            s2, c2 = table[i + 1]
            if s1 <= soc < s2:
                return c1 + (c2 - c1) * (soc - s1) / (s2 - s1)
        return 0.0  # Fallback, should not reach here

    def update(self, soc, slaves: Slaves = None):
        """
        Compute allowed charge and discharge currents based on current state.
        
        Args:
            soc (float): State of charge (0-100)        
        Returns:
            tuple: (allowed_charge_current, allowed_discharge_current)
        """
        if slaves != None:
            self.slaves = slaves
        if not self.slaves:
            return 0.0, 0.0

        # Aggregate worst-case values across all slaves
        min_cell_voltage = float('inf')
        max_cell_voltage = -float('inf')
        max_temperature  = -float('inf')

        for s in self.slaves:
            if not hasattr(s, 'battery') or not hasattr(s.battery, 'meas'):
                continue
                
            vcells = s.battery.meas.vcell
            temps  = s.battery.meas.temps
            
            if vcells:
                min_cell_voltage = min(min_cell_voltage, min(vcells))
                max_cell_voltage = max(max_cell_voltage, max(vcells))
            
            if temps:
                max_temperature = max(max_temperature, max(temps))

        # If we didn't get any valid measurements → safest possible
        if min_cell_voltage == float('inf') or max_cell_voltage == -float('inf'):
            return 0.0, 0.0
        
        now = time.time()
        
        over_temp = max_temperature > self.cfg.max_temp
        under_voltage = min_cell_voltage < self.cfg.under_voltage_cell
        over_voltage = max_cell_voltage > self.cfg.over_voltage_cell
        low_soc = soc < self.cfg.soc_low_cutoff
        
        # Base currents
        max_current = self.cfg.max_current
        base_charge_current = self.get_charge_current_from_table(soc)
        base_discharge_current = -max_current #TODO: can also implement discharge current table if needed, for now we just use max current for discharge
        
        # Initialize allowed currents
        allowed_charge = base_charge_current
        allowed_discharge = base_discharge_current
        
        # Apply temperature limit: set to 0 if over temp (reduce to safe level)
        if over_temp:
            allowed_charge = 0.0
            allowed_discharge = 0.0
        
        # Apply discharge limits
        if under_voltage or low_soc:
            allowed_discharge = 0.0
        
        # Handle over-voltage and settle logic
        settle_active = self.settle_end_time > now
        if over_voltage:
            allowed_charge = 0.0
            if not settle_active:
                self.settle_end_time = now + self.cfg.charge_settle_time
        elif settle_active:
            allowed_charge = 0.0
        else:
            self.settle_end_time = 0  # Reset if no over-voltage and settle complete
        
        return allowed_charge, allowed_discharge