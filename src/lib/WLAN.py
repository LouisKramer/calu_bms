import network
import uasyncio as asyncio
import time
from machine import Pin
from enum import Enum


class WlanState(Enum):
    DISCONNECTED = 0
    CONNECTING   = 1
    CONNECTED    = 2
    ERROR        = 3


class WlanManager:
    """
    Robust async WiFi manager for ESP32 / MicroPython.
    Features: state machine, dedicated LED task, exponential backoff,
    reconnects=0 (no driver interference), optional LED, verbose mode.
    """

    def __init__(
        self,
        ssid: str,
        password: str,
        hostname: str = "esp32-device",
        led_pin: int | None = 2,          # None = disable LED
        check_interval_sec: float = 8.0,
        blink_interval_ms: int = 400,
        verbose: bool = True
    ):
        self.ssid = ssid
        self.password = password
        self.check_interval = check_interval_sec
        self.blink_interval = blink_interval_ms
        self.verbose = verbose

        network.hostname(hostname)

        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.config(reconnects=0)   # WE control reconnection

        # LED: active-low (standard on ESP32 dev boards)
        self.led = None
        if led_pin is not None:
            self.led = Pin(led_pin, Pin.OUT)
            self.led.on()                    # start OFF

        self.state = WlanState.DISCONNECTED
        self._failure_count = 0

        self._running = False
        self._monitor_task = None
        self._led_task = None

    def _log(self, msg: str):
        if self.verbose:
            print(f"[WiFi] {msg}")

    async def connect_once(self, timeout_sec: float = 12.0) -> bool:
        """One-shot connection attempt. Pure, no LED code."""
        if self.wlan.isconnected():
            self.state = WlanState.CONNECTED
            self._log(f"Already connected → {self.wlan.ifconfig()[0]}")
            self._failure_count = 0
            return True

        self.state = WlanState.CONNECTING
        self._log(f"Connecting to {self.ssid}...")

        # Clean slate before every attempt
        if self.wlan.isconnected():
            self.wlan.disconnect()
            await asyncio.sleep_ms(250)

        self.wlan.connect(self.ssid, self.password)

        start = time.ticks_ms()
        timeout_ms = int(timeout_sec * 1000)

        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            status = self.wlan.status()

            if status == network.STAT_GOT_IP:
                ip = self.wlan.ifconfig()[0]
                ch = self.wlan.config("channel")
                self._log(f"Connected! IP: {ip}  channel: {ch}")
                self.state = WlanState.CONNECTED
                self._failure_count = 0
                return True

            elif status in (network.STAT_NO_AP_FOUND, network.STAT_WRONG_PASSWORD,
                           network.STAT_CONNECT_FAIL):
                err = {network.STAT_NO_AP_FOUND: "AP not found/out of range",
                       network.STAT_WRONG_PASSWORD: "Wrong password",
                       network.STAT_CONNECT_FAIL: "Other failure"}.get(status, f"status={status}")
                self._log(f"{err}")
                self.state = WlanState.ERROR
                self._failure_count += 1
                return False

            await asyncio.sleep_ms(self.blink_interval)   # poll rate

        self._log("Timeout")
        self.state = WlanState.ERROR
        self._failure_count += 1
        return False

    async def _monitor_loop(self):
        """Main monitor + auto-reconnect with backoff."""
        await self.connect_once()                     # initial attempt

        while self._running:
            if self.state == WlanState.CONNECTED and self.wlan.isconnected():
                self._failure_count = 0
                await asyncio.sleep(self.check_interval)
                continue

            # Reconnect path
            self._failure_count += 1
            backoff = min(64, 4 * (2 ** (self._failure_count - 1)))   # 4, 8, 16, ..., 64 s

            self._log(f"Disconnected → retry #{self._failure_count} after {backoff}s backoff")
            await asyncio.sleep(backoff)

            await self.connect_once(timeout_sec=10.0)

            await asyncio.sleep(self.check_interval)

    async def _led_loop(self):
        """Dedicated LED control – never blocks anything else."""
        while self._running:
            if self.led is None:
                await asyncio.sleep(1)
                continue

            if self.state == WlanState.CONNECTING:
                self.led.value(not self.led.value())   # blink
                await asyncio.sleep_ms(self.blink_interval)
            elif self.state == WlanState.CONNECTED:
                self.led.off()                         # ON (active-low)
                await asyncio.sleep(0.5)
            else:
                self.led.on()                          # OFF
                await asyncio.sleep(0.5)

    def start(self):
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._led_task = asyncio.create_task(self._led_loop())
        self._log(f"WiFi manager started (hostname: {network.hostname()})")

    async def stop(self):
        self._running = False
        for task in (self._monitor_task, self._led_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self.led:
            self.led.on()                              # OFF
        if self.wlan.isconnected():
            self.wlan.disconnect()
        self.wlan.active(False)
        self.state = WlanState.DISCONNECTED
        self._log("WiFi manager stopped")

    def is_connected(self) -> bool:
        return self.state == WlanState.CONNECTED and self.wlan.isconnected()

    def ip_address(self) -> str | None:
        return self.wlan.ifconfig()[0] if self.is_connected() else None

    @property
    def rssi(self) -> int | None:
        return self.wlan.status("rssi") if self.is_connected() else None

    @property
    def channel(self) -> int | None:
        return self.wlan.config("channel") if self.is_connected() else None

    async def wait_for_connection(self, timeout_sec: float = 30.0) -> bool:
        """Block until connected (or timeout)."""
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_sec * 1000:
            if self.is_connected():
                return True
            await asyncio.sleep_ms(400)
        return False