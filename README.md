# BME688 Sensor Data Collection and Visualization

This project uses a Feather S2 board to read temperature, humidity, pressure, and VOC gas concentration data from a BME688 sensor via I2C. The data is stored in InfluxDB at 1-minute intervals and visualized using a Grafana dashboard.

## Components

- **Hardware**: Adafruit Feather S2 board, BME688 sensor module
- **Database**: InfluxDB for time-series data storage
- **Visualization**: Grafana dashboard

## Setup Instructions

1. Connect the BME688 sensor to the Feather S2 board via I2C
2. Install required Python dependencies: `pip install -r requirements.txt`
3. Configure InfluxDB credentials in the `.env` file
4. Run the data collection script: `python sensor_data_collector.py`
5. Import the Grafana dashboard configuration

## Project Structure

- `sensor_data_collector.py`: Main script for reading sensor data and sending to InfluxDB
- `requirements.txt`: Python dependencies
- `grafana/dashboard.json`: Grafana dashboard configuration
- `.env.example`: Example environment variables file (copy to `.env` and update)