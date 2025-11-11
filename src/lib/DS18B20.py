# DS18B20 MicroPython Driver
# Simple 1-Wire temperature sensor driver using built-in onewire module

import onewire
import ds18x20
from machine import Pin

class DS18B20:
    """
    Driver for DS18B20 digital temperature sensor.
    Supports single or multiple sensors on a 1-Wire bus.
    """

    def __init__(self, data_pin, pullup=True):
        """
        Initialize DS18B20 on the specified GPIO pin.
        :param data_pin: GPIO pin number for 1-Wire data line
        :param pullup: Enable internal pull-up (default True)
        """
        self.data_pin = Pin(data_pin, Pin.IN if pullup else Pin.OUT)
        if pullup:
            self.data_pin = Pin(data_pin, Pin.IN, Pin.PULL_UP)
        self.bus = onewire.OneWire(self.data_pin)
        self.sensors = ds18x20.DS18X20(self.bus)
        self.roms = self.sensors.scan()  # Scan for connected sensors
        if not self.roms:
            raise ValueError("No DS18B20 sensors found on the bus")

    def get_temperatures(self):
        """
        Read temperature from all detected sensors.
        :return: Dict of ROM addresses to temperatures in °C
        """
        self.sensors.convert_temp()
        temps = {}
        for i, rom in enumerate(self.roms):
            temp = self.sensors.read_temp(rom)
            if temp != -999.0:  # Invalid reading
                temps[i] = round(temp, 2)
        return temps

    def get_temperature(self, rom=None):
        """
        Read temperature from a specific sensor or first one.
        :param rom: ROM address (bytes) or None for first sensor
        :return: Temperature in °C
        """
        if rom is None:
            rom = self.roms[0]
        self.sensors.convert_temp()
        temp = self.sensors.read_temp(rom)
        return round(temp, 2) if temp != -999.0 else None

    def get_roms(self):
        """
        Get dictionary of detected ROM addresses, numbered starting from 0.
        :return: Dict with integer keys (starting from 0) and ROM bytes as values
        """
        return {i: rom for i, rom in enumerate(self.roms)}