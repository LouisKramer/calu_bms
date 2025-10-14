import ADES1830
import DS18B20
import asyncio
import network
import espnow
import json
from machine import WDT, Pin

FW_VERSION = "1.0.0.0"
HW_VERSION = "1.0.0.0"
USR_LED = 14
ERR_LED = 4
TEMP_OWM_PIN = 9
#################################################################
#  Error handler
#################################################################
class error_code:
   ERROR_NO = 0
   ERROR_ADES = 1
   ERROR_WLAN = 3
   ERROR_1WIRE = 4
   ERROR_OTHER = 5
   ERROR_COMM = 6
class error_handler():
   def __init__(self, led_pin=2):
        self.current_error = error_code.ERROR_NO  # Variable to hold error code
        self.led = Pin(led_pin, Pin.OUT)
        self.blink_task = None  # To manage the blinking loop
    
   async def blink_led(self):
      """Async task to blink LED continuously based on error code until resolved."""
      while self.current_error != error_code.ERROR_NO:
          code = self.current_error
          if code == error_code.ERROR_ADES:
              pattern = [0.5, 0.5] * 2  # Quick double blink
          elif code == error_code.ERROR_WLAN:
              pattern = [1, 1]      # Slow blink
          elif code == error_code.ERROR_1WIRE:
              pattern = [0.2, 0.1] * 3  # Triple fast blink
          elif code == error_code.ERROR_COMM:
              pattern = [1.0, 0.5]      # Long on, short off
          else:
              pattern = [0.1, 0.9]      # Default: Short blink
          
          for on_off in pattern:
              self.led.value(1 if on_off == pattern[0] else 0)  # Toggle based on pattern
              await asyncio.sleep(on_off)
          
          await asyncio.sleep(1)  # Pause between pattern repeats
      
      self.led.off()  # Turn off LED when error resolved
      self.blink_task = None

   def set_error(self, err_code, str = "error"):
      print(str)
      """Set the error code and start blinking/sending if needed."""
      if err_code == self.current_error:
         return  # No change
      self.current_error = err_code
      if err_code != error_code.ERROR_NO and self.blink_task is None:
         self.blink_task = asyncio.create_task(self.blink_led())
      status.set_err(self.current_error)

   def clear_error(self):
      """Resolve the error."""
      self.current_error = error_code.ERROR_NO
      status.err(self.current_error)
#################################################################
#  Watchdog
#################################################################
class Watchdog:
   def __init__(self, timeout=5000):
      self.wdt = WDT(timeout=timeout)
      self.task = None
      self.start()
   
   async def _feed_task(self):
      while True:
         self.wdt.feed()
         await asyncio.sleep(1)
   
   def start(self):
      if self.task is None:
         self.task = asyncio.create_task(self._feed_task())
         return self.task
   
   def stop(self):
      if self.task is not None:
         self.task.cancel()
         self.task = None
#################################################################
#  Config Handler
#################################################################
class bms_config:
   def __init__(self):
      self.uv = 2.5
      self.ov = 3.65
      self.bal_start_vol = 3.4
      self.bal_th = 0.02
      self.adc_conv_en = 1 #TODO: needed?
      self.bal_en = 1
      self.ext_bal_en = 1 
      self.bal_pwm = 0
    
   def to_dict(self):
         return {
            "type": "cfg",
            "uv": self.uv,
            "ov": self.ov,
            "bal_start_vol": self.bal_start_vol,
            "bal_th": self.bal_th,
            "adc_conv_en": self.adc_conv_en,
            "bal_en": self.bal_en,
            "ext_bal_en": self.ext_bal_en,
            "bal_pwm" : self.bal_pwm
         }

   def from_dict(self, config_dict):
      self.uv = config_dict.get("uv", self.uv)
      self.ov = config_dict.get("ov", self.ov)
      self.bal_start_vol = config_dict.get("bal_start_vol", self.bal_start_vol)
      self.bal_th = config_dict.get("bal_th", self.bal_th)
      self.adc_conv_en = config_dict.get("adc_conv_en", self.adc_conv_en)
      self.bal_en = config_dict.get("bal_en", self.bal_en)
      self.ext_bal_en = config_dict.get("ext_bal_en", self.ext_bal_en)
      self.bal_pwm = config_dict.get("bal_pwm", self.bal_pwm)
      return self 
class bms_config_handler(bms_config):
   def __init__(self):
      super().__init__()

   def set_config(self, new_settings):
      super().from_dict(new_settings)
      return super().to_dict()
   
   def get_config(self):
      return super().to_dict()
#################################################################
#  Command Handler
#################################################################
class bms_command_handler:
   def __init__(self):
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
      balancer.start()
      return status.get_status()

   def stop_monitoring(self):
      monitor.stop()
      balancer.stop()
      return status.get_status()

   def get_data(self):
      return monitor.get_data()
   
   def get_info(self):
      return info.get_info()
   
   def get_status(self):
      return status.get_status()

   def get_config(self):
      return config.get_config()
   
   def reboot():
      machine.reboot()
      return status.get_status() # doesn't matter anyway
   
   def soft_reset(self):
      machine.soft_reset()
      return status.get_status() # doesn't matter anyway
      
   def update_fw(self):
      error.set_error(error_code.ERROR_COMM, f"Update fw command not implemented yet!")
      return status.get_status()

   def execute_command(self, command_str):
        # Look up the command in the dictionary
      method = self.command_map.get(command_str)
      if method:
         print("Executing command: ", command_str)
         return method()  # Call the method
      else:
         error.set_error(error_code.ERROR_COMM, f"Unknown command: {command_str}")
         return status.get_status()
#################################################################
#  Info Handler
#################################################################
class bms_info:
   def __init__(self):
      self.id = 0
      self.fw_ver = FW_VERSION
      self.hw_ver = HW_VERSION
      self.ncell = 16
      self.ntemp = 4
    
   def to_dict(self):
         return {
            "type": "inf",
            "id": self.id,
            "fw_ver": self.fw_ver,
            "hw_ver": self.hw_ver,
            "ncell": self.ncell,
            "ntemp": self.ntemp
         }
class bms_info_handler(bms_info):
   def __init__(self):
      super().__init__()

   def get_info(self):
      return super().to_dict()
   
   def set_id(self, id):
      # Check if id is a 48-bit number (0 to 2^48-1)
      if not isinstance(id, int):
         raise TypeError("ID must be an integer")
      if id < 0 or id > 0xFFFFFFFFFFFF:  # 2^48 - 1
         raise ValueError("ID must be a 48-bit number (0 to 281474976710655)")
      self.id = id

   def set_ncells(self, ncell):
      # Check if ncells is between 3 and 16
      if not isinstance(ncell, int):
         raise TypeError("ncells must be an integer")
      if ncell < 3 or ncell > 16:
         error.set_error(error_code.ERROR_ADES, f"ncells must be between 3 and 16")
         #raise ValueError("ncells must be between 3 and 16")
      self.ncell = ncell

   def set_ntemp(self, ntemp):
      # Check if ntemp is between 0 and 4
      if not isinstance(ntemp, int):
         raise TypeError("ntemp must be an integer")
      if ntemp < 0 or ntemp > 4:
         raise ValueError("ntemp must be between 0 and 4")
      self.ntemp = ntemp
#################################################################
#  Status Handler
#################################################################
class bms_status:
   def __init__(self):
      self.state = "run"
      self.led   = 0
      self.err   = error_code.ERROR_NO
      self.ov_flag    = [0] * 16 #TODO magic number
      self.uv_flag    = [0] * 16 #TODO magic number

   def to_dict(self):
         return {
            "type": "state",
            "state": self.state,
            "led": self.led,
            "err": self.err,
            "ov_flag": self.ov_flag,
            "uv_flag": self.uv_flag
         }
class bms_status_handler(bms_status):
   def __init__(self, led_pin):
      super().__init__()
      self.led = Pin(led_pin, Pin.OUT)

   def get_status(self):
      return super().to_dict()
   
   def set_led(self, led):
      self.led.value(led)
      self.led = led

   def set_state(self, state):
      self.state = state

   def set_err(self, err):
      self.err = err
#################################################################
#  Monitor Handler
#################################################################
class bms_monitor:
   def __init__(self):
      self.temp = {}
      self.vstr   = 0.0
      self.vcell  = []
      self.state = 0

   def to_dict(self):
         return {
            "type": "mon",
            "temp": self.temp,
            "vstr": self.vstr,
            "vcell": self.vcell,
            "state": self.state
         }
class bms_monitor_handler(bms_monitor):
   def __init__(self):
      super().__init__()
      self.cell_task = None
      self.aux_task = None
      self.temp_task = None
      self.state_task = None
   
   async def _mon_cell_task(self):
      ades.hal.wakeup()
      ades.set_ref_power_up(1)
      ades.start_cell_volt_conv(redundant=False, continuous=True, discharge_permitted=False, reset_filter=False, openwire=0)
      #ades.start_s_adc_conv(continuous=True, discharge_permitted=False, openwire=0)
      while True:
         try:
            # 1. read sensors
            self.vcell = ades.get_all_cell_voltages(mode="average")
            status.set_state(ades.get_status())
            # 2. validate sensor data (basic checks)
            if self.vcell  is None or self.temp is None or self.vstr is None:
               error_handler.set_error(error_code.ERROR_ADES)
            else:
               # 3. update data_dict with new sensor values
               super().to_dict()

         except Exception as e:
            # Handle any errors during sensor reading
            error.set_error(error_code.ERROR_ADES)
            print(f"Cell read error: {e}")

         # 4. wait before next reading
         await asyncio.sleep_ms(8) # Average updates every 8ms
   
   async def _mon_aux_task(self):
      while True:
         try: 
            ades.start_aux_adc_conv(openwire=False, pullup=False)
            #ades.start_aux2_adc_conv()
            await asyncio.sleep_ms(1) #taux = 1ms conversion time
            self.vstr = ades.get_string_voltage()
         except: 
            error.set_error(error_code.ERROR_ADES)
            print(f"Aux read error: {e}")
         await asyncio.sleep(1) 

   async def _mon_temp_task(self):
      while True:
         try: 
            self.temp = ds18.get_temperatures()
         except: 
            error.set_error(error_code.ERROR_ADES)
            print(f"Temperature read error: {e}")
         await asyncio.sleep(5) 

   async def _mon_state_task(self):
      ades.set_cell_undervoltage(config.uv)
      ades.set_cell_overvoltage(config.ov)
      while True:
         try: 
            ades.get_ov_uv_flag()
            pass
         except: 
            error.set_error(error_code.ERROR_ADES)
            print(f"State read error: {e}")
         await asyncio.sleep_ms(10) 

   def start(self):
      if self.cell_task is None:
         self.cell_task = asyncio.create_task(self._mon_cell_task())
      if self.aux_task is None:
         self.aux_task = asyncio.create_task(self._mon_aux_task())
      if self.temp_task is None:
         self.temp_task = asyncio.create_task(self._mon_temp_task())      
      if self.state_task is None:
         self.state_task = asyncio.create_task(self._mon_state_task())         
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
   def get_data(self):
      return super().to_dict()
#################################################################
#  Balancer Handler
#################################################################
class bms_balancing_handler():
   def __init__(self):

      self.bal_task = None
      self.bal_pwm = [0] * 16 #TODO magic number
   
   async def _balancing_task(self):
      while True:
         if config.bal_en == 1:
            #ades.unmute_discharge()
            for i, cell in enumerate(monitor.vcell):
               if cell > config.bal_start_vol and i < info.ncell:
                  self.bal_pwm[i] = config.bal_pwm
               else:
                  self.bal_pwm[i] = 0
            # TODO: implement threshold balancing
            #config.bal_th = 0.02
         else:
            self.bal_pwm = [0] * len(self.bal_pwm)
            pass
         pwm = ades.set_pwm(self.bal_pwm)
         if pwm != self.bal_pwm :
            print("set_pwm failed")
            error.set_error(error_code.ERROR_ADES)

         # TODO implement external balancing
         if config.ext_bal_en == 1:
            pass
            #ades.mute_discharge()
         await asyncio.sleep_ms(10) 

   def start(self):
      if self.bal_task is None:
         self.bal_task = asyncio.create_task(self._balancing_task())
   
   def stop(self):
      if self.bal_task is not None:
         self.bal_task.cancel()
         self.bal_task = None      
#################################################################
#  MAIN
#################################################################

# A WLAN interface must be active to send()/recv()
sta = network.WLAN(network.WLAN.IF_STA)
sta.active(True)
sta.disconnect()   # Because ESP8266 auto-connects to last Access Point
# initialize espnow
e = espnow.ESPNow()
e.active(True)

master = None
watchdog = Watchdog(timeout=50000)
status = bms_status_handler(led_pin = USR_LED)
error = error_handler(led_pin = ERR_LED)
ades = ADES1830.ADES1830()
ds18 = DS18B20.DS18B20(TEMP_OWM_PIN, False)
command= bms_command_handler()

config = bms_config_handler()
info = bms_info_handler()
monitor = bms_monitor_handler()
balancer = bms_balancing_handler()

async def listen_to_master_task():
   while True:
      # listen to master for commands and settings
      if e.any():
         peer, msg = e.recv(timeout_ms=100) 
         if peer == master:
            # 2. deserialize JSON to dict
            dict = json.loads(msg)
            # 3. executer settins handler or command handler
            if dict.get("type") == "cfg":
               response = config.set_config(dict)
            elif dict.get("type") == "cmd":
               response = command.execute_command(dict.get("command"))
            else:
               print("Unknown data reveived")
            # 3. serialize response to JSON
            json_str = json.dumps(response)
            # 4. encode JSON to bytes
            data_bytes = json_str.encode('utf-8')
            # 5. send data_bytes to master using ESPNow
            e.send(master, data_bytes)
      else:
         await asyncio.sleep_ms(10)

async def main():
   status.set_state("Init")
   ncells = ades.init()
   while ncells <= 3:
      print("ADES1830 init failed try again..")
      await asyncio.sleep(1)
      ncells = ades.init()
   # Get device ID   
   info.set_id(ades.get_device_id())
   info.set_ncells(ncells)
   # 2. Init OneWire Temp sensors (get nr of sensors)
   info.set_ntemp(len(ds18.get_roms()))  
   # 4. discover master
   print("Discovering master...")
   while True:
      master, msg = e.recv(timeout_ms=10) 
      if msg == b'I AM YOUR MASTER':
         print("Discovered master:", master)
         e.add_peer(master)
         json_str = json.dumps(info.get_info())
         data_bytes = json_str.encode('utf-8')  
         e.send(master, data_bytes)
         break
      else:
         await asyncio.sleep(5)
   status.set_state("Idle")
   #5. Master discovered --> listen to commands
   asyncio.create_task(listen_to_master_task())
   status.set_state("Monitoring")
   while True:
      await asyncio.sleep(1000)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped by user")