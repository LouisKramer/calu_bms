# wifi_manager.py
import network
import asyncio
import machine
import time
from common.logger import *


class WifiManager:
    """
    Simple async Wi-Fi connection manager for master device with LED feedback.
    
    LED states (active-low = inverted):
    - ON (led.value(0))     → connected
    - slow blink            → connecting
    - 3 quick blinks        → failed / retrying
    - OFF (led.value(1))    → stopped / inactive
    """

    def __init__(
        self,
        ssid: str,
        password: str,
        hostname: str = "bmsnow-master",
        led_pin: int = 2,                  # onboard LED on many ESP32 boards
        connect_timeout_s: float = 15.0,
        retry_delay_s: float = 8.0,
    ):
        self.ssid = ssid
        self.password = password
        self.hostname = hostname
        self.connect_timeout_s = connect_timeout_s
        self.retry_delay_s = retry_delay_s

        self.log = create_logger("WifiMgr", level=LogLevel.INFO)

        # Wi-Fi
        self.wlan = network.WLAN(network.STA_IF)

        # LED (active-low: 0 = lit, 1 = off)
        self.led = machine.Pin(led_pin, machine.Pin.OUT)
        self.led.value(1)  # off at start

        # State
        self._running = False
        self._task = None
        self._last_status = "unknown"

    def _led_on(self):
        self.led.value(0)   # lit

    def _led_off(self):
        self.led.value(1)   # dark

    def _led_toggle(self):
        self.led.value(not self.led.value())

    async def _blink_pattern(self, on_ms: int, off_ms: int, count: int):
        """Blink LED count times (active-low aware)"""
        for _ in range(count):
            self._led_on()
            await asyncio.sleep_ms(on_ms)
            self._led_off()
            await asyncio.sleep_ms(off_ms)

    def _set_status(self, state: str):
        """Update LED according to Wi-Fi state"""
        if state == "connected":
            self._led_on()
            pattern = "solid ON"
        elif state == "connecting":
            self._led_toggle()           # called repeatedly → slow blink
            pattern = "slow blink"
        elif state == "failed":
            asyncio.create_task(self._blink_pattern(120, 120, 3))  # 3 quick blinks
            pattern = "3 quick blinks"
        else:
            self._led_off()
            pattern = "OFF"

        if state != self._last_status:
            self.log.info(f"WiFi status → {state} (LED: {pattern})")
            self._last_status = state

    async def _connection_task(self):
        self._running = True

        while self._running:
            if self.wlan.isconnected():
                self._set_status("connected")
                await asyncio.sleep(8)  # relaxed check when connected
                continue

            self._set_status("connecting")
            self.log.info(f"Connecting to {self.ssid} ...")

            try:
                self.wlan.active(True)
                self.wlan.config(dhcp_hostname=self.hostname)
                self.wlan.connect(self.ssid, self.password)

                start = time.ticks_ms()
                while not self.wlan.isconnected():
                    if time.ticks_diff(time.ticks_ms(), start) > int(self.connect_timeout_s * 1000):
                        raise RuntimeError("Connection timeout")
                    self._led_toggle()              # visual feedback while waiting
                    await asyncio.sleep_ms(300)

                ip = self.wlan.ifconfig()[0]
                self.log.info(f"Connected → IP: {ip}")
                self._set_status("connected")

            except Exception as e:
                self.log.warn(f"WiFi failed: {e}")
                self._set_status("failed")
                await asyncio.sleep(self.retry_delay_s)

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._connection_task())
            self.log.info("WiFi manager started")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self.wlan.disconnect()
        self.wlan.active(False)
        self._led_off()
        self.log.info("WiFi manager stopped")

    @property
    def is_connected(self) -> bool:
        return self.wlan.isconnected()

    @property
    def ip_address(self) -> str:
        return self.wlan.ifconfig()[0] if self.is_connected else "0.0.0.0"
