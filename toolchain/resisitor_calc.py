import math

def find_e24_resistor(target_value, R2, Vin, Vout):
    """
    Find the closest E24 series resistor value for R1, calculate percentage error,
    compute the voltage divider gain, and calculate the correction gain needed
    to achieve the desired output voltage.
    
    Args:
        target_value (float): Desired resistance value for R1 in ohms
        R2 (float): Resistance of R2 in ohms
        Vin (float): Input voltage in volts
        Vout (float): Desired output voltage in volts
        
    Returns:
        tuple: (closest E24 resistor value for R1, percentage error, actual gain, correction gain)
               where actual gain is Vout/Vin using the closest R1 and given R2,
               and correction gain is the factor to correct the actual output to the desired output
    """
    # E24 series values (per decade)
    e24_values = [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30,
                  33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91]
    
    # Handle negative or zero input for target_value, R2, or Vin
    if target_value <= 0 or R2 <= 0 or Vin <= 0 or Vout <= 0:
        return 0, 0.0, 0.0, 0.0
    
    # Determine the decade (power of 10) for target_value
    decade = 10 ** int(math.log10(target_value))
    
    # Scale E24 values to match the decade
    scaled_e24 = []
    for val in e24_values:
        scaled_e24.append(val * decade / 10)
        if decade > 1:
            scaled_e24.append(val * (decade / 10) / 10)
        if decade < 1e6:
            scaled_e24.append(val * (decade * 10) / 10)
    
    # Find the closest value for R1
    closest_R1 = min(scaled_e24, key=lambda x: abs(x - target_value))
    
    # Calculate percentage error for R1
    error = abs(closest_R1 - target_value) / target_value * 100
    
    # Calculate desired gain using target R1
    G_desired = R2 / (target_value + R2)
    
    # Calculate actual gain using closest R1
    G_actual = R2 / (closest_R1 + R2)
    
    # Calculate correction gain
    G_correction = G_desired / G_actual if G_actual != 0 else 0.0
    
    return round(closest_R1, 3), round(error, 2), round(G_actual, 3), round(G_correction, 3)

# Example usage
if __name__ == "__main__":
    import math
    R2 = 1000
    Ua = 2

    for i in range(1,16):
        Uin = i * 4
        R1 = R2 * ((Uin/Ua)-1)
        Re24, error, G_act, G_corr = find_e24_resistor(R1, R2, Uin, Ua)
        print(f"Uin = {Uin}, R1 = {R1}, R1_e24 = {Re24}, error = {error}%, Gain_corr = {G_corr}")