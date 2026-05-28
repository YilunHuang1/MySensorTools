# LiDAR Code Map

## Current Verified Paths

- `src/middleware/sensor/lidar/BUILD.bazel`
  - Aliases the LiDAR node to `//src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk:vanjee_lidar_sdk_node`.
  - Installs SDK config files, parameter files, and `time_sync/config/sync.yaml`.
- `src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk`
  - Third-party VanJee driver implementation and configuration.
  - Inspect this tree for packet decoding, driver node startup, packet/pointcloud publishing, and model-specific params.
- `src/middleware/sensor/lidar/time_sync/time_sync.cpp`
  - Creates fault client `lidar_driver`.
  - Reports `PERCEPTION_LIDAR_DRIVER_RTC_NOT_INCREASING`.
- `src/middleware/sensor/lidar/time_sync/config/sync.yaml`
  - Current checked config contains `serial_232: /dev/ttyS3` and `sleep_time: 0`.
- `src/middleware/sensor/lidar/lidar_ota`
  - LiDAR OTA wrapper. The OTA binary path in code is `/app/lidar/VanJeeLidar_arm64`.
- `src/application/vita_slam/vs_cfg/slam/slam.yaml`
  - LiDAR enabled with topic `/lidar_points`.
  - LiDAR internal IMU topic is `/lidar_imu`.
  - Point time unit is controlled by `ego.lio.timestamp_unit`; current checked value is `0` for seconds.
- `src/application/vita_slam/vs_ros/slam_node.cpp`
  - Subscribes to `sensor_cfg.lidar.topic` and `sensor_cfg.lidar.imu_topic`.
  - Reports `LIDAR_DATA_ANOMALY` when converted cloud is null/empty/too small.
  - Also consumes `/lidar_imu`; keep this distinct from primary `/imu_raw`.
- `src/application/vln/traj_to_cmd_task.h`
  - Uses `/lidar_points` for trajectory refinement/costmap paths.
- `src/application/function_statemachine/guard/guard_node.cpp`
  - Subscribes to configured LiDAR point cloud topic for guard/safety checks.

## Common Evidence To Collect

- Topic existence/count/rate for `/lidar_points`, `/lidar_imu`, and any packet topic in the bag.
- PointCloud2 fields, width/height, `point_step`, `row_step`, data length, and first/last stamp.
- Number of points per frame and min/max range distribution.
- Driver log lines containing `vanjee`, `lidar`, `RTC`, `PPS`, `sync`, `packet`, `timeout`, or `PERCEPTION_LIDAR`.
- If timing is the issue, compare:
  - MCAP log time.
  - ROS header stamp.
  - Per-point time field and configured `timestamp_unit`.
  - Expected scan period.
