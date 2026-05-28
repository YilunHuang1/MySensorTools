# Sensor Tools Guide

## Layout

| Directory | Purpose |
| --- | --- |
| `uwb/smoke_test` | UWB firmware smoke tests in standalone serial mode and online ROS2 mode. |
| `uwb/truth_value_analysis` | Batch MCAP truth-value accuracy analysis for distance and angle. |
| `uwb/vendor_compare` | Feirui vs Quanji static/dynamic UWB CSV comparison. |
| `uwb/mcap_tools` | UWB MCAP to CSV and visualization helpers. |
| `uwb/visualization` | Consolidated UWB CSV trajectory plotting. |
| `uwb/ble_tools` | UWB BLE peripheral and serial command tools. |
| `lidar/packets_parse` | Vanjee WLR-722Z packet decoding and PCD extraction. |
| `lidar/realtime_check` | Runtime LiDAR topic and packet health checks. |
| `camera/distortion` | Stereo distortion, intrinsic, and motion blur tools. |
| `camera/isp_json` | ISP JSON comparison and SC230AI tuning examples. |
| `camera/eeprom` | EEPROM hex dump parser. |
| `imu/mcap_analysis` | IMU MCAP fault and anomaly analysis. |
| `imu/vibration` | IMU vibration comparison script. |
| `infrared/raw_tools` | Infrared RAW/YUYV image conversion helpers. |
| `infrared/driver_reference` | Infrared camera driver reference source snippets. |
| `common` | Cross-sensor utilities such as MCAP log extraction. |
| `docs/codex_sensor_skills` | Codex sensor triage skills and code maps. |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Some tools need robot-side ROS2 packages and should be run on the robot or in a sourced ROS2 environment.

## Common Commands

UWB smoke test:

```bash
cd uwb/smoke_test
python3 uwb_smoke_test.py --mode standalone --serial-port /dev/ttyS7
python3 uwb_smoke_test.py --mode online --ranging-duration 15
```

UWB truth-value analysis:

```bash
cd uwb/truth_value_analysis
python3 uwb_analysis_pipeline.py --self-test
python3 uwb_analysis_pipeline.py -s /path/to/mcap_dir --recursive
```

UWB vendor comparison:

```bash
cd uwb/vendor_compare
python3 main_analysis.py --data-dir /path/to/dataset --output-dir analysis_results
```

UWB CSV plotting:

```bash
python3 uwb/visualization/plot_uwb_csv.py /path/to/uwb.csv --mode 2d -o uwb_xy.png
python3 uwb/visualization/plot_uwb_csv.py /path/to/uwb.csv --mode 3d -o uwb_xyz.png
```

LiDAR PCD extraction:

```bash
cd lidar/packets_parse
python3 scripts/extract.py --mcap /path/to/file.mcap --output pcd_output --max-frames 100
python3 analyze_pcd_quality.py
```

LiDAR realtime check:

```bash
python3 lidar/realtime_check/lidar_realtime_check.py --help
```

Camera EEPROM parse:

```bash
python3 camera/eeprom/parse_eeprom.py --file /path/to/eeprom_dump.txt
python3 camera/eeprom/parse_eeprom.py --interactive
```

Infrared RAW conversion:

```bash
python3 infrared/raw_tools/read_local_raw.py /path/to/frame.raw --width 640 --height 480 --output-dir output
```

MCAP ROS log extraction:

```bash
python3 common/parse_mcap_log.py /path/to/file.mcap -o logs
python3 common/parse_mcap_log.py /path/to/file.mcap --topic /x5/vlog=x5.txt --topic /s100/vlog=s100.txt
```

IMU MCAP analysis:

```bash
python3 imu/mcap_analysis/analyze_imu_mcap.py --help
```

## Maintenance

- Add new tools under the sensor directory that owns the workflow.
- Keep reusable parsing/conversion code parameterized with CLI arguments.
- Do not commit raw MCAP, generated plots, model files, binary libraries, or local reports.
- If a tool needs sample data, document the expected format and keep the sample small.
- Run `python3 -m py_compile` on changed Python files before pushing.
