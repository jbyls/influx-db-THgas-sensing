"""
Updated SCD-30 CO2 sensor code for Feather S2
This code reads CO2, temperature, and humidity data from SCD-30 sensor and responds to 'read' commands with JSON data
Compatible with the specific SCD-30 library version on your board
"""
import time
import board
import busio
import json
import digitalio
import supervisor
import adafruit_scd30

# Set up the built-in LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# Flash LED to indicate code.py is starting
for _ in range(2):
    led.value = True
    time.sleep(0.2)
    led.value = False
    time.sleep(0.2)

# Initialize I2C
i2c = None
sensor = None

def setup_sensor():
    """Initialize the SCD-30 sensor"""
    global i2c, sensor
    try:
        # Initialize I2C
        i2c = busio.I2C(board.SCL, board.SDA)
        
        # Initialize SCD-30 sensor - default I2C address is 0x61
        sensor = adafruit_scd30.SCD30(i2c)
        
        # Configure sensor - check which methods are available
        if hasattr(sensor, 'measurement_interval'):
            sensor.measurement_interval = 2
        
        # Start measurements - handle different library versions
        if hasattr(sensor, 'start_periodic_measurement'):
            sensor.start_periodic_measurement()
        elif hasattr(sensor, 'start_continuous_measurement'):
            sensor.start_continuous_measurement()
        
        # Indicate success with LED
        led.value = True
        time.sleep(0.5)
        led.value = False
        
        return True
    except Exception as e:
        # Indicate error with rapid LED flashing
        for _ in range(5):
            led.value = True
            time.sleep(0.1)
            led.value = False
            time.sleep(0.1)
        print(f"Error initializing sensor: {e}")
        return False

def read_sensor():
    """Read data from SCD-30 sensor and return as dictionary"""
    try:
        if not sensor:
            return {"error": "Sensor not initialized"}
        
        # Check which attribute to use for data availability
        data_available_attr = 'data_available' if hasattr(sensor, 'data_available') else 'data_ready'
        
        # Wait for data to be available
        if not getattr(sensor, data_available_attr):
            # Wait up to 2 seconds for data
            timeout = 0
            while not getattr(sensor, data_available_attr) and timeout < 2:
                time.sleep(0.1)
                timeout += 0.1
                
            if not getattr(sensor, data_available_attr):
                return {"error": "No data available from sensor"}
        
        # Read sensor data - check which attributes are available
        if hasattr(sensor, 'CO2'):
            co2 = sensor.CO2
        elif hasattr(sensor, 'co2'):
            co2 = sensor.co2
        else:
            co2 = 0
            
        if hasattr(sensor, 'temperature'):
            temperature = sensor.temperature
        else:
            temperature = 0
            
        if hasattr(sensor, 'relative_humidity'):
            humidity = sensor.relative_humidity
        elif hasattr(sensor, 'humidity'):
            humidity = sensor.humidity
        else:
            humidity = 0
        
        # Blink LED to indicate successful reading
        led.value = True
        time.sleep(0.1)
        led.value = False
        
        # Return data as dictionary
        return {
            "co2": round(co2, 1),
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2)
        }
    except Exception as e:
        return {"error": str(e)}

# Initialize sensor
sensor_ready = setup_sensor()
if not sensor_ready:
    print("Failed to initialize sensor. Check connections and try again.")

# Main loop
while True:
    try:
        # Check for incoming serial data
        if supervisor.runtime.serial_bytes_available:
            command = input().strip()
            
            # Process commands
            if command == "read":
                if sensor_ready:
                    data = read_sensor()
                    print(json.dumps(data))
                else:
                    # Try to initialize sensor again
                    sensor_ready = setup_sensor()
                    if sensor_ready:
                        data = read_sensor()
                        print(json.dumps(data))
                    else:
                        print(json.dumps({"error": "Sensor not available"}))
            elif command == "status":
                print(json.dumps({"status": "running", "sensor_ready": sensor_ready}))
        
        # Short delay to prevent tight loop
        time.sleep(0.1)
        
    except Exception as e:
        print(json.dumps({"error": f"Exception in main loop: {str(e)}"}))
        time.sleep(1)  # Delay to prevent rapid error messages
