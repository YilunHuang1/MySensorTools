# lidar-debug source map

Baseline: remote master `291b58055b54a924735604f26b840ab1f22b5427` (2026-09-17).
Paths below are relative to vita-robot. Read them at that revision with `git show`;
recheck remote master and deployed revision before a new investigation.

- `src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/src/source/source_packet_aorta.hpp` — Raw packet transport; messages can split hardware packets.
- `src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/src/source/source_pointcloud_aorta.hpp` — Point-cloud Aorta publication.
- `src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/src/source/foxglove_point_cloud_encoder.hpp` — Point-field offsets/types; do not assume ROS PointCloud2 layout.
- `src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/src/source/source_imu_packet_aorta.hpp` — LiDAR IMU conversion and units.
- `src/middleware/sensor/lidar/time_sync/time_sync.cpp` — Clock synchronization and fault reporting.
- `src/application/vita_slam/vs_ros/aorta_interface/aorta_sensor_adapters.hpp` — Consumer timestamp/point interpretation.

Record exact channel/schema, source/publish/log timestamps, counts and configuration.
Topic registration, static code and an old sample do not establish current device health.
See [Aorta contract](../../AORTA.md).
