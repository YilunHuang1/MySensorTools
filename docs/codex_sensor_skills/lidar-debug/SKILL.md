---
name: lidar-debug
description: Debug Vita robot LiDAR issues using vita-robot code-grounded checks. Use when investigating /lidar_points, /lidar_imu, /lidar_packets, empty or sparse point clouds, 100ms/200ms timestamp anomalies, VanJee driver startup, UDP/packet flow, LiDAR time sync, lidar RTC faults, SLAM LiDAR ingestion, or LiDAR firmware/OTA questions.
---

# LiDAR Debug

Use this skill for S100 LiDAR problems. Treat old Copilot notes as hints only; verify every conclusion against the current `vita-robot` tree and the provided logs/bags.

## Workflow

1. Capture the symptom, exact CST time, robot platform, and data source: live robot, log archive, rosbag, or MCAP.
2. Read the current code/config before answering. Start with [references/code-map.md](references/code-map.md).
3. Separate the chain into driver output, ROS topic transport, SLAM/VLN consumption, and fault reporting.
4. For bag/MCAP issues, use `robot-rosbag-log-triage` first to get topic counts, time ranges, and logs; then return here for LiDAR-specific interpretation.
5. For point cloud issues, inspect both packet-level evidence and PointCloud2 evidence. Do not infer packet loss only from SLAM behavior.
6. For timing issues, compare message header stamp, publish/log time, point `time` field/unit, LiDAR RTC sync logs, and expected scan period.
7. For `lidar ts ... later than imu back ts`, do not stop at "timestamp mismatch". Build the full evidence chain:
   - first failing `ldr ts` interval and exact `/lidar_imu` back timestamp gap;
   - point count or point-cloud dimensions near the same time;
   - VanJee publish/split-frame rate near the same time;
   - preceding `fallen`, impact, emergency stop, mode change, or functional-safety logs;
   - code formula that produces `lidar_end_time`.
8. Report findings as verified facts, root cause, fix plan, and remaining uncertainty.

## Live Checks

Prefer non-destructive commands:

```bash
ros2 topic list | grep -Ei 'lidar|points|packet|imu'
ros2 topic hz /lidar_points
ros2 topic echo /lidar_points --once --no-arr
ros2 topic hz /lidar_imu
grep -RniE 'PERCEPTION_LIDAR|RTC|lidar|vanjee|pps|sync' /log/usr/archive
```

Use packet capture only when network/UDP is the question and the interface/port are known:

```bash
tcpdump -i <iface> udp -c 50
```

## Interpretation Rules

- `/lidar_points` is the main PointCloud2 topic consumed by `vita_slam` and VLN guard paths in the current code.
- `/lidar_imu` is the LiDAR internal IMU topic consumed by SLAM as the LiDAR IMU, not the S100 body IMU.
- The LiDAR module in `src/middleware/sensor/lidar` wraps the third-party VanJee SDK target; driver topics and packet behavior may be defined under `src/third_party/sensors/vanjee_lidar`.
- A 100ms/200ms interval issue needs scan-period, header stamp, publish time, and packet/frame assembly checks. Do not call it packet loss until packet counts or frame IDs support it.
- Empty PointCloud2 can come from driver startup/config, UDP ingress, packet decoding, point filtering/range filtering, or downstream conversion. Keep these separate.
- LiDAR RTC/time-sync faults are reported in `time_sync`; correlate `PERCEPTION_LIDAR_DRIVER_RTC_NOT_INCREASING` with sync logs before blaming SLAM.
- In `vita_slam`, `/lidar_points` header stamp becomes `lidar_beg_time`; point offset/curvature is used to compute `lidar_end_time`. If `last_lidar_imu_ts < lidar_end_time`, SLAM cannot form a synchronized LiDAR+IMU measurement and may later drop frames by `imu_boundary`.
- For VanJee 722Z, an abnormal sparse frame such as `16 x 23` or `POINTCLOUD_EMPTY: Point count: 80`, especially with `pub rate` above nominal and `splitFrame` count above expected, is driver scan-assembly evidence. Treat internal SLAM reset/reinitialization as downstream unless the first bad line is a SLAM reset.
- `Functional safety -- id: 0, fault code: 1031` can be background noise if normal `16 x 600` frames continue. It becomes relevant only when it aligns with abnormal point-cloud dimensions, split-frame count, timestamp mismatch, or impact/fall evidence.
- If an impact/fall is suspected, correlate `/lidar_imu`, `/imu_raw`, and `/imu_raw_x5` acceleration/gyro around the first bad frame. Decide whether impact is the trigger while keeping the driver publishing behavior as the software fault if partial frames enter SLAM.

## Output

Keep the answer short and evidence-led:

- Fault/symptom summary with exact time range.
- Data path and topic map.
- Verified evidence from logs/bag/code, including the earliest bad timestamp.
- Root cause stated directly; avoid a list of generic possibilities when evidence is enough.
- Fix plan split by owner: supplier driver, middleware guard, SLAM fault isolation, and recording improvements.
- Next data needed, if any.
