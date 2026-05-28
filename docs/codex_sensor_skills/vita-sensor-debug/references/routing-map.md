# Vita Sensor Debug Routing Map

Use this map after normalizing the problem time and evidence source.

## First-Pass Evidence

- MCAP/rosbag: list topics, message counts, first/last timestamps, and sample health around the issue time.
- Logs: search `/x5/vlog`, `/s100/vlog`, `FAULT`, `FAULT_RESTORE`, `ERROR`, `WARN`, and the exact fault name/id.
- Code/config: verify topic names from current `vita-robot`, not old notes.
- Live robot: check topic presence/rate before changing config or restarting services.

## Topic-To-Skill Map

| Evidence | Primary skill |
| --- | --- |
| `/imu_raw`, `/imu_raw_x5`, `/lidar_imu`, `IMU_DATA_ANOMALY`, `acc_norm` | `imu-mcap-analysis` |
| `/lidar_points`, LiDAR packets, VanJee, RTC/time sync, point cloud empty/sparse | `lidar-debug` |
| `/image_left_raw/*`, `/image_right_raw/*`, `/stereo/*/isp_status` | `stereo-debug` |
| `/infrared_camera/image_raw`, `/infrared_camera/video_h265`, IR fill light, SC202CS | `infrared-debug` |
| `/uwb/data`, `/uwb/state`, `/uwb/head_touch`, BLE pairing, anchor/tag faults | `uwb-debug` |
| `/x5/vlog`, `/s100/vlog`, unknown fault, broad MCAP/log timeline | `robot-rosbag-log-triage` |

## Application-To-Sensor Hints

- `vita_slam` usually starts from IMU and LiDAR evidence. Check `slam.yaml` before assuming camera involvement.
- `vln` follow behavior can involve LiDAR, stereo, UWB, calibration, and function state. Start from the reported fault or missing topic.
- Charging/QR behavior often needs infrared evidence first, then downstream controller logs.
- Head-mounted vibration can affect LiDAR internal IMU and cameras differently from the body-mounted S100 IMU.

## Escalation Rules

- If no bag/log is provided, ask for exact CST time plus MCAP/log archive before making root-cause claims.
- If only screenshots are provided, extract the fault name/id/time and request the corresponding logs or MCAP.
- If multiple sensors fail at the same timestamp, consider power, time sync, CPU load, recorder drop, or impact before blaming one sensor.
- If current source files contain conflict markers, state that code-grounded conclusions are blocked until that module is cleaned up.
