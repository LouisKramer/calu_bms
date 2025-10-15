from machine import WDT, Pin
import asyncio
import ADES1830
import DS18B20
import time
import network
import espnow
import json

FW_VERSION = "1.0.0.0"
HW_VERSION = "1.0.0.0"
USR_LED = 14
ERR_LED = 4
TEMP_OWM_PIN = 9
MAX_NCELL = 16

print("main started")

# Main execution
# Initialize ADES1830
ades = ADES1830.ADES1830()
ds18 = DS18B20.DS18B20(data_pin=9, pullup=False)
#startup sequence:
# 1. wakeup
# 2. softreset and wait for 50ms
# 3. wakeup
# 4. clear communication counter
# 5. Set REFON bit in CFGA (must be set before checking reset/cleared values)
# 6. Write config to Registers
#   a. CFGA.CTH[2:0] = 0b010 S-ADC comparison threshold to 9mv
#   b. CFGA.REFON = 1
#   c. CFGA.FC[2:0] = 0b101 set IIR filter to 32
#   d. CFGA rest is default as in datasheet
#   e. CFGB.VUV = 0
#   f. CFGB.VOV = 0
#   g. CFGB rest is default as in datasheet
# 7. Wait for T_REFUP = 5ms
# 8. Disable Balancing --> set all PWM to 0
# 9. Reset IIR filter change CFGA.FC[2:0] = 0b001 set IIR filter to 2
# 10. Clear flags in RDSTATC

# 11. Start continious cell measurement
# 12. Enable Balancing --> set all PWMs to x
# 13. Read device ID
# 14. Read cell voltage data.
# ...

# Instantiate registers
while False:
    temp_sens = ds18.get_roms()
    print(temp_sens)
    print(f"NR of Temp sensors = {len(temp_sens)}")
    temps=ds18.get_temperatures()
    print(f"Temperatures: {temps}")
    ades.hal.wakeup()
    ades.set_ref_power_up(1)
    time.sleep_ms(5)
    uv = ades.get_cell_undervoltage()
    print(f"Undervoltage: {uv:.4f}")
    ades.set_cell_undervoltage(2.5)
    time.sleep_ms(1)
    uv = ades.get_cell_undervoltage()
    print(f"Undervoltage: {uv:.4f}")

    pwm = ades.get_pwm()
    print(f"PWM: {list(pwm)}")

    #pwm = ades.set_pwm([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,0])
    #print(f"PWM: {list(pwm)}")

    #cell_pwm = ades.set_pwm_cell(10, 4)
    #print(f"PWM cell 4: {cell_pwm}")

    pwm = ades.get_pwm()
    print(f"PWM: {list(pwm)}")

    ades.set_ref_power_up(1)
    ades.start_cell_volt_conv(redundant=False, continuous=True, discharge_permitted=False, reset_filter=False, openwire=0)
    #ades.start_s_adc_conv(continuous=True, discharge_permitted=False, openwire=0)
    #ades.start_aux_adc_conv(openwire=False, pullup=False)
    #ades.start_aux2_adc_conv()
    time.sleep_ms(1)
    for i in range(2):
        cell = ades.get_all_cell_voltages()
        cell3 = ades.get_cell_voltage(cell=3)
    #    internal_temp = ades.get_internal_temp()
    #    device_id = ades.get_device_id()
    #    reference_voltage2 = ades.get_reference_voltage2()
    #    digital_supply_voltage = ades.get_digital_supply_voltage()
        print(f"Cell Voltages: {cell[0]:.4f} V, {cell[1]:.4f} V, {cell[2]:.4f} V")
    #    print(f"Internal Temp: {internal_temp:.2f} °C")
    #    print(f"Device ID: {device_id:04x}")
    #    print(f"Reference Voltage 2: {reference_voltage2:.4f} V")
    #    print(f"Digital Supply Voltage: {digital_supply_voltage:.4f} V")
        asyncio.sleep_ms(1)

        
    time.sleep(5)

#################################################################
#  Watchdog
#################################################################
class Watchdog:
   def __init__(self, timeout=5000):
      self.wdt = WDT(timeout=timeout)
      self.task = None
   
   async def _feed_task(self):
      while True:
         self.wdt.feed()
         await asyncio.sleep(2)
   
   def start(self):
      if self.task is None:
         self.task = asyncio.create_task(self._feed_task())
         return self.task
   
   def stop(self):
      if self.task is not None:
         self.task.cancel()
         self.task = None
#################################################################
#  Monitor Handler
#################################################################
class bms_monitor_handler():
    def __init__(self):
        self.cell_task = None
        self.aux_task = None
        self.temp_task = None
        self.state_task = None
        self.bal_task = None
        self.temp = {}
        self.vstr   = 0.0
        self.vcell  = []
        self.state = 0
        self.ncell = 0
        self.ntemp = 0
        self.id = 0

        self.cfg_cell_uv = 2.5
        self.cfg_cell_ov = 3.6
        self.cfg_str_uv = 25.0
        self.cfg_str_ov = 25.0
        self.cfg_bal_pwm = 0
        self.cfg_bal_en = False
        self.cfg_ext_bal_en = False
        self.cfg_bal_th = 0.2
        self.cfg_bal_start_vol = 3.4

        self.sta_string_ov_uv = 0
        self.sta_cell_ov_uv = 0
        self.sta_cell_ov = []
        self.sta_cell_uv = []
        self.sta_bal_pwm = []

        self.ades = None
        self.ds18 = None

    def configure(self, cell_uv: float, 
                  cell_ov: float, 
                  str_uv: float, 
                  str_ov: float, 
                  bal_pwm: int, 
                  bal_th: float, 
                  bal_start_voltage: float, 
                  bal_en: bool, ext_bal_en: bool):
        #TODO: implement checks
        self.cfg_cell_uv        = cell_uv
        self.cfg_cell_ov        = cell_ov
        self.cfg_str_uv         = str_uv
        self.cfg_str_ov         = str_ov
        self.cfg_bal_en         = bal_en
        self.cfg_ext_bal_en     = ext_bal_en
        self.cfg_bal_th         = bal_th
        self.cfg_bal_start_vol  = bal_start_voltage
        self.cfg_bal_pwm        = bal_pwm

    def initialize(self):
        try:
            # Init and get nr of temp sens
            self.ds18 = DS18B20.DS18B20(data_pin=TEMP_OWM_PIN, pullup=False)
            self.ntemp = len(ds18.get_roms())
        except Exception as err:
            print(f"Init DS18B20 error: {err}")
        try:
            #Init, and get number of detected cells
            self.ades = ADES1830.ADES1830()
            self.ncell = self.ades.init()
            # Get device ID   
            self.id = self.ades.get_device_id()
            self.ades.set_cell_undervoltage(self.cfg_cell_uv)
            self.ades.set_cell_overvoltage(self.cfg_cell_ov)
        except Exception as err:
            print(f"Init ADES1830 error: {err}")

    # Monitors cell voltages
    async def __mon_cell_task(self):
      self.ades.start_cell_volt_conv(redundant=False, continuous=True, discharge_permitted=False, reset_filter=False, openwire=0)
      #ades.start_s_adc_conv(continuous=True, discharge_permitted=False, openwire=0)
      while True:
         try:
            # Read sensors
            self.vcell = self.ades.get_all_cell_voltages(mode="average")
            # Validate sensor data (basic checks)
            if self.vcell is None:
               pass
            #error_handler.set_error(error_code.ERROR_ADES)

         except Exception as err:
            print(f"Cell read error: {err}")
         # 4. wait before next reading
         await asyncio.sleep_ms(8) # Average updates every 8ms

   # Monitor Auxilary measurements
    async def __mon_aux_task(self):
        while True:
            try: 
                self.ades.start_aux_adc_conv(openwire=False, pullup=False)
                #ades.start_aux2_adc_conv()
                await asyncio.sleep_ms(1) #taux = 1ms conversion time
                self.vstr = self.ades.get_string_voltage()
            except Exception as err:
                print(f"Aux read error: {err}")
            await asyncio.sleep(1) 

    async def __mon_temp_task(self):
        while True:
            try: 
                self.temp = self.ds18.get_temperatures()
            except Exception as err:
                print(f"Temperature read error: {err}")
            await asyncio.sleep(2) 
    # Monitors Errors, Warnings,Cell/String Undervoltage, Cell/String Overvoltage etc.
    async def __mon_state_task(self):
        while True:
            try: 
                self.sta_cell_ov, self.sta_cell_uv = self.ades.get_ov_uv_flag()
                if all(x == 0 for x in self.sta_cell_ov) and all(x == 0 for x in self.sta_cell_ov):
                    self.sta_cell_ov_uv = 0
                else:
                    self.sta_cell_ov_uv = 1
                if self.vstr > self.cfg_str_ov or self.vstr < self.cfg_str_uv:
                    self.sta_string_ov_uv = 1
                else: 
                    self.sta_string_ov_uv = 0
            except Exception as err:
                print(f"State read error: {err}")
            await asyncio.sleep_ms(100) 

    async def __bal_task(self):
        while True:
            bal_pwm = [0] * MAX_NCELL
            if self.cfg_bal_en == 1:
                for i, cell in enumerate(self.vcell):
                    if cell > self.cfg_bal_start_vol and i < self.ncell:
                        bal_pwm[i] = self.cfg_bal_pwm
                    else:
                        bal_pwm[i] = 0

                if (max(self.vcell) - min(self.vcell)) >= self.cfg_bal_th and (max(self.vcell) > self.cfg_cell_uv):
                    max_index = self.vcell.index(max(self.vcell))   
                    self.bal_pwm[max_index] = self.cfg_bal_pwm

            else:
                bal_pwm= [0] * MAX_NCELL

            if bal_pwm != self.sta_bal_pwm :
                try:
                    pwm = self.ades.set_pwm(bal_pwm)
                    assert pwm != bal_pwm 
                except Exception as err:
                    print(f"Set PWM ADES1830 error: {err}")

            self.sta_bal_pwm = bal_pwm

            # TODO implement external balancing
            if self.cfg_ext_bal_en == 1:
                pass

            await asyncio.sleep_ms(10) 

    def start(self):
        if self.cell_task is None:
            self.cell_task = asyncio.create_task(self.__mon_cell_task())
        if self.aux_task is None:
            self.aux_task = asyncio.create_task(self.__mon_aux_task())
        if self.temp_task is None:
            self.temp_task = asyncio.create_task(self.__mon_temp_task())      
        if self.state_task is None:
            self.state_task = asyncio.create_task(self.__mon_state_task())         
        if self.bal_task is None:
            self.bal_task = asyncio.create_task(self.__bal_task())   
    def stop(self):
        if self.cell_task is not None:
            self.cell_task.cancel()
            self.cell_task = None
        if self.aux_task is not None:
            self.aux_task.cancel()
            self.aux_task = None
        if self.temp_task is not None:
            self.temp_task.cancel()
            self.temp_task = None
        if self.state_task is not None:
            self.state_task.cancel()
            self.state_task = None
        if self.bal_task is not None:
            self.bal_task.cancel()
            self.bal_task = None            
    def get_data(self):
        return self.__to_dict_data()
    def __to_dict_data(self):
        return {
            "type": "mon",
            "temp": self.temp,
            "vstr": self.vstr,
            "vcell": self.vcell,
            "state": self.state
        }
    def get_info(self):
        return self.__to_dict_info()
    def __to_dict_info(self):
        return {
            "type": "inf",
            "id": self.id,
            "fw_ver": FW_VERSION,
            "hw_ver": HW_VERSION,
            "ncell": self.ncell,
            "ntemp": self.ntemp
        }
    def get_status(self):
        return self.__to_dict_status()
    def __to_dict_status(self):
        return {
            "type": "sta",
            "str_ov_uv_flag": self.sta_string_ov_uv,
            "cell_ov": self.sta_cell_ov,
            "cell_uv": self.sta_cell_ov
        }
    def get_config(self):
        return self.__to_dict_config()
    def __to_dict_config(self):
        return {
            "type": "cfg",
            "cell_uv": self.cfg_cell_uv,
            "cell_ov": self.cfg_cell_ov,
            "str_uv": self.cfg_str_uv,
            "str_ov": self.cfg_str_ov,
            "bal_start_vol": self.cfg_bal_start_vol,
            "bal_th": self.cfg_bal_th,
            "bal_en": self.cfg_bal_en,
            "ext_bal_en": self.cfg_ext_bal_en,
            "bal_pwm" : self.cfg_bal_pwm
        }
    def set_config(self, config):
        self.__from_dict_config(config)
        return self.__to_dict_config()
    def __from_dict_config(self, config_dict):
        self.cfg_cell_uv                    = config_dict.get("cell_uv", self.cfg_cell_uv)
        self.cfg_cell_ov                    = config_dict.get("cell_ov", self.cfg_cell_ov)
        self.cfg_str_uv                     = config_dict.get("str_uv",self.cfg_str_uv)
        self.cfg_str_ov                     = config_dict.get("str_ov",self.cfg_str_ov)
        self.cfg_bal_start_vol              = config_dict.get("bal_start_vol", self.cfg_bal_start_vol)
        self.cfg_bal_th                     = config_dict.get("bal_th", self.cfg_bal_th)
        self.cfg_bal_en                     = config_dict.get("bal_en", self.cfg_bal_en)
        self.cfg_ext_bal_en                 = config_dict.get("ext_bal_en", self.cfg_ext_bal_en)
        self.cfg_bal_pwm                    = config_dict.get("bal_pwm" , self.cfg_bal_pwm)

#################################################################
#  BMS command handler
#################################################################
class bms_command_handler:
    def __init__(self, monitor: bms_monitor_handler):
        # Dictionary to map command strings to methods
        self.command_map = {
            "led_on"             : self.turn_on_led,
            "led_off"            : self.turn_off_led,
            "start_mon"          : self.start_monitoring,
            "stop_mon"           : self.stop_monitoring,
            "get_info"           : self.get_info,
            "get_status"         : self.get_status,
            "get_data"           : self.get_data,
            "get_config"         : self.get_config,
            "reboot"             : self.reboot,
            "soft_reset"         : self.soft_reset,
            "update_fw"          : self.update_fw
            # Add more commands as needed
        }
        self.e = None
        self.listen_to_master_task = None
        self.master = None
        self.monitor = monitor

    def start(self):
        if self.listen_to_master_task is None:
            self.listen_to_master_task = asyncio.create_task(self.__listen_to_master_task())
        return self.listen_to_master_task
    
    def stop(self):
        if self.listen_to_master_task is not None:
            self.listen_to_master_task.cancel()
            self.listen_to_master_task = None

    async def connect(self):
        # A WLAN interface must be active to send()/recv()
        try: 
            sta = network.WLAN(network.WLAN.STA_IF)
            sta.active(True)
            sta.disconnect()   # Because ESP8266 auto-connects to last Access Point
            # initialize espnow
            self.e = espnow.ESPNow()
            self.e.active(True)
        except Exception as err:
            print(f"Init ESPnow error: {err}")       

        # 4. discover master
        print("Discovering master...")
        while True:
            self.master, msg = self.e.recv(timeout_ms=10) 
            if msg == b'I AM YOUR MASTER':
                print("Discovered master:", self.master)
                self.e.add_peer(self.master)
                json_str = json.dumps(self.monitor.get_info())
                data_bytes = json_str.encode('utf-8')  
                self.e.send(self.master, data_bytes)
                break
            else:
                await asyncio.sleep(5)

    async def __listen_to_master_task(self):
        while True:
        # listen to master for commands and settings
            if self.e.any():
                peer, msg = self.e.recv(timeout_ms=100) 
            if peer == self.master:
                # 2. deserialize JSON to dict
                dict = json.loads(msg)
                # 3. executer settins handler or command handler
                if dict.get("type") == "cfg":
                    response = self.monitor.set_config(dict)
                    self.monitor.stop()
                    self.monitor.initialize()
                    self.monitor.start()
                elif dict.get("type") == "cmd":
                    response = self.execute_command(dict.get("command"))
                else:
                    print("Unknown data reveived")
                # 3. serialize response to JSON
                json_str = json.dumps(response)
                # 4. encode JSON to bytes
                data_bytes = json_str.encode('utf-8')
                # 5. send data_bytes to master using ESPNow
                self.e.send(self.master, data_bytes)
            else:
                await asyncio.sleep_ms(10)       

    def turn_on_led(self):
       print("LED turned ON")
       status.set_led(1)
       return status.get_status()
 
    def turn_off_led(self):
       print("LED turned OFF")
       status.set_led(0)
       return status.get_status()
    
    def start_monitoring(self):
       monitor.start()
       return status.get_status()
 
    def stop_monitoring(self):
       monitor.stop()
       return status.get_status()
 
    def get_data(self):
       return self.monitor.get_data()
    
    def get_info(self):
       return self.monitor.get_info()
    
    def get_status(self):
       return self.monitor.get_status()
 
    def get_config(self):
       return self.monitor.get_config()
    
    def reboot():
       machine.reboot()
       return False # doesn't matter anyway
    
    def soft_reset(self):
       machine.soft_reset()
       return False # doesn't matter anyway
       
    def update_fw(self):
       #error(error_code.ERROR_COMM, f"Update fw command not implemented yet!")
       return False
 
    def execute_command(self, command_str):
        # Look up the command in the dictionary
        method = self.command_map.get(command_str)
        if method:
            print("Executing command: ", command_str)
            return method()  # Call the method
        else:
            raise Exception("Command not found")
#################################################################
#  Main
#################################################################    
async def main():
    watchdog = Watchdog()
    wd_task = watchdog.start()

    monitor = bms_monitor_handler()
    monitor.configure()
    monitor.initialize()
    monitor.start()
    await asyncio.sleep(1)

    commands = bms_command_handler(monitor)
    await commands.connect()
    cmd_task = commands.start()
    while True:
        await asyncio.sleep(5)




    

if __name__ == '__main__':
    try: 
        asyncio.run(main())
    except Exception as err:
        print("running main failed.")