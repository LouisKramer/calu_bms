from machine import Pin

class SN74HC154:
    def __init__(self, enable_pin, a0_pin, a1_pin, a2_pin, a3_pin):
        """Initialize the SN74HC154 demultiplexer with address pins.
        
        Args:
            a0_pin (int): GPIO pin number for A0 (LSB)
            a1_pin (int): GPIO pin number for A1
            a2_pin (int): GPIO pin number for A2 
            a3_pin (int): GPIO pin number for A3 (MSB)
        """
        self.en = Pin(enable_pin, Pin.OUT)
        self.a0 = Pin(a0_pin, Pin.OUT)
        self.a1 = Pin(a1_pin, Pin.OUT)
        self.a2 = Pin(a2_pin, Pin.OUT)
        self.a3 = Pin(a3_pin, Pin.OUT)
        self.select(0)  # Set initial output to Y0
        self.__disable()

    def select(self, output):
        """Select one of the 16 outputs (Y0 to Y15).
        
        Args:
            output (int): Output to select (0 to 15)
        
        Raises:
            ValueError: If output is not in range 0 to 15
        """
        if not 0 <= output <= 15:
            raise ValueError("Output must be between 0 and 15")
        self.__enable()
        # Set address pins based on binary value of output
        self.a0.value(output & 0x01)      # A0: LSB
        self.a1.value((output >> 1) & 0x01)  # A1
        self.a2.value((output >> 2) & 0x01)  # A2: 
        self.a3.value((output >> 3) & 0x01)  # A3: MSB

    def deselect(self):
        self.__disable()

    def __enable(self):
        self.en.value(0)

    def __disable(self):
        self.en.value(1)