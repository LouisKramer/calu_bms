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
        self.cfgb = self.register_map.get_register("CFGB")
        self.rdcva = self.register_map.get_register("RDCVA")
    
    def set_ref_power_up(self, value: int):
        self.cfga.read()
        self.cfga.set_ref_pwr_up(value)
        self.cfga.read()
        return self.cfga.get_ref_pwr_up()
    
    def get_cell_undervoltage(self):
        self.cfgb.read()
        return self.to_voltage_12bit(self.cfgb.get_undervoltage())

    def get_cell_overvoltage(self):
        self.cfgb.read()
        return self.to_voltage_12bit(self.cfgb.get_overvoltage())
    
    def set_cell_undervoltage(self, uv):
        self.cfgb.read()
        val = self.to_code_12bit(uv)
        self.cfgb.set_undervoltage(val)
        self.cfgb.read()
        return self.cfgb.get_undervoltage()

    def set_cell_overvoltage(self,ov):
        self.cfgb.read()
        self.cfgb.set_overvoltage(ov)
        self.cfgb.read()
        return self.cfgb.get_overvoltage()
    
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
        data = self.hal.read(address=address, length=32)
        if len(data) != 32:
            raise ValueError("Expected 36-byte array from rdcva.read()")
        raw_voltages = struct.unpack('<16H', data[:32])
        cell_voltages = [self.to_voltage_16bit(voltage) for voltage in raw_voltages]
        return cell_voltages  # Or handle other modes appropriately

    def get_device_id(self):
        self.rdsid.read()
        return self.rdsid.get_device_id()

    def get_internal_temp(self):
        self.rdstata.read()
        i_temp = self.rdstata.get_internal_temp()
        return self.code_to_temp(i_temp)

    def get_reference_voltage2(self):
        self.rdstata.read()
        v_ref2 = self.rdstata.get_second_voltage_ref()
        return self.to_voltage_16bit(v_ref2)
    
    def get_digital_supply_voltage(self):
        self.rdstatb.read()
        dig_sup_vol = self.rdstatb.get_digital_supply_voltage()
        return self.to_voltage_16bit(dig_sup_vol)

#################################################################
#  Commands
#################################################################        
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
#################################################################
#  Conversion helpers
#################################################################
    def to_code_12bit(self, voltage):
        LSB = 0.0024
        OFFSET = 1.5
        # Calculate digital code
        digital_code = (voltage - OFFSET) / LSB
        # Round to nearest integer
        digital_code = round(digital_code)
        # Clamp to signed 12-bit range (-2048 to 2047)
        digital_code = max(min(digital_code, 2047), -2048)
        # Convert to 12-bit two's complement (0x000 to 0xFFF representation)
        if digital_code < 0:
            digital_code = (digital_code + 4096) & 0xFFF  # Two's complement for 12 bits
        return digital_code
    
    def to_voltage_12bit(self, digital_code):
        LSB = 0.0024
        OFFSET = 1.5
        # Convert 12-bit code to signed integer (-2048 to 2047)
        if digital_code & 0x800:  # If sign bit is set (negative)
            signed_code = digital_code - 4096
        else:
            signed_code = digital_code
        # Calculate voltage
        voltage = (signed_code * LSB) + OFFSET
        return voltage
    
    def to_code_16bit(self, voltage):
        LSB = 0.00015
        OFFSET = 1.5
        # Calculate digital code
        digital_code = (voltage - OFFSET) / LSB
        # Round to nearest integer
        digital_code = round(digital_code)
        # Clamp to signed 16-bit range (-32768 to 32767)
        digital_code = max(min(digital_code, 32767), -32768)
        # Convert to 16-bit two's complement (0x0000 to 0xFFFF representation)
        if digital_code < 0:
            digital_code = (digital_code + 65536) & 0xFFFF  # Two's complement for 16 bits
        return digital_code

    def to_voltage_16bit(self, digital_code):
        LSB = 0.00015
        OFFSET = 1.5

        # Convert 16-bit code to signed integer (-32768 to 32767)
        if digital_code & 0x8000:  # If sign bit is set (negative)
            signed_code = digital_code - 65536
        else:
            signed_code = digital_code

        # Calculate voltage
        voltage = (signed_code * LSB) + OFFSET
        return voltage

    def temp_to_16bit_code(self, temperature):
        LSB = 0.02
        OFFSET = -73.0
        # Calculate digital code
        digital_code = (temperature - OFFSET) / LSB
        # Round to nearest integer
        digital_code = round(digital_code)
        # Clamp to signed 16-bit range (-32768 to 32767)
        digital_code = max(min(digital_code, 32767), -32768)
        # Convert to 16-bit two's complement (0x0000 to 0xFFFF representation)
        if digital_code < 0:
            digital_code = (digital_code + 65536) & 0xFFFF  # Two's complement for 16 bits
        return digital_code

    def code_to_temp(self, digital_code):
        LSB = 0.02
        OFFSET = -73.0
        # Convert 16-bit code to signed integer (-32768 to 32767)
        if digital_code & 0x8000:  # If sign bit is set (negative)
            signed_code = digital_code - 65536
        else:
            signed_code = digital_code
        # Calculate temperature
        temperature = (signed_code * LSB) + OFFSET
        return temperature