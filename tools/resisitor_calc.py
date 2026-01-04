import math

def find_closest_e24(target_value):
    """
    Find the closest E24 series resistor value.
    
    Args:
        target_value (float): Desired resistance value in ohms
        
    Returns:
        float: Closest E24 resistor value, rounded to 3 decimal places
    """
    if target_value <= 0:
        return 0.0
    
    # E24 series values (per decade)
    e24_values = [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30,
                  33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91]
    
    # Determine the decade (power of 10) for target_value
    decade = 10 ** int(math.log10(target_value))
    
    # Scale E24 values to match the decade and adjacent decades
    scaled_e24 = []
    for val in e24_values:
        scaled_e24.append(val * decade / 10)
        if decade > 1:
            scaled_e24.append(val * (decade / 10) / 10)
        if decade < 1e6:
            scaled_e24.append(val * (decade * 10) / 10)
    
    # Find the closest value
    closest = min(scaled_e24, key=lambda x: abs(x - target_value))
    
    return round(closest, 3)

def find_best_two_resistors(target_value, max_voltage, Vin, R2):
    """
    Find the best pair of E24 resistors in series to match target_value,
    ensuring voltage across each does not exceed max_voltage.
    
    Args:
        target_value (float): Desired total resistance in ohms
        max_voltage (float): Maximum voltage per resistor in volts
        Vin (float): Input voltage in volts
        R2 (float): Resistance of R2 in ohms
        
    Returns:
        tuple: (string representation of resistors, equivalent resistance, error)
    """
    best_error = float('inf')
    best_pair = None
    best_equiv = 0.0
    
    # Try all pairs of E24 resistors in reasonable range
    decade = 10 ** int(math.log10(target_value))
    e24_values = [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30,
                  33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91]
    scaled_e24 = []
    for val in e24_values:
        scaled_e24.append(val * decade / 10)
        if decade > 1:
            scaled_e24.append(val * (decade / 10) / 10)
        if decade < 1e6:
            scaled_e24.append(val * (decade * 10) / 10)
            
    for r1 in scaled_e24:
        for r2 in scaled_e24:
            equiv = r1 + r2
            if equiv == 0:
                continue
            # Calculate voltage across each resistor
            v_r1 = Vin * (r1 / (r1 + r2 + R2))
            v_r2 = Vin * (r2 / (r1 + r2 + R2))
            if v_r1 > max_voltage or v_r2 > max_voltage:
                continue
            error = abs(equiv - target_value) / target_value * 100
            if error < best_error:
                best_error = error
                best_pair = (r1, r2)
                best_equiv = equiv
    
    if best_pair:
        return f"{best_pair[0]} + {best_pair[1]}", best_equiv, best_error
    return None, 0.0, float('inf')

def find_e24_resistor(target_value, R2, Vin, Vout):
    """
    Find the closest E24 series resistor value for R1, calculate percentage error,
    compute the voltage divider gain, and calculate the correction gain needed
    to achieve the desired output voltage. Check if the voltage across R1 exceeds
    the maximum rated voltage for 0603 SMD resistor (75V), and if so, split R1 into two equal resistors.
    If the error exceeds 3%, try to find a better pair of resistors.
    
    Args:
        target_value (float): Desired resistance value for R1 in ohms
        R2 (float): Resistance of R2 in ohms
        Vin (float): Input voltage in volts
        Vout (float): Desired output voltage in volts
        
    Returns:
        tuple: (R1 representation (str or float), percentage error, actual gain, correction gain)
               where actual gain is Vout/Vin using the effective R1 and given R2,
               and correction gain is the factor to correct the actual output to the desired output
    """
    # Handle negative or zero input for target_value, R2, Vin, or Vout
    if target_value <= 0 or R2 <= 0 or Vin <= 0 or Vout <= 0:
        return 0, 0.0, 0.0, 0.0
    
    max_voltage = 50.0  # Maximum rated voltage for 0603 SMD resistor in volts
    
    # Find initial closest E24 for target
    closest_R1 = find_closest_e24(target_value)
    
    # Calculate voltage across R1
    voltage_R1 = Vin * (closest_R1 / (closest_R1 + R2))
    
    split = False
    #if voltage_R1 > max_voltage:
    #    split = True
    #    half_target = target_value / 2
    #    closest_half = find_closest_e24(half_target)
    #    closest_R1 = 2 * closest_half
    #    # Recalculate voltage (approximately half, but use new for accuracy)
    #    voltage_R1 = Vin * (closest_R1 / (closest_R1 + R2))  # Total voltage across effective R1
    
    # Calculate percentage error for effective R1
    error = abs(closest_R1 - target_value) / target_value * 100
    
    # If error > 3%, try two resistors
    if (error > 2.0) or (voltage_R1 > max_voltage):
        two_res, equiv_R1, two_error = find_best_two_resistors(target_value, max_voltage, Vin, R2)
        if two_error < error:
            closest_R1 = equiv_R1
            error = two_error
            split = True
            r1_repr = two_res
        else:
            split = True
            half_target = target_value / 2
            closest_half = find_closest_e24(half_target)
            closest_R1 = 2 * closest_half
            error = abs(closest_R1 - target_value) / target_value * 100
            r1_repr = f"2x {closest_half}" if split else closest_R1
    else:
        r1_repr = f"2x {closest_half}" if split else closest_R1

    
    # Calculate desired gain using target R1
    G_desired = R2 / (target_value + R2)
    
    # Calculate actual gain using effective closest R1
    G_actual = R2 / (closest_R1 + R2)
    
    # Calculate correction gain
    G_correction = G_desired / G_actual if G_actual != 0 else 0.0
    
    return r1_repr, round(error, 2), round(G_actual, 3), round(G_correction, 3)

# Example usage
if __name__ == "__main__":
    R2 = 10000
    Ua = 2
    G_prev = 1.0

    for i in range(1, 33):
        Uin = i * 4
        R1 = R2 * ((Uin / Ua) - 1)
        Re24, error, G_act, G_corr = find_e24_resistor(R1, R2, Uin, Ua)
        G_comb = round(G_corr * G_prev,3)
        G_prev = G_corr
        print(f"BAT{i:2d}:  Uin = {Uin:4d},  R1 = {R1:8.1f},  R1_e24 = {Re24:20},  error = {error:4.1f}%,  Gain_corr = {G_corr:.3f},  G_combined = {G_comb:.3f}")