"""
Basic test script for SCD-30 CO2 sensor on Feather S2
This script scans for I2C devices and tests the SCD-30 sensor
"""
import time
import board
import busio
import digitalio

# Set up the built-in LED for status indication
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# Flash LED to indicate script is starting
for _ in range(3):
    led.value = True
    time.sleep(0.2)
    led.value = False
    time.sleep(0.2)

print("Starting SCD-30 sensor test...")

# Initialize I2C
i2c = busio.I2C(board.SCL, board.SDA)

# Scan for I2C devices
devices = []
print("Scanning for I2C devices...")

try:
    i2c.try_lock()
    for address in i2c.scan():
        devices.append(address)
        print(f"Found device at address: 0x{address:02x}")
    i2c.unlock()
except Exception as e:
    print(f"Error during I2C scan: {e}")

if not devices:
    print("No I2C devices found!")
    print("Please check your wiring connections.")
else:
    print(f"Found {len(devices)} I2C device(s)")
    
    # Try to import and use the SCD-30 library
    try:
        import adafruit_scd30
        
        print("Initializing SCD-30 sensor...")
        # The SCD-30 has a default I2C address of 0x61
        scd = adafruit_scd30.SCD30(i2c)
        
        # Configure the sensor
        scd.measurement_interval = 2  # seconds
        
        # Start continuous measurements
        scd.start_periodic_measurement()
        
        print("Waiting for first measurement (this may take a few seconds)...")
        # Wait for the first measurement to be available
        timeout = 0
        while not scd.data_available and timeout < 10:
            led.value = not led.value  # Toggle LED while waiting
            time.sleep(0.5)
            timeout += 0.5
            print(".", end="")
        print()
        
        if scd.data_available:
            # Read and display sensor data
            print("SCD-30 sensor data:")
            print(f"CO2: {scd.CO2:.1f} ppm")
            print(f"Temperature: {scd.temperature:.2f} °C")
            print(f"Relative Humidity: {scd.relative_humidity:.2f} %")
            
            # Indicate success with LED
            for _ in range(5):
                led.value = True
                time.sleep(0.1)
                led.value = False
                time.sleep(0.1)
        else:
            print("No data available from SCD-30 sensor after timeout")
            
    except ImportError:
        print("SCD-30 library not found!")
        print("Please install the adafruit_scd30 library in the lib folder.")
    except Exception as e:
        print(f"Error testing SCD-30 sensor: {e}")

print("Test complete.")
