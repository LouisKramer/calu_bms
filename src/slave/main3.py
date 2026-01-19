from machine import WDT, Pin
import asyncio
import ADES1830
import DS18B20
import time
import network
import espnow
import json
import sys
from collections import deque
import requests

HA_URL = 'http://192.168.1.90:8123'  # Home Assistant IP and port
API_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI4NDZjNWFkNmJiNjc0MWY1ODU3NGM0MWJmYTFmNjEzNCIsImlhdCI6MTc2MDg3MDQ1MSwiZXhwIjoyMDc2MjMwNDUxfQ.4IwK58gY4JIm-PCbIRpyZDwZWMDSjxca0_8Z9Yg-iPs'  # From Home Assistant
ENTITY_ID = 'sensor.micropython_temperature'


FW_VERSION = "1.0.0.0"
HW_VERSION = "1.0.0.0"
USR_LED = 14
ERR_LED = 4
TEMP_OWM_PIN = 9
MAX_NCELL = 16
#################################################################
#  Error Handler
#################################################################
class error_handler():
    ERROR_LEVELS = {
        'warning': 1,  # Slow blink
        'error': 2,    # Fast blink
        'critical': 3  # Solid on
    }
    def __init__(self, led_pin=ERR_LED, debug=True):
        # Setup LED
        self.led = machine.Pin(led_pin, machine.Pin.OUT)
        self.led.on()#led is inverted
        #sys.excepthook = self.excepthook
        self.blink_task = None
        self.debug = debug
        self.has_error = False
        self.err_lvl = 0
        self.err_msg = ""
        self.err_ts = time.time()

    async def __blink_led(self, level):
        """Blink LED based on error level for specified duration (seconds)."""
        if level == self.ERROR_LEVELS['warning']:
            interval = 2.0  # Slow
        elif level == self.ERROR_LEVELS['error']:
            interval = 1.0  # Fast
        while True:
            self.led.on()
            asyncio.sleep(interval)
            self.led.off()
            asyncio.sleep(interval)

    def handle_error(self, level, message):
        self.has_error = True
        self.err_msg = message
        self.err_lvl = level
        print(f"Error: {message}")
        if self.debug:
            print(f"[{level.upper()}] {message}")
                # Indicate via LED
        if level != 'error':
            if self.blink_task is None:
                self.blink_task = asyncio.create_task(self.__blink_led(self.ERROR_LEVELS[level]))
        else:
            self.led.off()#led is inverted
        

    def get_error(self):
        return self.__to_dict_error()
    
    def __to_dict_error(self):
        return {
            "type":     "err",
            "level":    self.err_lvl,
            "msg":      self.err_msg,
            "ts":       self.err_ts
        }    


#################################################################
#  Watchdog
#################################################################
class Watchdog:
   def __init__(self, timeout=50000):
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
    def __init__(self, error: error_handler):
        self.cell_task = None
        self.aux_task = None
        self.temp_task = None
        self.state_task = None
        self.bal_task = None
        self.request_restart = False

        self.mon_temp = {}
        self.mon_vstr   = 0.0
        self.mon_vcell  = []
        self.mon_state = 0

        self.inf_ncell = 0
        self.inf_ntemp = 0
        self.inf_id = 0
        self.inf_block_pos = 0

        self.cfg_cell_uv = 0.8
        self.cfg_cell_ov = 3.6
        self.cfg_str_uv = 15.0
        self.cfg_str_ov = 20.0
        self.cfg_bal_pwm = 15
        self.cfg_bal_en = True
        self.cfg_ext_bal_en = False
        self.cfg_bal_th = 0.2
        self.cfg_bal_start_vol = 1

        self.sta = "off"
        self.sta_string_ov_uv = 0
        self.sta_cell_ov_uv = 0
        self.sta_cell_ov = []
        self.sta_cell_uv = []
        self.sta_bal_pwm = []
        self.sta_conv_cnt = []

        self.ades = None
        self.ds18 = None
        self.err = error
        print(self.get_config())

    def configure(self, cell_uv: float = None, 
                    cell_ov: float = None, 
                    str_uv: float = None, 
                    str_ov: float = None, 
                    bal_pwm: float = None, 
                    bal_th: float = None, 
                    bal_start_voltage: float = None, 
                    bal_en: bool = None, 
                    ext_bal_en: bool = None):
        # Check types for provided parameters
        float_params = [cell_uv, cell_ov, str_uv, str_ov, bal_th, bal_pwm, bal_start_voltage]
        if any(x is not None and not isinstance(x, float) for x in float_params):
            raise TypeError("Voltage and threshold parameters must be floats")
        bool_params = [bal_en, ext_bal_en]
        if any(x is not None and not isinstance(x, bool) for x in bool_params):
            raise TypeError("Enable parameters must be booleans")

        # Check voltage ranges (assuming typical Li-ion battery parameters)
        if cell_uv is not None:
            if not (2.5 <= cell_uv <= 3.6):
                raise ValueError("Cell undervoltage must be between 2.5V and 3.6V")
            self.cfg_cell_uv = cell_uv

        if cell_ov is not None:
            if not (3.6 <= cell_ov <= 4.3):
                raise ValueError("Cell overvoltage must be between 4.0V and 4.3V")
            self.cfg_cell_ov = cell_ov

        # Ensure cell_uv < cell_ov if both are provided or one is provided and the other is already set
        if (cell_uv is not None and cell_ov is not None and not (cell_uv < cell_ov)) or \
           (cell_uv is not None and hasattr(self, 'cfg_cell_ov') and not (cell_uv < self.cfg_cell_ov)) or \
           (cell_ov is not None and hasattr(self, 'cfg_cell_uv') and not (self.cfg_cell_uv < cell_ov)):
            raise ValueError("Cell overvoltage must be greater than undervoltage")

        # Check string voltage ranges (assuming series configuration of up to 16 cells)
        if str_uv is not None:
            ref_cell_uv = cell_uv if cell_uv is not None else self.cfg_cell_uv
            ref_cell_ov = cell_ov if cell_ov is not None else self.cfg_cell_ov
            if not (ref_cell_uv * 16 <= str_uv <= ref_cell_ov * 16):
                raise ValueError("String undervoltage must be within cell voltage range for 16 cells")
            self.cfg_str_uv = str_uv

        if str_ov is not None:
            ref_cell_ov = cell_ov if cell_ov is not None else self.cfg_cell_ov
            if not (ref_cell_ov * 16 <= str_ov <= ref_cell_ov * 16 + 1.0):
                raise ValueError("String overvoltage must be within reasonable range")
            self.cfg_str_ov = str_ov

        # Ensure str_uv < str_ov if both are provided or one is provided and the other is already set
        if (str_uv is not None and str_ov is not None and not (str_uv < str_ov)) or \
           (str_uv is not None and hasattr(self, 'cfg_str_ov') and not (str_uv < self.cfg_str_ov)) or \
           (str_ov is not None and hasattr(self, 'cfg_str_uv') and not (self.cfg_str_uv < str_ov)):
            raise ValueError("String overvoltage must be greater than undervoltage")

        # Check balance PWM (0-100% for PWM)
        if bal_pwm is not None:
            if not (0 <= bal_pwm <= 100):
                raise ValueError("Balance PWM must be between 0 and 100")
            self.cfg_bal_pwm = self.__pwm_percentage_to_hex(bal_pwm)

        # Check balance threshold and start voltage
        if bal_th is not None:
            if not (0.001 <= bal_th <= 2.0):
                raise ValueError("Balance threshold must be between 0.001V and 2.0V")
            self.cfg_bal_th = bal_th

        if bal_start_voltage is not None:
            if not (3.0 <= bal_start_voltage <= 4.2):
                raise ValueError("Balance start voltage must be between 3.0V and 4.2V")
            self.cfg_bal_start_vol = bal_start_voltage

        # Update boolean parameters if provided
        if bal_en is not None:
            self.cfg_bal_en = bal_en
        if ext_bal_en is not None:
            self.cfg_ext_bal_en = ext_bal_en
    def write_config(self):
        pass
    def initialize(self):
        self.sta = "init"
        self.request_restart = False
        # Init and get nr of temp sens
        self.ds18 = DS18B20.DS18B20(data_pin=TEMP_OWM_PIN, pullup=False)
        self.inf_ntemp = len(self.ds18.get_roms())
        #Init, and get number of detected cells
        self.ades = ADES1830.ADES1830()
        self.inf_ncell = self.ades.init(self.cfg_cell_ov, self.cfg_cell_uv)
        # Get device ID   
        self.inf_id = self.ades.get_device_id()
        self.inf_block_pos = 0 #TODO: Read in block position from DIP switches

    # Monitors cell voltages
    async def __mon_cell_task(self):
        print("Run cell monitoring task")
        self.ades.start_cell_volt_conv(redundant=False, continuous=True, discharge_permitted=False, reset_filter=False, openwire=0)
        #ades.start_s_adc_conv(continuous=True, discharge_permitted=False, openwire=0)
        while True:
            # Read sensors
            self.mon_vcell = self.ades.get_all_cell_voltages(mode="average")
            # wait before next reading
            await asyncio.sleep(1) # Average updates every 8ms

   # Monitor Auxilary measurements
    async def __mon_aux_task(self):
        print("Run aux monitoring task")
        while True:
            self.ades.start_aux_adc_conv(openwire=False, pullup=False)
            #ades.start_aux2_adc_conv()
            await asyncio.sleep_ms(1) #taux = 1ms conversion time
            self.mon_vstr = self.ades.get_string_voltage()
            await asyncio.sleep(1) 

    async def __mon_temp_task(self):
        print("Run temperature monitoring task")
        while True:
            self.mon_temp = self.ds18.get_temperatures()
            await asyncio.sleep(2) 

    # Monitors Errors, Warnings,Cell/String Undervoltage, Cell/String Overvoltage etc.
    async def __mon_state_task(self):
        print("Run ADES1830 state monitoring task")
        while True:
            # check conversion counter
            self.sta_conv_cnt.append(self.ades.get_conversion_counter())
            print(f"conversion counter {self.sta_conv_cnt}")
            if len(self.sta_conv_cnt) > 3:
                self.sta_conv_cnt.pop(0)
                if all(x == self.sta_conv_cnt[0] for x in self.sta_conv_cnt):
                    self.request_restart = True
                    self.err.handle_error('warning', f"Restart requested, reason: conversiont counter stalled")

            # check OV UV flags    
            self.sta_cell_ov, self.sta_cell_uv = self.ades.get_ov_uv_flag()
            if all(x == 0 for x in self.sta_cell_ov) and all(x == 0 for x in self.sta_cell_ov):
                self.sta_cell_ov_uv = 0
            else:
                self.sta_cell_ov_uv = 1
            if self.mon_vstr > self.cfg_str_ov or self.mon_vstr < self.cfg_str_uv:
                self.sta_string_ov_uv = 1
            else: 
                self.sta_string_ov_uv = 0
            await asyncio.sleep(3) 

    async def __bal_task(self):
        print("Run cell balancing task")
        while True:
            bal_pwm = [0] * MAX_NCELL
            if self.cfg_bal_en == 1:
                for i, cell in enumerate(self.mon_vcell):
                    if cell > self.cfg_bal_start_vol:
                        bal_pwm[i] = self.cfg_bal_pwm
                    else:
                        bal_pwm[i] = 0

                #if (max(self.mon_vcell) - min(self.mon_vcell)) >= self.cfg_bal_th and (max(self.mon_vcell) > self.cfg_cell_uv):
                #    max_index = self.mon_vcell.index(max(self.mon_vcell))   
                #    bal_pwm[max_index] = self.cfg_bal_pwm

            else:
                bal_pwm= [0] * MAX_NCELL

            if bal_pwm != self.sta_bal_pwm :
                try:
                    print(f"Change balancing pwm to: {bal_pwm}")
                    pwm = self.ades.set_pwm(bal_pwm)
                    assert pwm == bal_pwm 
                except Exception as err:
                    self.err.handle_error('error', f"Set PWM ADES1830 error: {err}")

            self.sta_bal_pwm = bal_pwm

            # TODO implement external balancing
            if self.cfg_ext_bal_en == 1:
                pass

            await asyncio.sleep(10) 

    def start(self):
        print("Start monitoring")
        self.sta = "monitoring"
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
        print("Stop monitoring")
        self.sta = "off"
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
            "temp": self.mon_temp,
            "vstr": self.mon_vstr,
            "vcell": self.mon_vcell,
            "state": self.mon_state
        }
    def get_info(self):
        return self.__to_dict_info()
    def __to_dict_info(self):
        return {
            "type": "inf",
            "id": self.inf_id,
            "fw_ver": FW_VERSION,
            "hw_ver": HW_VERSION,
            "ncell": self.inf_ncell,
            "ntemp": self.inf_ntemp
        }
    def get_status(self):
        return self.__to_dict_status()
    def __to_dict_status(self):
        return {
            "type": "sta",
            "state": self.sta,
            "str_ov_uv_flag": self.sta_string_ov_uv,
            "cell_ov": self.sta_cell_ov,
            "cell_uv": self.sta_cell_uv
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
        cfg_cell_uv                    = config_dict.get("cell_uv", self.cfg_cell_uv)
        cfg_cell_ov                    = config_dict.get("cell_ov", self.cfg_cell_ov)
        cfg_str_uv                     = config_dict.get("str_uv",self.cfg_str_uv)
        cfg_str_ov                     = config_dict.get("str_ov",self.cfg_str_ov)
        cfg_bal_start_vol              = config_dict.get("bal_start_vol", self.cfg_bal_start_vol)
        cfg_bal_th                     = config_dict.get("bal_th", self.cfg_bal_th)
        cfg_bal_en                     = config_dict.get("bal_en", self.cfg_bal_en)
        cfg_ext_bal_en                 = config_dict.get("ext_bal_en", self.cfg_ext_bal_en)
        cfg_bal_pwm                    = config_dict.get("bal_pwm" , self.cfg_bal_pwm)
        self.configure(cell_uv          = cfg_cell_uv,
                       cell_ov          = cfg_cell_ov,
                       str_uv           = cfg_str_uv, 
                       str_ov           = cfg_str_ov, 
                       bal_pwm          = cfg_bal_pwm,
                       bal_th           = cfg_bal_th,
                       bal_start_voltage= cfg_bal_start_vol,
                       bal_en           = cfg_bal_en,
                       ext_bal_en       = cfg_ext_bal_en)      
        
    def __pwm_percentage_to_hex(pwm_percentage: float) -> int:
        if not isinstance(pwm_percentage, (int, float)):
            raise ValueError("PWM percentage must be a number")
        if not 0.0 <= pwm_percentage <= 100.0:
            raise ValueError("PWM percentage must be between 0.0 and 100.0")
    
        # Linearly map 0-100% to 0-15
        hex_value = round(pwm_percentage / 100.0 * 15)
        return hex_value
#################################################################
#  BMS command handler
#################################################################
class bms_command_handler:
    def __init__(self, monitor: bms_monitor_handler, error: error_handler):
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
        self.error = error

        self.led_usr = machine.Pin(USR_LED, machine.Pin.OUT)
        self.led_usr.off()

    def start(self, sim = False):
        if self.listen_to_master_task is None and sim == False:
            self.listen_to_master_task = asyncio.create_task(self.__listen_to_master_task())
        elif self.listen_to_master_task is None and sim == True:
            self.listen_to_master_task = asyncio.create_task(self.__sim_master_task())
        return self.listen_to_master_task
    
    def stop(self):
        if self.listen_to_master_task is not None:
            self.listen_to_master_task.cancel()
            self.listen_to_master_task = None

    async def connect(self, sim = False):
        # A WLAN interface must be active to send()/recv()
        if sim == True:
            return
        try: 
            sta = network.WLAN(network.WLAN.STA_IF)
            sta.active(True)
            sta.disconnect()   # Because ESP8266 auto-connects to last Access Point
            # initialize espnow
            self.e = espnow.ESPNow()
            self.e.active(True)
        except Exception as err:
            self.error.handle_error('error', f"Init ESPnow error: {err}")
 

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
            data = self.espnow.irecv()
            if data:
                peer, msg = data
                if peer == self.master:
                    # 2. deserialize JSON to dict
                    dict = json.loads(msg)
                    # 3. executer settins handler or command handler
                    if dict.get("type") == "cfg":
                        self.monitor.set_config(dict)
                        self.monitor.stop()
                        asyncio.sleep(1)
                        self.monitor.initialize()
                        self.monitor.start()
                        response = self.monitor.get_info()
                    elif dict.get("type") == "cmd":
                        response = self.execute_command(dict.get("command"))
                    else:
                        print("Unknown data reveived")
                    if self.error.has_error:
                        response = self.error.get_error()
                    # 3. serialize response to JSON
                    json_str = json.dumps(response)
                    # 4. encode JSON to bytes
                    data_bytes = json_str.encode('utf-8')
                    # 5. send data_bytes to master using ESPNow
                    self.e.send(self.master, data_bytes)
            else:
                await asyncio.sleep_ms(10)       

    async def __sim_master_task(self):
        while True:
            self.turn_on_led()
            await asyncio.sleep(1)    
            self.turn_off_led()
            await asyncio.sleep(1) 
            print(self.get_data())
            await asyncio.sleep(3)
            print(self.get_info())
            await asyncio.sleep(3)  
            print(self.get_status())
            await asyncio.sleep(3)  
            self.monitor.ades.clear_ov_uv(ov_uv = "all")
            #data = self.get_data()
            #temperature = data.get("temp")
            #headers = {
            #    'Authorization': 'Bearer ' + API_TOKEN,
            #    'Content-Type': 'application/json'
            #    }
            ## Prepare payload
            #payload = json.dumps({
            #    'state': temperature,
            #    'attributes': {
            #    'unit_of_measurement': '°C',
            #    'friendly_name': 'MicroPython Temperature'
            #    }
            #})   
            ## Send POST request
            #try:
            #    response = requests.post(
            #        f'{HA_URL}/api/states/{ENTITY_ID}',
            #        data=payload,
            #        headers=headers
            #    )
            #    print('Response:', response.text)
            #    response.close()
            #except Exception as e:
            #    print('Error:', e) 

    def turn_on_led(self):
       print("LED turned ON")
       self.led_usr.off()#led is inverted
       return self.monitor.get_status()
 
    def turn_off_led(self):
       print("LED turned OFF")
       self.led_usr.on()#led is inverted
       return self.monitor.get_status()
    
    def start_monitoring(self):
       self.monitor.start()
       return self.monitor.get_status()
 
    def stop_monitoring(self):
       self.monitor.stop()
       return self.monitor.get_status()
 
    def get_data(self):
       return self.monitor.get_data()
    
    def get_info(self):
       return self.monitor.get_info()
    
    def get_status(self):
       return self.monitor.get_status()
 
    def get_config(self):
       return self.monitor.get_config()
    
    def reboot(self):
       machine.reboot()
       return self.monitor.get_status() # doesn't matter anyway
    
    def soft_reset(self):
       machine.soft_reset()
       return self.monitor.get_status() # doesn't matter anyway
       
    def update_fw(self):
       #error(error_code.ERROR_COMM, f"Update fw command not implemented yet!")
       return self.monitor.get_status()
 
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
    print("Init BMS...")
    try: 
        error = error_handler(ERR_LED, True)
        watchdog = Watchdog()
        wd_task = watchdog.start()
    except Exception as err:
        print(err)

    monitor = bms_monitor_handler(error = error)
    try :
        monitor.initialize()
        monitor.start()
    except Exception as err:
        error.handle_error('error', err)

    await asyncio.sleep(1)

    commands = bms_command_handler(monitor = monitor,error = error)
    await commands.connect(sim=True)
    cmd_task = commands.start(sim=True)
    while True:
        if monitor.request_restart == True:
            monitor.stop()
            await asyncio.sleep(1)
            monitor.initialize()
            monitor.start()

        await asyncio.sleep(5)


try: 
    asyncio.run(main())
except Exception as err:
    print("running main failed.")