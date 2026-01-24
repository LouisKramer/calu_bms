import network
import uasyncio as asyncio
import time
from machine import Pin

class WlanManager:
    """
    Async WiFi manager with:
    - Auto-reconnect
    - Custom hostname
    - LED status (active-LOW / inverted logic on many ESP32 boards):
      - ON     = connected          → led.off()
      - BLINK  = connecting         → toggle led.off() / led.on()
      - OFF    = disconnected       → led.on()
    """
    
    def __init__(
        self,
        ssid: str,
        password: str,
        hostname: str = "esp32-device",
        led_pin: int = 2,
        check_interval_sec: float = 8.0,
        blink_interval_ms: int = 400
    ):
        self.ssid = ssid
        self.password = password
        self.check_interval = check_interval_sec
        self.blink_interval = blink_interval_ms
        
        network.hostname(hostname)
        
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        
        # LED: active-low (common on ESP32 dev boards)
        self.led = Pin(led_pin, Pin.OUT)
        self.led.on()                            # start OFF (active-low)
        
        self._task = None
        self._running = False
        self._connecting = False

    async def connect_once(self, timeout_sec: float = 12.0) -> bool:
        if self.wlan.isconnected():
            print("Already connected")
            self._connecting = False
            self.led.off()                       # ON (active-low)
            return True
            
        print(f"Connecting to {self.ssid} ...")
        self.wlan.connect(self.ssid, self.password)
        self._connecting = True
        
        start = time.ticks_ms()
        timeout_ms = timeout_sec * 1000
        
        while not self.wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                print("Connection timeout")
                self._connecting = False
                self.led.on()                    # OFF
                return False
                            # Blink: toggle between ON (off) and OFF (on)
            self.led.value(not self.led.value())
            await asyncio.sleep_ms(self.blink_interval)
            
        print("Connected! IP:", self.wlan.ifconfig()[0])
        self._connecting = False
        self.led.off()                           # ON (active-low)
        return True

    async def _monitor_and_reconnect(self):
        while self._running:
            if self._connecting:
                # Blink: toggle between ON (off) and OFF (on)
                self.led.value(not self.led.value())
                await asyncio.sleep_ms(self.blink_interval)
                continue
                
            if not self.wlan.isconnected():
                print("WiFi disconnected → attempting reconnect...")
                self._connecting = True
                await self.connect_once(timeout_sec=10.0)
                self._connecting = False
                
            # Connected → LED ON
            # Disconnected & idle → LED OFF
            if self.wlan.isconnected():
                self.led.off()                   # ON
            else:
                self.led.on()                    # OFF
                
            await asyncio.sleep(self.check_interval)

    async def start(self):
        if self._running:
            return
            
        self._running = True
        await self.connect_once()
        self._task = asyncio.create_task(self._monitor_and_reconnect())
        print(f"WiFi reconnector started (hostname: {network.hostname()})")

    async def stop(self):
        self._running = False
        self._connecting = False
        self.led.on()                            # OFF on stop
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("WiFi reconnector stopped")

    def is_connected(self) -> bool:
        return self.wlan.isconnected()

    def ip_address(self):
        if self.is_connected():
            return self.wlan.ifconfig()[0]
        return None
