---
name: imu-mcap-analysis
description: Analyze robot dog IMU faults from ROS2 MCAP bags, especially vita_slam IMU_DATA_ANOMALY, /imu_raw, /imu_raw_x5, and /lidar_imu issues. Use when debugging ASM330 or LiDAR ICM45688P IMU anomalies, acceleration norm thresholds, MCAP-only evidence, or deciding whether a fault comes from raw sensor data, ROS conversion, VQF, or slam ingestion.
---

# IMU MCAP Analysis

Use this skill when investigating IMU faults in `vita-project`, especially `vita_slam` `IMU_DATA_ANOMALY`.

## Workflow

1. Identify the visible fault time in CST from logs.
2. Decide whether this is a direct-sample fault or a delayed-effect fault:
   - direct-sample: `IMU_DATA_ANOMALY`, impossible acceleration, dropouts;
   - delayed-effect: attitude drift / spinning, bad orientation after reboot or power-state change, stand-up failure with otherwise plausible raw samples.
3. Read [references/code-map.md](references/code-map.md) and re-check the current `vita-robot` code before making conclusions.
4. List MCAP channels with `scripts/analyze_imu_mcap.py topics`.
5. Analyze `/imu_raw`, `/imu_raw_x5`, and `/lidar_imu` around the visible fault time.
6. Decode `/x5/vlog` and `/s100/vlog` in the same time window.
7. Search backward and forward for physical/system events that can change interpretation:
   - `fallen`, collision/impact, emergency stop, passive/recovery, posture threshold;
   - low-power exit / reboot / sensor re-init;
   - gyro offset / bias / calibration logs;
   - evidence the robot was moving during the bias capture interval.
8. Compare the MCAP sample at the fault timestamp with the `vita_slam` log value when the failure is direct-sample based.
9. Trace the topic path in code before blaming conversion, VQF, or hardware.

## Command Pattern

```bash
python3 <skill_dir>/scripts/analyze_imu_mcap.py topics <bag.mcap>
python3 <skill_dir>/scripts/analyze_imu_mcap.py analyze <bag.mcap> \
  --center "2026-05-13 14:24:54.240" \
  --window-seconds 2 \
  --topics /imu_raw,/imu_raw_x5,/lidar_imu
python3 <skill_dir>/scripts/analyze_imu_mcap.py logs <bag.mcap> \
  --center "2026-05-13 14:24:54.240" \
  --window-seconds 2 \
  --log-topics /x5/vlog,/s100/vlog \
  --log-keywords "IMU_DATA_ANOMALY,SPI,Accel Norm,GPS 0 buffer overflow"
```

The script uses the Python `mcap` package and manual CDR decoding of `sensor_msgs/msg/Imu` and `rcl_interfaces/msg/Log`, so it does not require `ros2 bag` or `mcap_ros2`.

## vita_slam Facts To Verify

- Primary SLAM IMU comes from `vita-robot/src/application/vita_slam/vs_cfg/slam/slam.yaml`, usually `/imu_raw`.
- `PrimaryImuCallback()` computes `acc_norm` directly from `sensor_msgs::msg::Imu::linear_acceleration` before `RosUtils::ToImuMeas()`.
- `RosUtils::ToImuMeas()` only copies `linear_acceleration` and `angular_velocity`; it does not scale, filter, or VQF-transform the data.
- `/imu_raw` is published by `lowlevel_service/ControlManager.cpp` from `imu_state.acc_raw`.
- `imu_state.acc_raw` is populated before VQF, offset compensation, and coordinate transform.
- `/imu_raw_x5` is the X5/head ASM330 topic and is not the primary `vita_slam` IMU unless config says so.
- `/lidar_imu` is the head LiDAR internal IMU and enters `LidarImuCallback()` as `sensor_id=1`; it is not the direct trigger for `IMU_DATA_ANOMALY`.
- The checked fault ID for `IMU_DATA_ANOMALY` is `PERCEPTION_SLAM_SENSOR_FUSION_IMU_DATA_ANOMALY` / `0x40070102`.

## Interpretation Rules

- A single `/imu_raw` sample below `0.1` norm that matches the fault log means the fault existed before `vita_slam` conversion.
- Walking over a speed bump can produce high acceleration spikes, especially on `/lidar_imu` mounted in the head.
- A body-mounted S100 ASM330 sample with all acceleration axes near zero for one frame is more likely a raw read/publish glitch than normal vibration.
- Repeated `/lidar_imu` values near a fixed high magnitude can indicate sensor range saturation during impact, even if it is not the primary fault.
- Always correlate fault samples with `/s100/vlog` and `/x5/vlog`; this can reveal SPI errors, fault restore edges, GPS buffer warnings, or lowlevel logs at the same timestamp.
- If `/imu_raw` has a one-frame near-zero acceleration sample and neighboring frames are normal, prioritize read/publish glitch checks before declaring permanent IMU hardware failure.
- If all three IMU topics are bad at the same wall-clock time, consider robot impact, timestamp/log parsing, or common power/timing issues rather than a single sensor.
- If asked whether an anomaly is caused by collision or falling, compare event order first: physical/fallen logs before sensor faults are a trigger/correlation, while sensor faults before `fallen` can support a sensor-caused fall.
- Use acceleration/gyro spikes only as corroboration. They prove impact energy at a sensor location, not by themselves the root cause of the robot state transition.
- `/lidar_imu` saturation near the LiDAR head can explain LiDAR/head-local anomalies after a hit; it does not automatically prove the body S100 `/imu_raw` is faulty.
- Separate root cause from downstream effects such as `POINTCLOUD_EMPTY`, `POSE_DIVERGED`, SLAM reset/reinit, or fault restore messages.
- Normal `/imu_raw` near the symptom does **not** rule out a bad gyro bias captured earlier during IMU re-init.
- If attitude spins while accel looks normal, check whether gyro offsets were estimated after low-power exit / reboot while the robot was moving.
- Large gyro offsets logged soon after init are suspect when the robot was not guaranteed static during bias calculation.
- If the MCAP starts after the re-init / bias window, request earlier system logs before closing the case as "IMU healthy."

## Code-Level Checks To Consider

- In `sensor/imu/imu.cpp`, inspect whether `ReadRawAccel()`/`ReadRawGyro()` propagate SPI transfer failures or can leave zero/default bytes.
- In IMU init / bias-estimation logic, verify the required stationary assumption and what happens if the robot moves during the capture window after resume from low power.
- In `DataCollectionLoop()`, verify whether abnormal `acc_raw` is logged/dropped before publishing.
- In `lowlevel_service/ControlManager.cpp`, verify whether `/imu_raw` publishes `acc_raw`/`gyro_raw` without pre-publish validation.
- In `vita_slam/vs_ros/slam_node.cpp`, verify whether abnormal primary IMU frames are still fed into `AddImuMeas()` after fault reporting.

## Report Template

Use `references/report-template.md` for concise handoff reports.
