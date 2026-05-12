# MySensorTools

A collection of tools for robot sensor fault diagnosis, data analysis, log interpretation, data parsing, and visualization, covering **Lidar**, **Stereo Camera**, **Infrared**, **UWB**, and **IMU** sensors.

## 📦 Project Structure

```
MySensorTools/
├── common/          # Shared utilities (log parsing, base classes, visualization helpers)
├── lidar/           # LiDAR sensor tools
├── stereo/          # Stereo camera sensor tools
├── infrared/        # Infrared sensor tools
├── uwb/             # Ultra-Wideband (UWB) positioning sensor tools
├── imu/             # Inertial Measurement Unit (IMU) tools
├── tests/           # Unit tests for all modules
├── requirements.txt
└── setup.py
```

## 🛠 Features

| Module     | Data Parser | Fault Diagnosis | Visualization |
|------------|:-----------:|:---------------:|:-------------:|
| LiDAR      | ✅          | ✅              | ✅            |
| Stereo     | ✅          | ✅              | ✅            |
| Infrared   | ✅          | ✅              | ✅            |
| UWB        | ✅          | ✅              | ✅            |
| IMU        | ✅          | ✅              | ✅            |

## 🚀 Quick Start

### Installation

```bash
pip install -e .
# or install only runtime dependencies
pip install -r requirements.txt
```

### IMU Example

```python
from imu.data_parser import IMUDataParser
from imu.diagnosis import IMUDiagnoser

parser = IMUDataParser()
records = parser.parse_csv("imu_log.csv")

diagnoser = IMUDiagnoser()
faults = diagnoser.diagnose(records)
for fault in faults:
    print(fault)
```

### LiDAR Example

```python
from lidar.data_parser import LidarDataParser
from lidar.diagnosis import LidarDiagnoser
from lidar.visualization import plot_point_cloud

parser = LidarDataParser()
frames = parser.parse_pcd("scan.pcd")

diagnoser = LidarDiagnoser()
faults = diagnoser.diagnose(frames[0])
plot_point_cloud(frames[0])
```

### Log Parsing Example

```python
from common.log_parser import SensorLogParser

log_parser = SensorLogParser()
entries = log_parser.parse_file("sensor.log")
errors = log_parser.filter_by_level(entries, "ERROR")
```

## 🧪 Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## 📋 Supported Sensor Formats

| Sensor   | Formats                                       |
|----------|-----------------------------------------------|
| LiDAR    | PCD, CSV (x,y,z,intensity)                    |
| Stereo   | CSV (disparity / depth)                       |
| Infrared | CSV (temperature matrix)                      |
| UWB      | CSV (timestamp, tag_id, x, y, z)              |
| IMU      | CSV (acc_x/y/z, gyro_x/y/z, roll/pitch/yaw)  |

## 📄 License

MIT
