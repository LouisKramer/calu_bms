from machine import Pin
import asyncio
import ADES1830
import time
print("main started")

# Main execution
# Initialize ADES1830
ades = ADES1830.ADES1830()

# Instantiate registers
while True:
    ades.hal.wakeup()
    ades.set_ref_power_up(1)
    ades.start_cell_volt_conv(redundant=False, continuous=True, discharge_permitted=False, reset_filter=False, openwire=0)
    ades.start_s_adc_conv(continuous=True, discharge_permitted=False, openwire=0)
    ades.start_aux_adc_conv(openwire=False, pullup=False)
    ades.start_aux2_adc_conv()
    time.sleep_us(1)
    for i in range(10):
        cell = ades.get_all_cell_voltages()
        cell3 = ades.get_cell_voltage(cell=3)
        internal_temp = ades.get_internal_temp()
        device_id = ades.get_device_id()
        reference_voltage2 = ades.get_reference_voltage2()
        digital_supply_voltage = ades.get_digital_supply_voltage()
        print(f"Cell Voltages: {cell[0]:.4f} V, {cell[1]:.4f} V, {cell3:.4f} V")
        print(f"Internal Temp: {internal_temp:.2f} °C")
        print(f"Device ID: {device_id:04x}")
        print(f"Reference Voltage 2: {reference_voltage2:.4f} V")
        print(f"Digital Supply Voltage: {digital_supply_voltage:.4f} V")
        asyncio.sleep_ms(1)

        
    time.sleep(5)
