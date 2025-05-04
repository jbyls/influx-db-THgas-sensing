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

# Import the SCD30 library
try:
    import adafruit_scd30
except ImportError:
    print("ERROR: adafruit_scd30 library not found!")
    print("Please install it using the CircuitPython Library Manager")
    while True:
        pass

# Configure auto-reload to be on
supervisor.runtime.autoreload = True

# Setup I2C connection
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize SCD30 sensor
try:
    scd = adafruit_scd30.SCD30(i2c)
    print("SCD30 sensor initialized successfully")
except Exception as e:
    print(f"ERROR initializing SCD30: {e}")
    while True:
        pass

# Set measurement interval (2 seconds)
scd.measurement_interval = 2

# Function to read sensor data
def read_sensor():
    """Read data from SCD30 sensor and print it."""
    # Wait for sensor data to be available
    timeout = 0
    max_timeout = 10  # Maximum wait time in seconds
    
    while not scd.data_available and timeout < max_timeout:
        print("Waiting for sensor data...")
        time.sleep(1)
        timeout += 1
    
    if not scd.data_available:
        print("ERROR: No data available from SCD30 after timeout")
        return False
    
    try:
        # Read the sensor data
        co2 = scd.CO2
        temperature = scd.temperature
        humidity = scd.relative_humidity
        
        # Print in human-readable format
        print(f"CO2: {co2:.1f} ppm, Temp: {temperature:.2f} °C, RH: {humidity:.2f} %")
        
        # Print in JSON format for easy parsing
        data = {
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "co2": round(co2, 1)
        }
        print(f"JSON:{json.dumps(data)}")
        
        return True
    except Exception as e:
        print(f"ERROR reading sensor: {e}")
        return False

# Main loop
print("Starting SCD30 sensor readings...")
print("Press Ctrl+C to exit")

while True:
    try:
        success = read_sensor()
        if not success:
            print("Failed to read sensor, resetting...")
            time.sleep(5)
            microcontroller.reset()  # Reset the microcontroller if reading fails
        
        # Wait before next reading
        time.sleep(3)
    except Exception as e:
        print(f"ERROR in main loop: {e}")
        time.sleep(5)
