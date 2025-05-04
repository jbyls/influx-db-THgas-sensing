#!/usr/bin/env python3
"""
Test script to verify InfluxDB Cloud connection and write a test data point
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Set up file logging
log_file = open('influxdb_cloud_test_log.txt', 'w')

def log(message):
    """Write message to both stdout and log file"""
    print(message)
    log_file.write(message + '\n')
    log_file.flush()

# Load environment variables - force reload
load_dotenv(override=True)

# Get InfluxDB configuration from environment variables
INFLUXDB_URL = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET")

log(f"InfluxDB Cloud URL: {INFLUXDB_URL}")
log(f"InfluxDB Organization: {INFLUXDB_ORG}")
log(f"InfluxDB Bucket: {INFLUXDB_BUCKET}")
log(f"InfluxDB Token: {INFLUXDB_TOKEN[:10]}...{INFLUXDB_TOKEN[-5:] if len(INFLUXDB_TOKEN) > 15 else '***'}")

# Create test data
test_data = {
    "temperature": 22.3,
    "humidity": 45.7,
    "pressure": 1013.2,
    "gas_resistance": 12345,
    "voc": 1.5
}

try:
    # Initialize InfluxDB client
    log("\nConnecting to InfluxDB Cloud...")
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    query_api = client.query_api()
    
    # 1. Check InfluxDB health
    log("\nChecking InfluxDB Cloud health...")
    health = client.health()
    log(f"InfluxDB status: {health.status}")
    log(f"InfluxDB version: {health.version}")
    
    # 2. Check bucket existence
    log("\nChecking if bucket exists...")
    buckets_api = client.buckets_api()
    buckets = buckets_api.find_buckets().buckets
    bucket_exists = False
    
    for bucket in buckets:
        if bucket.name == INFLUXDB_BUCKET:
            bucket_exists = True
            log(f"Bucket '{INFLUXDB_BUCKET}' exists")
            break
    
    if not bucket_exists:
        log(f"Bucket '{INFLUXDB_BUCKET}' not found. Please create it in the InfluxDB Cloud UI.")
        sys.exit(1)
    
    # 3. Write test data using the InfluxDB client
    log("\nWriting test data point to InfluxDB Cloud...")
    point = Point("bme688_sensor").tag("device", "test_script") \
        .field("temperature", test_data["temperature"]) \
        .field("humidity", test_data["humidity"]) \
        .field("pressure", test_data["pressure"]) \
        .field("gas_resistance", test_data["gas_resistance"]) \
        .field("voc", test_data["voc"]) \
        .time(datetime.utcnow())

    try:
        write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
        log("Data written successfully to InfluxDB Cloud!")
    except Exception as e:
        log(f"Write operation failed: {e}")
        log("This may indicate that your token lacks write permissions.")
        sys.exit(1)

    # 4. Query data to verify it was written
    log("\nQuerying data to verify it was written...")
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "bme688_sensor")
      |> filter(fn: (r) => r.device == "test_script")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> limit(n: 10)
    '''
    
    try:
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        
        if result:
            log("Query successful! Results:")
            for table in result:
                for record in table.records:
                    time = record.get_time()
                    
                    # Check if we're dealing with pivoted data
                    if "temperature" in record.values:
                        # Pivoted data
                        temperature = record.values.get("temperature", "N/A")
                        humidity = record.values.get("humidity", "N/A")
                        pressure = record.values.get("pressure", "N/A")
                        gas_resistance = record.values.get("gas_resistance", "N/A")
                        voc = record.values.get("voc", "N/A")
                        log(f"Time: {time} - Temperature: {temperature}, Humidity: {humidity}, Pressure: {pressure}, Gas Resistance: {gas_resistance}, VOC: {voc}")
                    else:
                        # Non-pivoted data
                        field = record.get_field()
                        value = record.get_value()
                        log(f"Time: {time} - Field: {field}, Value: {value}")
        else:
            log("No data found in query result. This may be due to timing - try again in a few seconds.")
    except Exception as e:
        log(f"Query operation failed: {e}")
        log("This may indicate that your token lacks read permissions.")
    
    log("\nTest completed! If you see data in the results above, your InfluxDB Cloud setup is working correctly.")
    client.close()

except Exception as e:
    log(f"\nError: {e}")
    log("\nTroubleshooting tips:")
    log("1. Make sure your InfluxDB Cloud URL is correct")
    log("2. Check that your token is valid and has not expired")
    log("3. Verify your organization name is correct")
    log("4. Ensure your bucket exists in your InfluxDB Cloud instance")
    log("5. Check your internet connection")
    log_file.close()
    sys.exit(1)
finally:
    # Make sure to close the log file
    log_file.close()
