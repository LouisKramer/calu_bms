from ADES1830_REG import RegisterMap
from ADES1830_HAL import HAL
import time
import struct

class ADES1830:
    def __init__(self):
        self.hal = HAL()
        self.register_map = RegisterMap("registers.json", hal=self.hal)
        self.nr_of_cells = 16
        self.initialize_registers()

    def initialize_registers(self):
        self.rdsid = self.register_map.get_register("RDSID")
        self.rdstata = self.register_map.get_register("RDSTATA")
        self.rdstatb = self.register_map.get_register("RDSTATB")
        self.rdstatc = self.register_map.get_register("RDSTATC")
        self.cfga = self.register_map.get_register("CFGA")
        self.rdcva = self.register_map.get_register("RDCVA")
    
    def set_ref_power_up(self, value: int):
        self.cfga.read()
        self.cfga.set_ref_pwr_up(value)
        self.cfga.read()
        return self.cfga.get_ref_pwr_up()

    def get_cell_voltage(self, cell: int = 1, mode: str = "normal"):
        # Check parameters
        if cell < 1 or cell > self.nr_of_cells:  # Assuming nr_of_cells is defined in the class
            raise ValueError(f"Cell must be between 1 and {self.nr_of_cells}")
        cell_voltages = self.get_all_cell_voltages(mode=mode)
        return cell_voltages[cell-1]
    
    def get_all_cell_voltages(self, mode: str = "normal"):
        # Check parameters
        if mode not in ["normal", "average", "filtered", "switch"]:
            raise ValueError("Mode must be 'normal', 'average', 'filtered', or 'switch'")
        if mode == "normal":
            address=0x00C #RDCVALL
        elif mode == "average":
            address=0x04C #RDACALL
        elif mode == "filtered":
            address=0x018 #RDFCALL
        elif mode == "switch":
            address=0x010 #RDSALL
        data = self.hal.read(address=address,length=32)
        if len(data) != 32:
            raise ValueError("Expected 36-byte array from rdcva.read()")
        raw_voltages = struct.unpack('<16H', data[:32])
        cell_voltages = [voltage * 0.00015 + 1.5 for voltage in raw_voltages]
        return cell_voltages  # Or handle other modes appropriately
        

    def get_device_id(self):
        self.rdsid.read()
        return self.rdsid.get_device_id()

    def get_internal_temp(self):
        self.rdstata.read()
        i_temp = ((self.rdstata.get_internal_temp() * 0.00015 + 1.5) / 0.0075) - 273
        return i_temp

    def get_reference_voltage2(self):
        self.rdstata.read()
        v_ref2 = self.rdstata.get_second_voltage_ref() * 0.00015 + 1.5
        return v_ref2
    
    def get_digital_supply_voltage(self):
        self.rdstatb.read()
        dig_sup_vol = self.rdstatb.get_digital_supply_voltage() * 0.00015 + 1.5
        return dig_sup_vol
    
    def start_cell_volt_conv(self, redundant: bool= False, 
                             continuous: bool = False, 
                             discharge_permitted: bool = False, 
                             reset_filter: bool =False, 
                             openwire: int = 0):
        """Start cell voltage conversion
         Args:
             redundant (bool): Use redundant measurement
             continuous (bool): Continuous conversion mode
             discharge_permitted (bool): Allow cell discharge during conversion
             reset_filter (bool): Reset filter before conversion
             openwire (int): Open wire detection mode (0-3)
         """
        #check parameters
        if openwire < 0 or openwire > 3:
            raise ValueError("openwire must be 0-3")
        #build command
        command = (
            0x260
            | ((1 if redundant else 0) << 8)
            | ((1 if continuous else 0) << 7)
            | ((1 if discharge_permitted else 0) << 4)
            | ((1 if reset_filter else 0) << 2)
            | (openwire & 0x3)
        )
        self.hal.command(command)  # ADCV, RD=0 (Redundant), CONT=1(continuous), DCP=0(discharge permitted), RSTF=0 (reset filter), OW=00 (openwire detection)
    
    def start_s_adc_conv(self, continuous: bool = False,
                         discharge_permitted: bool = False,
                         openwire: int = 0):
        #check parameters
        if openwire < 0 or openwire > 3:
            raise ValueError("openwire must be 0-3")
        #build command
        command = (
            0x068
            | ((1 if continuous else 0) << 7)
            | ((1 if discharge_permitted else 0) << 4)
            | (openwire & 0x3)
        )
        self.hal.command(command)  # ADSV
    
    def start_aux_adc_conv(self, openwire: bool = False, pullup: bool = False):
        command = 0x410 | ((1 if openwire else 0) << 8) | ((1 if pullup else 0) << 7)
        self.hal.command(command)  # ADAX

    def start_aux2_adc_conv(self):
        self.hal.command(0x400)  # ADAX2
    
    def clear_cell_voltage_registers(self):
        self.hal.command(0x711)  # CLRCELL

    def clear_filtered_cell_voltage_registers(self):
        self.hal.command(0x714)  # CLRFC

    def clear_aux_registers(self):
        self.hal.command(0x712)  # CLRAUX

    def clear_s_adc_registers(self):
        self.hal.command(0x716)  # CLRSPIN
    
    def clear_flags(self):
        self.hal.command(0x717)  # CLRFLAG