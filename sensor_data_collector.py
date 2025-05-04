#!/usr/bin/env python3
"""
SCD30 Sensor Data Collector for InfluxDB Cloud

This script reads CO2, temperature, and humidity data from an SCD30 sensor
connected to a Feather S2 board via I2C, and stores the data in InfluxDB Cloud.
"""

import os
import time
import logging
import serial
import json
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sensor_data.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Helper function to safely get and convert environment variables
def get_env_var(var_name, default=None, var_type=str):
    value = os.getenv(var_name, default)
    if value is None:
        return None
    
    # For debugging
    print(f"Raw {var_name}: '{value}'")
    
    try:
        if var_type is int:
            # Strip any whitespace and comments
            if isinstance(value, str):
                value = value.split('#')[0].strip()
            return int(value)
        elif var_type is float:
            if isinstance(value, str):
                value = value.split('#')[0].strip()
            return float(value)
        else:
            return value
    except (ValueError, TypeError) as e:
        logger.error(f"Error converting {var_name}: {e}")
        return default

# Global variables for configuration
INFLUXDB_URL = None
INFLUXDB_TOKEN = None
INFLUXDB_ORG = None
INFLUXDB_BUCKET = None
COM_PORT = None
MEASUREMENT_INTERVAL = 60
SENSOR_TYPE = "scd30"

def load_configuration():
    """Load configuration from environment variables"""
    global INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET, COM_PORT, MEASUREMENT_INTERVAL, SENSOR_TYPE
    
    # Load environment variables - force reload
    load_dotenv(override=True)
    
    # Get InfluxDB configuration
    INFLUXDB_URL = get_env_var("INFLUXDB_URL")
    INFLUXDB_TOKEN = get_env_var("INFLUXDB_TOKEN")
    INFLUXDB_ORG = get_env_var("INFLUXDB_ORG")
    INFLUXDB_BUCKET = get_env_var("INFLUXDB_BUCKET")
    COM_PORT = get_env_var("COM_PORT")
    MEASUREMENT_INTERVAL = get_env_var("MEASUREMENT_INTERVAL", 60, int)
    SENSOR_TYPE = get_env_var("SENSOR_TYPE", "scd30")  # Default to BME688 if not specified

class FeatherS2SensorReader:
    """Class to handle communication with the Feather S2 board and BME688 sensor."""
    
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
            
            # Clear any initial data in the buffer
            # self.serial_conn.reset_input_buffer()
            
            # # Exit the CircuitPython REPL if active by sending Ctrl+C
            # self.serial_conn.write(b'\x03\x03')  # Send Ctrl+C twice
            # time.sleep(0.5)
            
            # # Clear buffer again after Ctrl+C
            # if self.serial_conn.in_waiting:
            #     initial_data = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='replace')
            #     logger.info(f"Cleared initial data: '{initial_data}'")
            
            # # Send a newline to check if we get a response
            # self.serial_conn.write(b'\n')
            # time.sleep(0.5)
            
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
            # First, make sure we're not in the REPL
            # self.serial_conn.write(b'\x03')  # Send Ctrl+C to exit any running program
            # time.sleep(0.5)
            
            # # Clear any existing data in the buffer
            # self.serial_conn.reset_input_buffer()
            
            # # Send command to request sensor data
            # logger.info("Sending 'read' command to Feather S2")
            # self.serial_conn.write(b'read\n')
            
            # # Wait for response with a longer timeout
            # time.sleep(1.5)  # Increased timeout for more reliable response
            
            # Read all available data
            all_data = ""
            if self.serial_conn.in_waiting:
                all_data = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='replace')
                logger.info(f"Received data: '{all_data}'")
                
                # Look for JSON data in the response with JSON: prefix
                import re
                # First try to match the JSON: prefix format
                json_match = re.search(r'JSON:(\{.*?\})', all_data, re.DOTALL)
                
                # If that doesn't work, fall back to the generic JSON pattern
                if not json_match:
                    json_match = re.search(r'\{.*?\}', all_data, re.DOTALL)
                    logger.info("Falling back to generic JSON pattern search")
                
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
                                try:
                                    json_str = json_match.group(0)
                                    logger.info(f"Found JSON string: '{json_str}'")
                                    sensor_data = json.loads(json_str)
                                    logger.info(f"Parsed sensor data: {sensor_data}")
                                    return sensor_data
                                except json.JSONDecodeError as e:
                                    logger.error(f"Failed to parse JSON: {e}")
                            
            else:
                logger.warning("No data received from sensor. Check if the Feather S2 is responding.")
            
            # If we got here, we didn't get valid data
            return None
        except Exception as e:
            logger.error(f"Error reading sensor data: {e}")
            return None

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
        self.is_cloud = 'cloud' in url.lower() or not url.startswith('http://localhost')
        
    def connect(self):
        """Connect to InfluxDB with retry logic."""
        for attempt in range(1, self.max_retries + 1):
            try:
                # Initialize the InfluxDB client
                logger.info(f"Connecting to InfluxDB at {self.url} (Attempt {attempt}/{self.max_retries})...")
                self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
                self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
                
                # Verify connection by checking health
                health = self.client.health()
                logger.info(f"InfluxDB status: {health.status}, version: {health.version}")
                
                # Verify bucket exists
                buckets_api = self.client.buckets_api()
                buckets = buckets_api.find_buckets().buckets
                bucket_exists = False
                
                for bucket in buckets:
                    if bucket.name == self.bucket:
                        bucket_exists = True
                        logger.info(f"Bucket '{self.bucket}' exists")
                        break
                
                if not bucket_exists:
                    if self.is_cloud:
                        logger.error(f"Bucket '{self.bucket}' not found in InfluxDB Cloud. Please create it in the InfluxDB Cloud UI.")
                    else:
                        logger.error(f"Bucket '{self.bucket}' not found. Please create it first.")
                    return False
                
                logger.info(f"Successfully connected to InfluxDB at {self.url}")
                return True
                
            except ApiException as e:
                logger.error(f"InfluxDB API error (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Maximum retry attempts reached. Could not connect to InfluxDB.")
                    return False
                    
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error (attempt {attempt}/{self.max_retries}): {e}")
                if self.is_cloud:
                    logger.error("Could not connect to InfluxDB Cloud. Please check your internet connection.")
                else:
                    logger.error("Could not connect to local InfluxDB. Please check if the server is running.")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Maximum retry attempts reached. Could not connect to InfluxDB.")
                    return False
                    
            except Exception as e:
                logger.error(f"Failed to connect to InfluxDB (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Maximum retry attempts reached. Could not connect to InfluxDB.")
                    return False
    
    def write_data(self, data):
        """Write sensor data to InfluxDB with retry logic."""
        if not self.client or not self.write_api:
            logger.error("InfluxDB client is not initialized")
            return False
        
        for attempt in range(1, self.max_retries + 1):
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
                    logger.error(f"Invalid data format: {data}")
                    return False
                
                self.write_api.write(bucket=self.bucket, org=self.org, record=point)
                logger.info(f"Data written to InfluxDB: {data}")
                return True
                
            except ApiException as e:
                logger.error(f"InfluxDB API error during write (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying write in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Maximum retry attempts reached. Could not write data.")
                    return False
                    
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error during write (attempt {attempt}/{self.max_retries}): {e}")
                if self.is_cloud:
                    logger.error("Could not connect to InfluxDB Cloud. Please check your internet connection.")
                else:
                    logger.error("Could not connect to local InfluxDB. Please check if the server is running.")
                    
                if attempt < self.max_retries:
                    logger.info(f"Retrying write in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Maximum retry attempts reached. Could not write data.")
                    return False
                    
            except Exception as e:
                logger.error(f"Failed to write data (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying write in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Maximum retry attempts reached. Could not write data.")
                    return False
    
    def close(self):
        """Close the InfluxDB client."""
        if self.client:
            try:
                self.client.close()
                logger.info("InfluxDB client closed")
            except Exception as e:
                logger.error(f"Error closing InfluxDB client: {e}")

def main():
    """Main function to read sensor data and write to InfluxDB Cloud."""
    # Load configuration from environment variables
    load_configuration()
    
    # Check if required environment variables are set
    if not INFLUXDB_URL:
        logger.error("InfluxDB URL is not set. Please set the INFLUXDB_URL environment variable.")
        sys.exit(1)
        
    if not INFLUXDB_TOKEN:
        logger.error("InfluxDB token is not set. Please set the INFLUXDB_TOKEN environment variable.")
        sys.exit(1)
    
    if not INFLUXDB_ORG:
        logger.error("InfluxDB organization is not set. Please set the INFLUXDB_ORG environment variable.")
        sys.exit(1)
        
    if not INFLUXDB_BUCKET:
        logger.error("InfluxDB bucket is not set. Please set the INFLUXDB_BUCKET environment variable.")
        sys.exit(1)
        
    if not COM_PORT:
        logger.error("COM port is not set. Please set the COM_PORT environment variable.")
        sys.exit(1)
    
    # Initialize sensor reader
    sensor_reader = FeatherS2SensorReader(COM_PORT, sensor_type=SENSOR_TYPE)
    if not sensor_reader.connect():
        logger.error("Failed to connect to sensor. Exiting.")
        sys.exit(1)
    
    # Initialize InfluxDB writer with retry capabilities
    is_cloud = 'cloud' in INFLUXDB_URL.lower() or not INFLUXDB_URL.startswith('http://localhost')
    if is_cloud:
        logger.info("Connecting to InfluxDB Cloud...")
    else:
        logger.info("Connecting to local InfluxDB instance...")
        
    influxdb_writer = InfluxDBWriter(INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET, max_retries=3, retry_delay=5)
    if not influxdb_writer.connect():
        logger.error("Failed to connect to InfluxDB. Exiting.")
        sensor_reader.disconnect()
        sys.exit(1)
    
    logger.info(f"Starting data collection. Measurement interval: {MEASUREMENT_INTERVAL} seconds")
    
    # Track consecutive failures
    consecutive_failures = 0
    max_consecutive_failures = 5
    
    try:
        while True:
            try:
                # Read sensor data
                sensor_data = sensor_reader.read_sensor_data()
                
                if sensor_data:
                    # Write data to InfluxDB
                    success = influxdb_writer.write_data(sensor_data)
                    if success:
                        consecutive_failures = 0  # Reset failure counter on success
                    else:
                        consecutive_failures += 1
                        logger.warning(f"Failed to write data. Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
                else:
                    logger.warning("No sensor data received")
                    consecutive_failures += 1
                    logger.warning(f"Failed to get sensor data. Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
                
                # If too many consecutive failures, attempt to reconnect
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning("Too many consecutive failures. Attempting to reconnect...")
                    # Try to reconnect to the sensor
                    sensor_reader.disconnect()
                    time.sleep(2)
                    if sensor_reader.connect():
                        logger.info("Successfully reconnected to sensor")
                    else:
                        logger.error("Failed to reconnect to sensor")
                    
                    # Try to reconnect to InfluxDB
                    influxdb_writer.close()
                    time.sleep(2)
                    if influxdb_writer.connect():
                        logger.info("Successfully reconnected to InfluxDB")
                    else:
                        logger.error("Failed to reconnect to InfluxDB")
                    
                    consecutive_failures = 0  # Reset counter after reconnection attempt
                
                # Wait for the next measurement
                time.sleep(MEASUREMENT_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                consecutive_failures += 1
                logger.warning(f"Error in main loop. Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
                time.sleep(MEASUREMENT_INTERVAL)  # Still wait before next attempt
                
    except KeyboardInterrupt:
        logger.info("Data collection stopped by user")
    finally:
        # Clean up
        sensor_reader.disconnect()
        influxdb_writer.close()

if __name__ == "__main__":
    main()
