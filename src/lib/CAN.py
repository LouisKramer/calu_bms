# bms_can.py
# MicroPython CAN Communication Module for BMS
# Sends periodic status frames to inverter / other devices
# Assumes ESP32 with external transceiver (e.g. SN65HVD230)
# Uses machine.CAN (native ESP32 TWAI support)

import asyncio
import time
import struct
from machine import CAN, Pin

class BMSCan:
    """
    CAN Bus communication for BMS.
    - Broadcasts status (SOC, voltages, currents, faults) every 1s
    - Receives inverter commands (current requests, fault clears)
    - Standard IDs (0x180-0x1FF) for BMS
    - Configurable baudrate, node ID
    """

    # CAN IDs
    ID_BMS_STATUS = 0x180     # Broadcast: SOC, voltages, current, temp
    ID_BMS_FAULTS = 0x181     # Fault flags
    ID_BMS_CURRENT_LIMITS = 0x182  # Charge/Discharge limits
    ID_INVERTER_COMMAND = 0x200  # Receive: current setpoints, reset

    def __init__(self, config):
        """
        config (dict):
            can_tx_pin    : int (GPIO) - CAN TX
            can_rx_pin    : int (GPIO) - CAN RX
            baudrate      : int (e.g. 500000 for 500 kbps)
            node_id       : int (optional, for filtering)
            update_interval: float (s) - broadcast rate
        """
        self.config = config
        self.tx_pin = config['can_tx_pin']
        self.rx_pin = config['can_rx_pin']
        self.baudrate = config.get('baudrate', 500000)
        self.update_interval = config.get('update_interval', 1.0)

        # CAN Setup (ESP32 native)
        self.can = CAN(0, mode=CAN.NORMAL, baudrate=self.baudrate,
                       pins=(self.tx_pin, self.rx_pin), tx=Pin.OPEN_DRAIN)
        self.can.begin()

        # State
        self.last_update = 0
        self.received_commands = []

        # Background task
        asyncio.create_task(self._rx_task())

    async def _rx_task(self):
        """Receive loop for inverter commands."""
        while True:
            if self.can.any():
                msg = self.can.recv()
                if msg.id == self.ID_INVERTER_COMMAND:
                    self._handle_command(msg.data)
            await asyncio.sleep(0.01)  # 100 Hz poll

    def _handle_command(self, data):
        """Parse inverter commands (e.g. set current, clear faults)."""
        if len(data) < 4:
            return
        cmd = struct.unpack('<I', data[:4])[0]
        if cmd == 0x01:  # Clear faults
            self.clear_faults_via_can()
        elif cmd == 0x02:  # Set charge current
            charge = struct.unpack('<f', data[4:8])[0]
            self.requested_charge_current = charge
        # Add more commands as needed
        self.received_commands.append((time.time(), cmd))

    def send_status(self, status_dict):
        """
        Broadcast BMS status frame.
        status_dict from BatteryProtection.update():
            - soc, pack_voltage, cell_voltages, current, temperature
            - charge_current_limit, discharge_current_limit
            - faults (dict)
        """
        now = time.time()
        if now - self.last_update < self.update_interval:
            return

        # Frame 1: Basic Status (8 bytes)
        soc_byte = int(status_dict['soc'] / 100 * 255)  # 0-255
        current_scaled = int(status_dict['current'] * 10)  # -255 to 255 A
        temp_byte = int(max(0, min(255, status_dict['temperature'] + 40)))  # -40 to 215°C offset
        data1 = struct.pack('<BBbB', soc_byte, int(status_dict['pack_voltage'] * 10),
                            current_scaled, temp_byte)
        self.can.send(self.ID_BMS_STATUS, data1)

        # Frame 2: Current Limits (8 bytes)
        charge_limit = int(status_dict['charge_current_limit'])
        dis_limit = int(status_dict['discharge_current_limit'])
        enabled = 1 if status_dict['inverter_enabled'] else 0
        data2 = struct.pack('<HHBB', charge_limit, dis_limit, enabled, 0)  # Padding
        self.can.send(self.ID_BMS_CURRENT_LIMITS, data2)

        # Frame 3: Faults (8 bytes, bitflags)
        fault_flags = 0
        if status_dict['faults'].get('hardware_overcurrent'): fault_flags |= 1 << 0
        if status_dict['faults'].get('critical_over_voltage'): fault_flags |= 1 << 1
        if status_dict['faults'].get('critical_under_voltage'): fault_flags |= 1 << 2
        if status_dict['faults'].get('over_temp'): fault_flags |= 1 << 3
        if status_dict['faults'].get('imbalance'): fault_flags |= 1 << 4
        # Add more bits for other faults
        data3 = struct.pack('<IBBBB', fault_flags, 0, 0, 0, 0)  # 32-bit flags + padding
        self.can.send(self.ID_BMS_FAULTS, data3)

        # Optional: Cell voltages (multi-frame if >4 cells)
        if len(status_dict['cell_voltages']) <= 4:
            cell_bytes = [int(v * 100) for v in status_dict['cell_voltages']]
            data_cells = struct.pack('<BBBB', *cell_bytes[:4])  # 0.01V resolution
            self.can.send(0x183, data_cells)  # Cell frame ID

        self.last_update = now

    def clear_faults_via_can(self):
        """Clear faults received over CAN."""
        # Call your BMS clear_faults() here
        print("Faults cleared via CAN")

    def close(self):
        """Stop CAN."""
        self.can.deinit()

# === Usage Example ===
"""
# In main.py
can_config = {
    'can_tx_pin': 21,      # ESP32 GPIO
    'can_rx_pin': 22,
    'baudrate': 500000,    # 500 kbps
    'update_interval': 1.0
}
can_bus = BMSCan(can_config)

# In sensor loop:
status = await protector.update(...)  # From BatteryProtection
can_bus.send_status(status)

# Graceful shutdown:
can_bus.close()
"""