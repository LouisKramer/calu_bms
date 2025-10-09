# acs71240.py
# MicroPython library for Allegro ACS71240 current sensor IC
# Variant: ACS71240KEXBLT-030B3
# Target: ESP32-S3-WROOM-1-N8R8 (compatible with other ESP32 variants running MicroPython)
# 
# Features:
# - Reads analog output voltage from VIOUT pin using ADC
# - Converts voltage to current using sensitivity and zero-voltage offset
# - Supports optional FAULT pin monitoring (active low)
# - Interrupt callback support for FAULT detection
# - Zero-offset calibration method
# - Basic error handling and configuration
# - Docstrings for methods
# 
# Usage example:
# from machine import Pin
# from acs71240 import ACS71240
# sensor = ACS71240(viout_pin=Pin(1), fault_pin=Pin(2))  # Use appropriate GPIO pins
# current = sensor.read_current()
# if sensor.is_fault():
#     print("Overcurrent fault detected!")

import machine
import time

class ACS71240:
    """
    Class for interfacing with the ACS71240KEXBLT-030B3 current sensor.
    
    Parameters:
    - viout_pin: machine.Pin object or pin number for VIOUT (analog output)
    - fault_pin: Optional machine.Pin object or pin number for FAULT (digital input, active low)
    - vcc: Supply voltage (default 3.3V)
    - sensitivity: Sensitivity in V/A (default 0.044 V/A for this variant)
    - zero_volt: Zero-current output voltage (default 1.65V for bidirectional at 3.3V VCC)
    """
    
    def __init__(self, viout_pin, fault_pin=None, vcc=3.3, sensitivity=0.044, zero_volt=1.65):
        if not isinstance(viout_pin, machine.Pin):
            viout_pin = machine.Pin(viout_pin, machine.Pin.IN)
        self.adc = machine.ADC(viout_pin)
        # Configure ADC for full range (0-3.3V on ESP32-S3)
        self.adc.atten(machine.ADC.ATTN_11DB)  # 0-3.6V range, suitable for 3.3V
        self.adc.width(machine.ADC.WIDTH_12BIT)  # 12-bit resolution
        
        self.fault = None
        if fault_pin is not None:
            if not isinstance(fault_pin, machine.Pin):
                fault_pin = machine.Pin(fault_pin, machine.Pin.IN, machine.Pin.PULL_UP)
            self.fault = fault_pin
        
        self.vcc = vcc
        self.sensitivity = sensitivity
        self.zero_volt = zero_volt
        
        # Wait for power-on time (80us typ)
        time.sleep_us(100)
    
    def read_voltage(self):
        """
        Read the raw voltage from VIOUT pin.
        
        Returns:
        - float: Voltage in volts
        """
        # read_uv() returns microvolts
        return self.adc.read_uv() / 1_000_000.0
    
    def read_current(self, samples=1):
        """
        Read the current based on VIOUT voltage.
        
        Parameters:
        - samples: Number of samples to average (default 1) for noise reduction
        
        Returns:
        - float: Current in amperes (positive for one direction, negative for reverse)
        """
        total_voltage = 0.0
        for _ in range(samples):
            total_voltage += self.read_voltage()
            time.sleep_us(10)  # Small delay between samples
        avg_voltage = total_voltage / samples
        current = (avg_voltage - self.zero_volt) / self.sensitivity
        return current
    
    def is_fault(self):
        """
        Check if overcurrent fault is active.
        
        Returns:
        - bool: True if fault active (FAULT pin low), False otherwise
        
        Raises:
        - ValueError: If fault_pin not configured
        """
        if self.fault is None:
            raise ValueError("FAULT pin not configured")
        return self.fault.value() == 0
    
    def set_fault_callback(self, callback):
        """
        Set an interrupt callback for FAULT pin on falling edge (fault activation).
        
        Parameters:
        - callback: Function to call on fault (takes Pin as argument)
        
        Raises:
        - ValueError: If fault_pin not configured
        """
        if self.fault is None:
            raise ValueError("FAULT pin not configured")
        self.fault.irq(trigger=machine.Pin.IRQ_FALLING, handler=callback)
    
    def calibrate_zero(self, samples=100):
        """
        Calibrate the zero-current offset voltage by averaging samples at zero current.
        
        Parameters:
        - samples: Number of samples to average (default 100)
        
        Updates:
        - self.zero_volt with the calibrated value
        """
        total_voltage = 0.0
        for _ in range(samples):
            total_voltage += self.read_voltage()
            time.sleep_us(100)  # Delay for stability
        self.zero_volt = total_voltage / samples
    
    def get_specs(self):
        """
        Return a dictionary of key specifications for this variant.
        
        Returns:
        - dict: Specifications
        """
        return {
            "variant": "ACS71240KEXBLT-030B3",
            "vcc": self.vcc,
            "sensitivity": self.sensitivity,
            "zero_volt": self.zero_volt,
            "range": "±30A",
            "fault_trip": "±30A",
            "bandwidth": "120kHz",
            "response_time": "4us typ",
            "fault_response": "1.5us typ",
            "noise": "78mARMS typ",
            "package": "QFN-12"
        }