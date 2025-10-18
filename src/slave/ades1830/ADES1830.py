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
        self.rdstatd = self.register_map.get_register("RDSTATD")
        self.cfga = self.register_map.get_register("CFGA")
        self.cfgb = self.register_map.get_register("CFGB")
        self.rdcva = self.register_map.get_register("RDCVA")
        self.rdauxd = self.register_map.get_register("RDAUXD")
        self.pwma = self.register_map.get_register("PWMA")
        self.pwmb = self.register_map.get_register("PWMB")
    
    def init(self) -> int:
        self.hal.wakeup()
        self.soft_reset()
        time.sleep_ms(50)
        self.hal.wakeup()
        self.reset_command_counter()
        self.reset_reg_to_default()
        # Turn on Reference voltage
        if self.set_ref_power_up(1) != 1 :
            return 0
        self.start_cell_volt_conv(redundant=False, continuous=False, discharge_permitted=False, reset_filter=False, openwire=0)
        time.sleep_ms(1)
        vcell = self.get_all_cell_voltages()
        nr_of_cells = len([x for x in vcell if x > 1.1]) 
        if nr_of_cells == None: # TODO: magic nr
            return 0
        else:
            return nr_of_cells

    def reset_reg_to_default(self):
        self.register_map.write_defaults()

    def set_ref_power_up(self, value: int):
        self.cfga.set_ref_pwr_up(value)
        return self.cfga.get_ref_pwr_up()
    
    def get_cell_undervoltage(self):
        return self.to_voltage_12bit(self.cfgb.get_undervoltage())

    def get_cell_overvoltage(self):
        return self.to_voltage_12bit(self.cfgb.get_overvoltage())
    
    def set_cell_undervoltage(self, uv : float):
        val = self.to_code_12bit(uv)
        self.cfgb.set_undervoltage(val)
        return self.to_voltage_12bit(self.cfgb.get_undervoltage())

    def set_cell_overvoltage(self, ov : float):
        val = self.to_code_12bit(ov)
        self.cfgb.set_overvoltage(val)
        return self.to_voltage_12bit(self.cfgb.get_overvoltage())
    
    def get_string_voltage(self):
        value = self.rdauxd.get_string_voltage()
        return self.to_voltage_16bit(value, lsb = 0.00375, offset=37.5)

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

    def get_pwm(self):
        # Get integer values from pwma and pwmb
        pwm_int_a = self.pwma.get_pwm()
        pwm_int_b = self.pwmb.get_pwm()
        # Convert integers to bytes (little-endian)
        pwm_bytes_a = pwm_int_a.to_bytes(6,"little")  # 12 4-bit values = 6 bytes
        pwm_bytes_b = pwm_int_b.to_bytes(2,"little")  # 4 4-bit values = 2 bytes

        pwm_bytes = pwm_bytes_a + pwm_bytes_b  # 6 + 2 = 8 bytes
        # Unpack bytes into 4-bit values
        pwm = []
        for b in pwm_bytes:
            high, low = self.unpack_nibbles(b)
            pwm.append(high)
            pwm.append(low)

        # Validate the resulting list
        if len(pwm) != 16:
            raise ValueError("Expected 16 PWM values, got {}".format(len(pwm)))
        if any(not (0 <= x <= 15) for x in pwm):
            raise ValueError("PWM values must be between 0 and 15 (4-bit)")

        return pwm
    
    def get_pwm_cell(self, cell):
        pwm = bytearray(self.get_pwm())
        return pwm[cell]
    
    def set_pwm(self, pwm):
        # Validate input
        if len(pwm) != 16:
            raise ValueError("PWM list must have exactly 16 elements")
        if any(not (0 <= x <= 15) for x in pwm):
            raise ValueError("PWM values must be integers between 0 and 15 (4-bit)")

        # Pack 4-bit values into bytes (two 4-bit values per byte)
        pwm_bytes_a = bytearray()
        for i in range(0, 11, 2):  # Process pwm[0:12] in pairs
            pwm_bytes_a.append(self.pack_nibbles(pwm[i],pwm[i + 1]))

        pwm_bytes_b = bytearray()
        for i in range(12, 15, 2):  # Process pwm[13:] in pairs
            pwm_bytes_b.append(self.pack_nibbles(pwm[i],pwm[i + 1]))

        # Convert packed bytes to integers
        pwm_int_a = int.from_bytes(pwm_bytes_a, "little")
        pwm_int_b = int.from_bytes(pwm_bytes_b, "little")
        # Pass integers to set_pwm methods
        self.pwma.set_pwm(pwm_int_a)
        self.pwmb.set_pwm(pwm_int_b)
    
        return self.get_pwm()
    
    def set_pwm_cell(self, cell_pwm, cell):
        pwm = bytearray(self.get_pwm())
        pwm[cell] = cell_pwm
        self.set_pwm(pwm)
        return self.get_pwm_cell(cell)

    def get_device_id(self):
        return self.rdsid.get_device_id()

    def get_internal_temp(self):
        i_temp = self.rdstata.get_internal_temp()
        return self.code_to_temp(i_temp)

    def get_reference_voltage2(self):
        v_ref2 = self.rdstata.get_second_voltage_ref()
        return self.to_voltage_16bit(v_ref2)
    
    def get_digital_supply_voltage(self):
        dig_sup_vol = self.rdstatb.get_digital_supply_voltage()
        return self.to_voltage_16bit(dig_sup_vol)

    def get_ov_uv_flag(self):
        flags = self.rdstatd.get_ov_uv_flag()
        result_ov = []
        result_uv = []
        for cell in range(15):
            # UV bit is at position 2*cell, OV bit is at position 2*cell + 1
            result_uv.append((flags >> (2 * cell)) & 1)
            result_ov.append((flags >> (2 * cell + 1)) & 1)
        return result_ov,result_uv
            
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

    def clear_ov_uv(self):
        #FIXME: send which flags have to be cleared
        self.hal.command(0x715) #CLOVUV 

    def soft_reset(self):
        self.hal.command(0x027) # SRST
    
    def reset_command_counter(self): # RSTCC
        self.hal.command(0x02E)

    def snapshot(self): # SNAP
        self.hal.command(0x02D)
    
    def release_snapshot(self): #UNSNAP
        self.hal.command(0x02F)

    def mute_discharge(self): #MUTE
        self.hal.command(0x028)

    def unmute_discharge(self): #UNMUTE
        self.hal.command(0x029)

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
        return round(voltage, 2)
    
    def to_code_16bit(self, voltage, lsb = 0.00015, offset = 1.5):
        LSB = lsb
        OFFSET = offset
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

    def to_voltage_16bit(self, digital_code, lsb = 0.00015, offset = 1.5):
        LSB = lsb
        OFFSET = offset

        # Convert 16-bit code to signed integer (-32768 to 32767)
        if digital_code & 0x8000:  # If sign bit is set (negative)
            signed_code = digital_code - 65536
        else:
            signed_code = digital_code

        # Calculate voltage
        voltage = (signed_code * LSB) + OFFSET
        return round(voltage, 3)

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
        return round(temperature, 1)

    def pack_nibbles(self, high_nibble, low_nibble):
        # Ensure inputs are 4-bit values (0 to 15)
        high_nibble &= 0xF  # Mask to keep only the lower 4 bits
        low_nibble &= 0xF   # Mask to keep only the lower 4 bits
        return (high_nibble << 4) | low_nibble

    def unpack_nibbles(self, byte):
        # Ensure the input is a valid byte (0 to 255)
        byte &= 0xFF
        # Extract high nibble (upper 4 bits)
        high_nibble = (byte >> 4) & 0xF
        # Extract low nibble (lower 4 bits)
        low_nibble = byte & 0xF
        return high_nibble, low_nibble