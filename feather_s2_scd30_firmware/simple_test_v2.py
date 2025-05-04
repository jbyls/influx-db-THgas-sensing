"""
Simplified SCD-30 test for Feather S2 - Version 2
This is a minimal script to test I2C and the SCD-30 sensor
Compatible with different versions of the adafruit_scd30 library
"""
import time
import board
import busio

print("Starting simple SCD-30 test...")

# Initialize I2C
i2c = busio.I2C(board.SCL, board.SDA)

# Scan for I2C devices
print("Scanning for I2C devices...")
devices = []
try:
    i2c.try_lock()
    for address in i2c.scan():
        devices.append(address)
        print(f"Found device at address: 0x{address:02x}")
    i2c.unlock()
except Exception as e:
    print(f"Error during I2C scan: {e}")

if not devices:
    print("No I2C devices found! Check wiring.")
else:
    print(f"Found {len(devices)} I2C device(s)")
    
    # Look for SCD-30 at address 0x61
    if 0x61 in devices:
        print("SCD-30 found at address 0x61!")
        try:
            import adafruit_scd30
            
            # Initialize the sensor
            scd = adafruit_scd30.SCD30(i2c)
            
            # Configure the sensor - check which methods are available
            print("SCD-30 library version info:")
            print("Available methods:", dir(scd))
            
            # Set measurement interval if available
            if hasattr(scd, 'measurement_interval'):
                scd.measurement_interval = 2
                print("Set measurement interval to 2 seconds")
            
            # Start measurements - handle different library versions
            if hasattr(scd, 'start_periodic_measurement'):
                scd.start_periodic_measurement()
                print("Started periodic measurement")
            elif hasattr(scd, 'start_continuous_measurement'):
                scd.start_continuous_measurement()
                print("Started continuous measurement")
            else:
                print("No start measurement method found - sensor may start automatically")
            
            print("Waiting for first measurement (this may take a few seconds)...")
            # Wait for the first measurement to be available
            timeout = 0
            data_available_attr = 'data_available' if hasattr(scd, 'data_available') else 'data_ready'
            
            while not getattr(scd, data_available_attr) and timeout < 15:
                print(".", end="")
                time.sleep(1)
                timeout += 1
            print()
            
            # Continuous reading loop
            print("Starting continuous readings (press Ctrl+C to stop):")
            while True:
                if getattr(scd, data_available_attr):
                    # Check which attributes are available for readings
                    if hasattr(scd, 'CO2'):
                        co2 = scd.CO2
                    elif hasattr(scd, 'co2'):
                        co2 = scd.co2
                    else:
                        co2 = "N/A"
                        
                    if hasattr(scd, 'temperature'):
                        temp = scd.temperature
                    else:
                        temp = "N/A"
                        
                    if hasattr(scd, 'relative_humidity'):
                        humidity = scd.relative_humidity
                    elif hasattr(scd, 'humidity'):
                        humidity = scd.humidity
                    else:
                        humidity = "N/A"
                    
                    print(f"CO2: {co2} ppm, Temp: {temp} °C, RH: {humidity} %")
                time.sleep(2)
                
        except ImportError:
            print("SCD-30 library not found! Make sure adafruit_scd30.mpy is in the /lib folder.")
        except Exception as e:
            print(f"Error testing SCD-30: {e}")
    else:
        print("SCD-30 not found at expected address 0x61. Check wiring and power.")

print("Test complete.")
