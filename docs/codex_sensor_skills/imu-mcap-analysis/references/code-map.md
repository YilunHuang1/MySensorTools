# imu-mcap-analysis source map

Baseline: remote master `291b58055b54a924735604f26b840ab1f22b5427` (2026-09-17).
Paths below are relative to vita-robot. Read them at that revision with `git show`;
recheck remote master and deployed revision before a new investigation.

- `src/middleware/sensor/imu/aorta_imu_mapper.cpp` — Aorta IMU mapping; values copied here do not establish physical units by themselves.
- `src/middleware/sensor/imu/imu.cpp` — Sensor conversion, coordinate transforms, calibration and filtering.
- `src/application/lowlevel_service/ControlManager.cpp` — Trace body-IMU production and source units for the exact revision.
- `src/application/vita_slam/vs_ros/aorta_interface/aorta_sensor_adapters.hpp` — Aorta-to-SLAM conversion and timestamp interpretation.
- `src/application/vita_slam/vs_ros/slam_node.cpp` — Fault thresholds and active consumers; distinguish body IMU from LiDAR IMU.

Record exact channel/schema, source/publish/log timestamps, counts and configuration.
Topic registration, static code and an old sample do not establish current device health.
See [Aorta contract](../../AORTA.md).
