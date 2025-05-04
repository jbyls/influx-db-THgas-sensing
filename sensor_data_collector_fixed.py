import os
import time
import json
import logging
import serial
import re
from datetime import datetime
import requests
import backoff
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('sensor_data.log')
    ]
)
logger = logging.getLogger(__name__)

def get_env_var(var_name, default=None, var_type=str):
    """Get environment variable with optional default value and type conversion."""
    value = os.getenv(var_name)
    if value is None:
        if default is None:
            raise ValueError(f"Environment variable {var_name} is not set and no default provided")
        return default
    
    if var_type == bool:
        return value.lower() in ('true', 'yes', '1', 't', 'y')
    
    return var_type(value)

def main():
    """Main function to run the sensor data collector."""
    # Load environment variables - force reload
    load_dotenv(override=True)
    
    # Get InfluxDB configuration
    INFLUXDB_URL = get_env_var("INFLUXDB_URL")
    INFLUXDB_TOKEN = get_env_var("INFLUXDB_TOKEN")
    INFLUXDB_ORG = get_env_var("INFLUXDB_ORG")
    INFLUXDB_BUCKET = get_env_var("INFLUXDB_BUCKET")
    COM_PORT = get_env_var("COM_PORT")
    MEASUREMENT_INTERVAL = get_env_var("MEASUREMENT_INTERVAL", 60, int)
    SENSOR_TYPE = get_env_var("SENSOR_TYPE", "scd30")  # Default to SCD30

class FeatherS2SensorReader:
    """Class to handle communication with the Feather S2 board and sensor."""
    
    def __init__(self, com_port, baud_rate=115200, sensor_type="scd30"):
        """Initialize the Feather S2 reader."""
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.serial_conn = None
        self.sensor_type = sensor_type  # "bme688" or "scd30"
        
    def connect(self):
        """Establish a serial connection to the Feather S2 board."""
        try:
            self.serial_conn = serial.Serial(self.com_port, self.baud_rate, timeout=2)
            logger.info(f"Connected to {self.com_port} at {self.baud_rate} baud")
            
            # Allow time for the serial connection to initialize
            time.sleep(2)
            
            # Clear any pending data in the buffer
            if self.serial_conn.in_waiting:
                self.serial_conn.reset_input_buffer()
                
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.com_port}: {e}")
            return False
    
    def disconnect(self):
        """Close the serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info(f"Disconnected from {self.com_port}")
    
    def read_sensor_data(self):
        """Read sensor data from the Feather S2 board."""
        if not self.serial_conn or not self.serial_conn.is_open:
            logger.error("Serial connection is not open")
            return None
        
        try:
            # Check if there's any data available
            timeout_counter = 0
            max_timeout = 10  # Maximum wait time in seconds
            
            # Wait for data to be available with timeout
            while self.serial_conn.in_waiting == 0 and timeout_counter < max_timeout:
                time.sleep(0.5)
                timeout_counter += 0.5
                
            if self.serial_conn.in_waiting == 0:
                logger.warning("No data received from sensor within timeout period")
                return None
            
            # Read all available data
            try:
                all_data = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='replace')
                logger.info(f"Received data: '{all_data}'")
            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                self.disconnect()
                time.sleep(1)
                self.connect()  # Try to reconnect
                return None
            except Exception as e:
                logger.error(f"Error reading serial data: {e}")
                return None
                
            # Check for I/O errors in the data
            if "I/O ERROR" in all_data or "[Errno 5] Input/output error" in all_data:
                logger.warning("I/O error detected in sensor output, waiting for device to recover")
                time.sleep(2)  # Give the device time to reset or recover
                return None
                
            # Look for JSON data in the response with JSON: prefix
            # First try to match the JSON: prefix format
            json_match = re.search(r'JSON:(\{.*?\})', all_data, re.DOTALL)
            
            # If that doesn't work, fall back to the generic JSON pattern
            if not json_match:
                logger.info("Falling back to generic JSON pattern search")
                json_match = re.search(r'\{.*?\}', all_data, re.DOTALL)
                
            if json_match:
                # If we matched the JSON: prefix pattern, use group(1) to get just the JSON part
                # If we matched the generic pattern, use group(0) to get the whole match
                if 'JSON:' in all_data and json_match.re.pattern.startswith('JSON:'):
                    json_str = json_match.group(1)
                else:
                    json_str = json_match.group(0)
                logger.info(f"Found JSON string: '{json_str}'")
                
                try:
                    # Parse JSON response
                    sensor_data = json.loads(json_str)
                    logger.info(f"Parsed sensor data: {sensor_data}")
                    return sensor_data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse extracted JSON: {e}")
            else:
                logger.warning("No JSON data found in response")
                
                # If we received 'read' echoed back, we might be in the REPL
                if 'read' in all_data:
                    logger.warning("CircuitPython REPL detected. Trying to read sensor directly via REPL...")
                    
                    # Try to read sensor data directly through REPL commands
                    self.serial_conn.reset_input_buffer()
                    
                    # Send individual commands with proper line endings based on sensor type
                    # The REPL needs proper line endings to execute commands
                    if self.sensor_type == "bme688":
                        commands = [
                            "import board",
                            "import busio", 
                            "import adafruit_bme680", 
                            "i2c = busio.I2C(board.SCL, board.SDA)", 
                            "bme = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77)",
                            "print(f'TEMP:{bme.temperature:.2f}')",
                            "print(f'HUM:{bme.relative_humidity:.2f}')",
                            "print(f'PRES:{bme.pressure/100.0:.2f}')",
                            "print(f'GAS:{bme.gas:.2f}')"
                        ]
                    elif self.sensor_type == "scd30":
                        commands = [
                            "import board",
                            "import busio", 
                            "import adafruit_scd30", 
                            "i2c = busio.I2C(board.SCL, board.SDA)", 
                            "try:",
                            "    scd = adafruit_scd30.SCD30(i2c)",
                            "    print('SCD30 initialized successfully')",
                            "    # Force a measurement",
                            "    scd.start_periodic_measurement()",
                            "    import time",
                            "    print('Waiting for measurement...')",
                            "    # Wait longer for SCD30 to have data available",
                            "    for i in range(10):",
                            "        if scd.data_available:",
                            "            break",
                            "        print(f'Waiting {i+1}/10')",
                            "        time.sleep(1)",
                            "    if scd.data_available:",
                            "        co2 = scd.CO2",
                            "        temp = scd.temperature",
                            "        hum = scd.relative_humidity",
                            "        print(f'CO2:{co2:.1f}')",
                            "        print(f'TEMP:{temp:.2f}')",
                            "        print(f'HUM:{hum:.2f}')",
                            "    else:",
                            "        print('No data available from SCD-30 after waiting')",
                            "except Exception as e:",
                            "    print(f'Error initializing SCD30: {e}')"
                        ]
                    
                    # Clear any existing data
                    self.serial_conn.reset_input_buffer()
                    
                    # Send each command with proper line endings
                    for cmd in commands:
                        self.serial_conn.write(f"{cmd}\r\n".encode())
                        time.sleep(0.5)  # Wait for command to execute
                        
                        # Read any response to keep the buffer clear
                        if self.serial_conn.in_waiting:
                            response = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='replace')
                            logger.debug(f"Command response: {response}")
                    
                    # Wait for all commands to complete
                    time.sleep(5)  # Give it more time to execute all commands for SCD30
                    
                    # Read the final response
                    response_data = ""
                    if self.serial_conn.in_waiting:
                        response_data = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='replace')
                        logger.info(f"REPL response: {response_data}")
                        
                        # Parse the response based on sensor type
                        sensor_data = {}
                        
                        if self.sensor_type == "bme688":
                            # Extract temperature, humidity, pressure, and gas readings
                            temp_match = re.search(r'TEMP:([0-9.]+)', response_data)
                            hum_match = re.search(r'HUM:([0-9.]+)', response_data)
                            pres_match = re.search(r'PRES:([0-9.]+)', response_data)
                            gas_match = re.search(r'GAS:([0-9.]+)', response_data)
                            
                            if temp_match and hum_match and pres_match and gas_match:
                                try:
                                    temperature = float(temp_match.group(1))
                                    humidity = float(hum_match.group(1))
                                    pressure = float(pres_match.group(1))
                                    gas_resistance = float(gas_match.group(1))
                                    
                                    # Calculate VOC index (simplified)
                                    # This is a very basic approximation
                                    voc = max(1.0, min(5.0, gas_resistance / 50000.0))
                                    
                                    sensor_data = {
                                        "temperature": temperature,
                                        "humidity": humidity,
                                        "pressure": pressure,
                                        "gas_resistance": gas_resistance,
                                        "voc": voc
                                    }
                                    logger.info(f"Parsed BME688 data: {sensor_data}")
                                    return sensor_data
                                except ValueError as e:
                                    logger.error(f"Failed to convert BME688 values: {e}")
                            else:
                                logger.error("Could not find all BME688 readings in response")
                                
                        elif self.sensor_type == "scd30":
                            # Extract CO2, temperature, and humidity readings
                            co2_match = re.search(r'CO2:([0-9.]+)', response_data)
                            temp_match = re.search(r'TEMP:([0-9.]+)', response_data)
                            hum_match = re.search(r'HUM:([0-9.]+)', response_data)
                            
                            # Log all matches for debugging
                            logger.info(f"CO2 match: {co2_match.group(1) if co2_match else 'None'}")
                            logger.info(f"TEMP match: {temp_match.group(1) if temp_match else 'None'}")
                            logger.info(f"HUM match: {hum_match.group(1) if hum_match else 'None'}")
                            
                            # Check for initialization messages
                            init_success = 'SCD30 initialized successfully' in response_data
                            waiting_msgs = re.findall(r'Waiting ([0-9]+)/10', response_data)
                            no_data_msg = 'No data available from SCD-30' in response_data
                            error_msg = re.search(r'Error initializing SCD30: (.*)', response_data)
                            
                            if error_msg:
                                logger.error(f"SCD30 initialization error: {error_msg.group(1)}")
                            elif no_data_msg:
                                logger.warning("SCD30 reported no data available")
                            elif init_success:
                                logger.info("SCD30 initialized successfully")
                                if waiting_msgs:
                                    logger.info(f"Waited {len(waiting_msgs)} cycles for data")
                            
                            if co2_match and temp_match and hum_match:
                                try:
                                    co2 = float(co2_match.group(1))
                                    temperature = float(temp_match.group(1))
                                    humidity = float(hum_match.group(1))
                                    
                                    sensor_data = {
                                        "co2": co2,
                                        "temperature": temperature,
                                        "humidity": humidity
                                    }
                                    logger.info(f"Parsed SCD30 data: {sensor_data}")
                                    return sensor_data
                                except ValueError as e:
                                    logger.error(f"Failed to convert SCD30 values: {e}")
                            else:
                                logger.error("Could not find all SCD30 readings in response")
                                
                                # Try to extract any partial data
                                if co2_match or temp_match or hum_match:
                                    partial_data = {}
                                    if co2_match:
                                        try:
                                            partial_data["co2"] = float(co2_match.group(1))
                                        except ValueError:
                                            pass
                                    if temp_match:
                                        try:
                                            partial_data["temperature"] = float(temp_match.group(1))
                                        except ValueError:
                                            pass
                                    if hum_match:
                                        try:
                                            partial_data["humidity"] = float(hum_match.group(1))
                                        except ValueError:
                                            pass
                                    
                                    if partial_data and len(partial_data) >= 2:  # At least 2 valid readings
                                        logger.warning(f"Using partial SCD30 data: {partial_data}")
                                        return partial_data
                            
                            # If no JSON with prefix found, try the original JSON pattern
                            json_match = re.search(r'\{.*?\}', response_data, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(0)
                                logger.info(f"Found JSON string in REPL response: '{json_str}'")
                                
                                try:
                                    # Parse JSON response
                                    sensor_data = json.loads(json_str)
                                    logger.info(f"Parsed sensor data from REPL: {sensor_data}")
                                    return sensor_data
                                except json.JSONDecodeError as e:
                                    logger.error(f"Failed to parse JSON from REPL: {e}")
                else:
                    logger.warning("No data received from sensor. Check if the Feather S2 is responding.")
                
                # If we got here, we didn't get valid data
                return None
                
        except serial.SerialException as e:
            logger.error(f"Serial communication error: {e}")
            self.disconnect()
            # Wait a moment before returning
            time.sleep(1)
            return None
        except Exception as e:
            logger.error(f"Error reading sensor data: {e}")
            return None
        finally:
            # We don't want to disconnect here anymore since we're using continuous reading
            pass

class InfluxDBWriter:
    """Class to handle writing data to InfluxDB or InfluxDB Cloud."""
    
    def __init__(self, url, token, org, bucket, max_retries=3, retry_delay=5):
        """Initialize the InfluxDB client."""
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = None
        self.write_api = None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def connect(self):
        """Connect to InfluxDB."""
        try:
            logger.info(f"Connecting to InfluxDB at {self.url}")
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            
            # Verify connection by checking health
            health = self.client.health()
            logger.info(f"InfluxDB health check: {health.status}")
            
            # Check if we can write to the bucket
            try:
                # Create a test point
                test_point = Point("connection_test").tag("test", "true").field("value", 1)
                
                # Write the test point
                self.write_api.write(bucket=self.bucket, record=test_point)
                logger.info(f"Successfully wrote test point to bucket '{self.bucket}'")
                
                return True
            except Exception as e:
                logger.error(f"Failed to write test point to bucket '{self.bucket}': {e}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from InfluxDB."""
        if self.client:
            self.client.close()
            self.client = None
            self.write_api = None
            logger.info("Disconnected from InfluxDB")
    
    @backoff.on_exception(backoff.expo, 
                         (requests.exceptions.ConnectionError, 
                          requests.exceptions.Timeout), 
                         max_tries=3)
    def write_data(self, data):
        """Write sensor data to InfluxDB."""
        if not self.client or not self.write_api:
            logger.error("InfluxDB client is not initialized")
            return False

        try:
            # Create a data point based on sensor type
            if data.get("temperature") and data.get("humidity") and data.get("pressure") and data.get("gas_resistance") and data.get("voc"):
                point = Point("bme688_sensor") \
                    .tag("device", "feather_s2") \
                    .field("temperature", data["temperature"]) \
                    .field("humidity", data["humidity"]) \
                    .field("pressure", data["pressure"]) \
                    .field("gas_resistance", data["gas_resistance"]) \
                    .field("voc", data["voc"]) \
                    .time(datetime.utcnow())
            elif data.get("co2") and data.get("temperature") and data.get("humidity"):
                point = Point("scd30_sensor") \
                    .tag("device", "feather_s2") \
                    .field("co2", data["co2"]) \
                    .field("temperature", data["temperature"]) \
                    .field("humidity", data["humidity"]) \
                    .time(datetime.utcnow())
            else:
                logger.error(f"Unknown data format: {data}")
                return False

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.info(f"Data written to InfluxDB: {data}")
            return True
        except Exception as e:
            logger.error(f"Failed to write data to InfluxDB: {e}")
            return False

def main():
    """Main function to run the sensor data collector."""
    # Load environment variables - force reload
    load_dotenv(override=True)
    
    # Get InfluxDB configuration
    INFLUXDB_URL = get_env_var("INFLUXDB_URL")
    INFLUXDB_TOKEN = get_env_var("INFLUXDB_TOKEN")
    INFLUXDB_ORG = get_env_var("INFLUXDB_ORG")
    INFLUXDB_BUCKET = get_env_var("INFLUXDB_BUCKET")
    COM_PORT = get_env_var("COM_PORT")
    MEASUREMENT_INTERVAL = get_env_var("MEASUREMENT_INTERVAL", 60, int)
    SENSOR_TYPE = get_env_var("SENSOR_TYPE", "scd30")  # Default to SCD30

    # Initialize InfluxDB writer
    influxdb_writer = InfluxDBWriter(INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET)
    
    # Initialize Feather S2 sensor reader
    sensor_reader = FeatherS2SensorReader(COM_PORT, sensor_type=SENSOR_TYPE)
    
    # Connect to InfluxDB
    if not influxdb_writer.connect():
        logger.error("Failed to connect to InfluxDB. Exiting.")
        return
    
    # Main loop
    try:
        consecutive_failures = 0
        max_consecutive_failures = 5
        serial_reconnect_count = 0
        max_serial_reconnects = 3
        
        # Connect to the sensor initially
        if not sensor_reader.connect():
            logger.error("Failed to connect to the sensor initially. Retrying...")
            time.sleep(5)
            if not sensor_reader.connect():
                logger.error("Failed to connect to the sensor again. Please check connections.")
                return
        
        while True:
            # Read sensor data
            sensor_data = sensor_reader.read_sensor_data()
            
            if not sensor_data:
                logger.warning("No sensor data received")
                consecutive_failures += 1
                logger.warning(f"Failed to get sensor data. Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
                
                if consecutive_failures >= max_consecutive_failures:
                    logger.error("Too many consecutive failures. Reconnecting...")
                    
                    # Try to reconnect to the serial port
                    sensor_reader.disconnect()
                    time.sleep(2)
                    
                    if not sensor_reader.connect():
                        serial_reconnect_count += 1
                        logger.error(f"Failed to reconnect to serial port. Attempt {serial_reconnect_count}/{max_serial_reconnects}")
                        
                        if serial_reconnect_count >= max_serial_reconnects:
                            logger.error("Maximum serial reconnection attempts reached. Reconnecting to InfluxDB and resetting counters...")
                            influxdb_writer.disconnect()
                            time.sleep(2)
                            influxdb_writer.connect()
                            serial_reconnect_count = 0
                    else:
                        logger.info("Successfully reconnected to serial port")
                        serial_reconnect_count = 0
                    
                    consecutive_failures = 0
            else:
                # Reset consecutive failures counter
                consecutive_failures = 0
                serial_reconnect_count = 0
                
                # Write data to InfluxDB
                if not influxdb_writer.write_data(sensor_data):
                    logger.error("Failed to write data to InfluxDB")
                    # Try to reconnect to InfluxDB
                    influxdb_writer.disconnect()
                    time.sleep(2)
                    influxdb_writer.connect()
            
            # Wait for the next measurement (with shorter interval if there was an error)
            if consecutive_failures > 0:
                # Use a shorter interval when having problems to recover faster
                time.sleep(min(MEASUREMENT_INTERVAL, 10))
            else:
                time.sleep(MEASUREMENT_INTERVAL)
                
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Exiting...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Clean up
        sensor_reader.disconnect()
        influxdb_writer.disconnect()
        logger.info("Sensor data collector stopped")

if __name__ == "__main__":
    main()
