from machine import Pin
import asyncio
import ADES1830
import time
print("main started")

# Main execution
# Initialize ADES1830
ades = ADES1830.ADES1830()

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
while True:
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

    pwm = ades.set_pwm([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15])
    print(f"PWM: {list(pwm)}")

    cell_pwm = ades.set_pwm_cell(10, 4)
    print(f"PWM cell 4: {cell_pwm}")

    pwm = ades.get_pwm()
    print(f"PWM: {list(pwm)}")

    ades.set_ref_power_up(1)
    #ades.start_cell_volt_conv(redundant=False, continuous=True, discharge_permitted=False, reset_filter=False, openwire=0)
    #ades.start_s_adc_conv(continuous=True, discharge_permitted=False, openwire=0)
    #ades.start_aux_adc_conv(openwire=False, pullup=False)
    #ades.start_aux2_adc_conv()
    #time.sleep_us(1)
    #for i in range(2):
    #    cell = ades.get_all_cell_voltages()
    #    cell3 = ades.get_cell_voltage(cell=3)
    #    internal_temp = ades.get_internal_temp()
    #    device_id = ades.get_device_id()
    #    reference_voltage2 = ades.get_reference_voltage2()
    #    digital_supply_voltage = ades.get_digital_supply_voltage()
    #    print(f"Cell Voltages: {cell[0]:.4f} V, {cell[1]:.4f} V, {cell3:.4f} V")
    #    print(f"Internal Temp: {internal_temp:.2f} °C")
    #    print(f"Device ID: {device_id:04x}")
    #    print(f"Reference Voltage 2: {reference_voltage2:.4f} V")
    #    print(f"Digital Supply Voltage: {digital_supply_voltage:.4f} V")
    #    asyncio.sleep_ms(1)

        
    time.sleep(5)
