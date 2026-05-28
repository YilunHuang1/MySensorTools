---
name: robot-rosbag-log-triage
description: Triage Vita robot ROS2 bag, MCAP, and log problems across sensors. Use when correlating a fault time with /x5/vlog, /s100/vlog, MCAP topics, topic rates, timestamps, sensor messages, fault manager logs, or when deciding which sensor-specific skill should handle IMU, LiDAR, stereo, infrared, or UWB analysis.
---

# Robot Rosbag Log Triage

Use this skill before sensor-specific diagnosis when the user provides an MCAP/rosbag/log archive and an approximate problem time.

## Workflow

1. Normalize the issue time to an absolute CST timestamp.
2. List bag topics, message types, counts, and first/last timestamps.
3. Decode `/x5/vlog` and `/s100/vlog` around the window if present.
4. Build a causal timeline, not only a fault list. Search backward and forward from the visible fault for:
   - preceding `fallen`, impact, emergency stop, passive/recovery action, joystick/motion command;
   - power-state transitions, especially exit from low power / power saving;
   - sensor init / re-init / calibration / bias logs;
   - process restart versus internal reset/reinitialization;
   - sensor driver safety, split-frame, packet loss, calibration, time sync, and mode-change logs.
5. Extract fault lines and restore lines; keep original timestamps.
6. Compare fault time with sensor topic samples in the same window.
7. Route to the relevant skill:
   - IMU: `imu-mcap-analysis`
   - LiDAR: `lidar-debug`
   - Stereo: `stereo-debug`
   - Infrared: `infrared-debug`
   - UWB: `uwb-debug`
8. Separate bag evidence from live-robot checks.

## Useful Commands

When ROS2 is available:

```bash
ros2 bag info <bag_dir_or_mcap>
ros2 topic list
ros2 topic hz <topic>
```

When only Python MCAP parsing is available, prefer existing project tools:

```bash
python3 imu/mcap_analysis/analyze_imu_mcap.py topics <bag.mcap>
python3 imu/mcap_analysis/analyze_imu_mcap.py logs <bag.mcap> \
  --center "YYYY-MM-DD HH:MM:SS.mmm" \
  --window-seconds 10 \
  --log-topics /x5/vlog,/s100/vlog
```

For plain log archives:

```bash
grep -RniE 'FAULT|FAULT_RESTORE|ERROR|WARN|IMU|LIDAR|UWB|infrared|stereo' <log_dir>
```

## Correlation Rules

- Do not merge log time, MCAP receive time, and message header stamp. Compare them explicitly.
- Always include the time zone and the exact query window.
- A fault restore immediately after a fault often means single-frame or transient evidence; inspect neighbor samples.
- Missing topic data can mean the topic was not recorded, not necessarily absent on the robot.
- If the bag starts after a suspected init / calibration event, say explicitly that the bag cannot validate the causal setup phase.
- MCAP evidence can prove what was published/recorded; it cannot alone prove hardware cause without driver/register/log evidence.
- Do not answer with "possible causes" before identifying the earliest bad timestamp and the preceding state change. If evidence is sufficient, state the root cause directly.
- Distinguish process restart from internal application reset. Use process monitor PID logs when available.
- For robot falls/impacts, compare fault order: if `fallen` or emergency stop precedes the sensor fault, report it as a trigger/correlation, not as a downstream effect of that sensor fault.

## Output

Return:

- Bag/log metadata.
- Timeline around the issue.
- Relevant topics and sample health.
- Earliest bad line, preceding event, and whether the evidence supports causality.
- Which sensor-specific analysis should run next, or the direct conclusion if already proven.
