# Pins
class master_hal:
    ADC_CURRENT_BAT_PIN = 4
    CURRENT_FAULT_PIN = 5 #input for overcurrent 
    BAT_FAULT_PIN = 10 #Output for driving sic and safe relay

    SPI_SCLK_PIN = 6
    SPI_MOSI_PIN = 7
    SPI_MISO_PIN = 15
    SPI_CS_PIN = 16
    OWM_TEMP_PIN = 9

    BUZZER_PIN = 17
    LED_USER_PIN = 18
    LED_ERR_PIN = 8

    INT_REL0_PIN = 14
    INT_REL1_PIN = 21
    EXT_REL0_PIN = 11

    CAN_TX_PIN = 40
    CAN_RX_PIN = 39

class slave_hal:
    SPI_CS_STR0_PIN = 4
    SPI_CS_STR1_PIN = 5
    SPI_SCLK_PIN = 6
    SPI_MOSI_PIN = 7
    SPI_MISO_PIN = 15
    SPI_CS0_PIN = 16
    SPI_CS1_PIN = 17
    SPI_CS2_PIN = 18
    SPI_CS3_PIN = 8
    I2C_SCL_PIN = 46
    I2C_SDA_PIN = 3
    OWM_TEMP_PIN = 9
    CS_EN_PIN = 10
    ACT_BAL_PIN = 47
    ACT_BAL_PWM_PIN = 48
    LED_USER_PIN = 40
    LED_ERR_PIN = 39
    STR_SEL0_PIN = 41
    STR_SEL1_PIN = 42
    STR_SEL2_PIN = 2
    STR_SEL3_PIN = 38