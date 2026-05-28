---
name: vita-sensor-debug
description: Entry skill for triaging Vita robot sensor problems before routing to IMU, LiDAR, UWB, stereo, or infrared debug skills. Use when the user provides an MCAP/rosbag/log archive, fault time, vague sensor symptom, multi-sensor issue, vita_slam/VLN/perception fault, or asks which sensor-specific skill should be used.
---

# Vita Sensor Debug

Use this as the first-pass dispatcher for Vita robot sensor incidents. Keep this skill focused on triage and routing; load the sensor-specific skill only after the failing subsystem is identified.

## Workflow

1. Normalize the problem description:
   - Robot/platform if known: S100, X5, head sensor, body sensor.
   - Absolute CST time and window.
   - Evidence type: live robot, MCAP/rosbag, `/log/usr/archive`, screenshot, or code-only.
   - Main symptom: fault name/id, missing topic, abnormal value, perception behavior, or downstream behavior.
   - Whether there was a preceding power-state transition, restart, cable unplug/replug, manual relocation, or other event before the visible symptom.
   - Preceding physical/system event if any: fall, collision, speed bump, emergency stop, passive/recovery action, power-state change, restart, cable change, or manual relocation.
2. If a bag/log is provided, use `robot-rosbag-log-triage` first to list topics, decode `/x5/vlog` and `/s100/vlog`, and build a timestamped timeline.
3. Read [references/routing-map.md](references/routing-map.md) when the symptom is ambiguous or multi-sensor.
4. Route to exactly one primary skill first:
   - `imu-mcap-analysis` for IMU acceleration/gyro, `IMU_DATA_ANOMALY`, `/imu_raw`, `/imu_raw_x5`, `/lidar_imu`.
   - `lidar-debug` for `/lidar_points`, VanJee driver, LiDAR RTC/time sync, point cloud, LiDAR IMU as head-mounted auxiliary IMU.
   - `stereo-debug` for X5 dual-camera, left/right image streams, H265/NV12, ISP status, stereo timing.
   - `infrared-debug` for SC202CS infrared raw/H265 streams, IR fill light, QR/charging infrared behavior.
   - `uwb-debug` for `/uwb/data`, anchor/tag pairing, frame rate, link timeout, head touch, follow stutter from UWB.
5. If the first skill proves the sensor is healthy, return here and route to the next most likely subsystem or downstream application.
6. Always distinguish:
   - What the bag/log proves.
   - What current code/config proves.
   - What still requires live robot hardware checks.
   - Whether the supplied evidence covers only the symptom window or also covers the likely causal setup window.
   - Trigger/root cause versus downstream consequences such as SLAM reset, recovery action, or fault restore.

## Fast Routing Rules

- `vita_slam` + `IMU_DATA_ANOMALY` or `acc_norm`: `imu-mcap-analysis`.
- `vita_slam` + empty/sparse point cloud, `/lidar_points`, or LiDAR timestamp: `lidar-debug`.
- `VLN` follow stutter with UWB topic/fault: `uwb-debug`.
- `VLN` or perception camera issue with `/image_left_raw` or `/image_right_raw`: `stereo-debug`.
- Charging/QR/night image issue with `/infrared_camera`: `infrared-debug`.
- Unknown fault with MCAP/log only: `robot-rosbag-log-triage` first, then route.
- Multi-sensor event after impact/speed bump: start with the faulting primary topic and compare other sensors only as corroborating evidence.
- Attitude drift / spinning after low-power exit or reboot: route to `imu-mcap-analysis`, but require a backward check for sensor re-init and bias/calibration logs before deciding the IMU is healthy.
- If logs show `fallen`, emergency stop, or passive/recovery before the sensor fault, preserve that order in the conclusion. Do not imply the sensor fault caused the fall unless timestamps support it.
- For LiDAR `ldr ts ... later than imu back ts`, route to `lidar-debug` and require point-cloud dimension/rate plus `/lidar_imu` coverage evidence before concluding.

## Minimum Output

Return a concise triage result:

- Normalized time window and evidence source.
- Relevant topics/logs found or missing.
- Primary routed skill and reason.
- First three checks to run next.
- Missing information that would change the conclusion.
- For delayed-effect failures, whether the current evidence includes the setup phase before the visible symptom.
- Earliest bad timestamp and preceding trigger event, if found.
