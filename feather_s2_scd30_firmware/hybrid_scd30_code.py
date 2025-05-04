"""
Hybrid SCD-30 CO2 sensor code for Feather S2
This code continuously outputs data AND responds to 'read' commands with JSON data
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

print("Starting SCD-30 sensor code...")

# Initialize I2C
i2c = None
sensor = None

def setup_sensor():
    """Initialize the SCD-30 sensor"""
    global i2c, sensor
    try:
        # Initialize I2C
        i2c = busio.I2C(board.SCL, board.SDA)
        
        # Scan for I2C devices
        print("Scanning for I2C devices...")
        i2c.try_lock()
        for address in i2c.scan():
            print(f"Found device at address: 0x{address:02x}")
        i2c.unlock()
        
        # Initialize SCD-30 sensor - default I2C address is 0x61
        print("Initializing SCD-30 sensor...")
        sensor = adafruit_scd30.SCD30(i2c)
        
        # Configure sensor - check which methods are available
        print("Available methods:", dir(sensor))
        if hasattr(sensor, 'measurement_interval'):
            sensor.measurement_interval = 2
            print("Set measurement interval to 2 seconds")
        
        # Start measurements - handle different library versions
        if hasattr(sensor, 'start_periodic_measurement'):
            sensor.start_periodic_measurement()
            print("Started periodic measurement")
        elif hasattr(sensor, 'start_continuous_measurement'):
            sensor.start_continuous_measurement()
            print("Started continuous measurement")
        
        # Indicate success with LED
        led.value = True
        time.sleep(0.5)
        led.value = False
        
        print("SCD-30 sensor initialized successfully")
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
print("Setting up SCD-30 sensor...")
sensor_ready = setup_sensor()
if not sensor_ready:
    print("Failed to initialize sensor. Check connections and try again.")

# Variables for timing
last_reading_time = time.monotonic()
reading_interval = 2  # seconds

# Main loop
print("Starting main loop - will output data every 2 seconds and respond to 'read' commands")
while True:
    try:
        # Check for incoming serial data
        if supervisor.runtime.serial_bytes_available:
            command = input().strip()
            
            # Process commands
            if command == "read":
                if sensor_ready:
                    data = read_sensor()
                    json_data = json.dumps(data)
                    print(f"JSON:{json_data}")
                else:
                    # Try to initialize sensor again
                    sensor_ready = setup_sensor()
                    if sensor_ready:
                        data = read_sensor()
                        json_data = json.dumps(data)
                        print(f"JSON:{json_data}")
                    else:
                        print(json.dumps({"error": "Sensor not available"}))
            elif command == "status":
                print(json.dumps({"status": "running", "sensor_ready": sensor_ready}))
        
        # Periodically output sensor data regardless of commands
        current_time = time.monotonic()
        if current_time - last_reading_time >= reading_interval:
            if sensor_ready:
                data = read_sensor()
                if "error" not in data:
                    print(f"CO2: {data['co2']} ppm, Temp: {data['temperature']} °C, RH: {data['humidity']} %")
                    # Also output in JSON format for the collector
                    json_data = json.dumps(data)
                    print(f"JSON:{json_data}")
                else:
                    print(f"Error reading sensor: {data['error']}")
            last_reading_time = current_time
        
        # Short delay to prevent tight loop
        time.sleep(0.1)
        
    except Exception as e:
        print(f"Exception in main loop: {e}")
        time.sleep(1)  # Delay to prevent rapid error messages
