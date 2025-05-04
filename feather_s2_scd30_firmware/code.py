"""
SCD30 CO2, Temperature, and Humidity Sensor Data Streaming
for Feather S2 with CircuitPython

This script continuously reads data from an SCD30 sensor and prints it
in both human-readable and JSON formats for easy parsing.
"""
import time
import board
import busio
import json
import supervisor
import microcontroller
import digitalio
import watchdog

# Set up the built-in LED for status indication
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# Blink LED to indicate startup
for _ in range(3):
    led.value = True
    time.sleep(0.1)
    led.value = False
    time.sleep(0.1)

# Configure watchdog timer (30 seconds timeout)
wdt = microcontroller.watchdog
wdt.timeout = 30.0
wdt.mode = watchdog.WatchDogMode.RESET

# Import the SCD30 library
try:
    import adafruit_scd30
    print("SCD30 library loaded successfully")
except ImportError:
    print("ERROR: adafruit_scd30 library not found!")
    print("Please install it using the CircuitPython Library Manager")
    while True:
        wdt.feed()  # Keep feeding watchdog while displaying error
        led.value = True
        time.sleep(0.1)
        led.value = False
        time.sleep(0.9)

# Configure auto-reload to be on
supervisor.runtime.autoreload = True

# Setup I2C connection with error handling
i2c = None
scd = None

def initialize_sensor():
    global i2c, scd
    try:
        # Setup I2C connection
        i2c = busio.I2C(board.SCL, board.SDA)
        
        # Initialize SCD30 sensor
        scd = adafruit_scd30.SCD30(i2c)
        
        # Set measurement interval (2 seconds)
        scd.measurement_interval = 2
        
        print("SCD30 sensor initialized successfully")
        return True
    except Exception as e:
        print(f"ERROR initializing SCD30: {e}")
        return False

# Try to initialize the sensor
if not initialize_sensor():
    print("Failed to initialize sensor, will retry...")

# Track sensor initialization status
sensor_initialized = (scd is not None)

# Function to read sensor data
def read_sensor():
    """Read data from SCD30 sensor and print it."""
    global sensor_initialized, scd, i2c
    
    # Feed the watchdog
    wdt.feed()
    
    # Check if sensor is initialized
    if not sensor_initialized:
        print("Sensor not initialized, attempting to initialize...")
        sensor_initialized = initialize_sensor()
        if not sensor_initialized:
            return False
    
    try:
        # Wait for sensor data to be available
        timeout = 0
        max_timeout = 5  # Maximum wait time in seconds
        
        while not scd.data_available and timeout < max_timeout:
            led.value = not led.value  # Toggle LED while waiting
            print("Waiting for sensor data...")
            time.sleep(0.5)
            timeout += 0.5
            wdt.feed()  # Feed watchdog while waiting
        
        if not scd.data_available:
            print("ERROR: No data available from SCD30 after timeout")
            return False
        
        # Read the sensor data
        co2 = scd.CO2
        temperature = scd.temperature
        humidity = scd.relative_humidity
        
        # Blink LED to indicate successful reading
        led.value = True
        
        # Print in human-readable format
        print(f"CO2: {co2:.1f} ppm, Temp: {temperature:.2f} °C, RH: {humidity:.2f} %")
        
        # Print in JSON format for easy parsing
        data = {
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "co2": round(co2, 1)
        }
        print(f"JSON:{json.dumps(data)}")
        
        led.value = False
        return True
    except OSError as e:
        print(f"I/O ERROR reading sensor: {e}")
        # Try to reinitialize the sensor on I/O errors
        print("Attempting to reinitialize sensor after I/O error...")
        sensor_initialized = False
        return False
    except Exception as e:
        print(f"ERROR reading sensor: {e}")
        return False

# Main loop
print("Starting SCD30 sensor readings...")
print("Press Ctrl+C to exit")

error_count = 0
max_errors = 5

while True:
    try:
        # Feed the watchdog
        wdt.feed()
        
        # Try to read sensor data
        success = read_sensor()
        
        if success:
            # Reset error count on successful reading
            error_count = 0
        else:
            # Increment error count
            error_count += 1
            print(f"Failed to read sensor. Error count: {error_count}/{max_errors}")
            
            if error_count >= max_errors:
                print("Too many errors, resetting microcontroller...")
                time.sleep(1)
                microcontroller.reset()
        
        # Wait before next reading (shorter if there was an error)
        if success:
            for _ in range(6):  # 3 seconds with watchdog feeding
                time.sleep(0.5)
                wdt.feed()
        else:
            time.sleep(2)  # Shorter delay after errors
            
    except OSError as e:
        print(f"I/O ERROR in main loop: {e}")
        error_count += 1
        if error_count >= max_errors:
            print("Too many I/O errors, resetting microcontroller...")
            time.sleep(1)
            microcontroller.reset()
        time.sleep(2)
    except Exception as e:
        print(f"ERROR in main loop: {e}")
        error_count += 1
        if error_count >= max_errors:
            print("Too many errors, resetting microcontroller...")
            time.sleep(1)
            microcontroller.reset()
        time.sleep(2)
