# IMU Code Map

## Current Verified Paths

- `src/application/vita_slam/vs_cfg/slam/slam.yaml`
  - Primary IMU topic: `/imu_raw`.
  - LiDAR internal IMU topic: `/lidar_imu`.
- `src/application/vita_slam/vs_ros/slam_node.cpp`
  - `PrimaryImuCallback()` computes `acc_norm` from `sensor_msgs::msg::Imu.linear_acceleration`.
  - Fault condition: `acc_norm < 0.1 || acc_norm > 50.0`.
  - Reports `IMU_DATA_ANOMALY`.
  - Then converts with `RosUtils::ToImuMeas()` and adds the measurement to SLAM.
  - `LidarImuCallback()` converts `/lidar_imu` with sensor id `1`.
- `src/application/vita_slam/vs_sys/fault_reporter.hpp`
  - Maps `IMU_DATA_ANOMALY` to `PERCEPTION_SLAM_SENSOR_FUSION_IMU_DATA_ANOMALY`.
- `src/middleware/fault_ids/sub_fault_id/fault_id_perception.h`
  - `PERCEPTION_SLAM_SENSOR_FUSION_IMU_DATA_ANOMALY = 0x40070102`.
- `src/application/vita_slam/vs_ros/ros_interface/ros_utils.hpp`
  - `ToImuMeas()` copies acceleration and angular velocity from ROS IMU message into SLAM measurement.
- `src/application/lowlevel_service/ControlManager.cpp`
  - Publishes `/imu_raw`.
  - `OnImuPublishTimer()` fills `linear_acceleration` from `imu_state.acc_raw`.
  - Fills `angular_velocity` from `imu_state.gyro_raw`.
- `src/middleware/sensor/imu/imu.cpp`
  - Platform SPI device is selected by build platform: S100 uses `/dev/spidev0.0`, X5 uses `/dev/spidev2.0`.
  - `ReadRawAccel()` reads raw ASM330 accel registers and scales to g-like units.
  - `DataCollectionLoop()` stores `state.acc_raw` and `state.gyro_raw` before compensation/transform.
  - VQF uses the sampled accel/gyro for orientation, but `/imu_raw.linear_acceleration` comes from `acc_raw`.
- `src/middleware/peripheral/imu_node.cpp`
  - Publishes X5/head IMU, typically `/imu_raw_x5`, from peripheral middleware.
- `src/middleware/sensor/lidar` and VanJee driver
  - LiDAR internal IMU publishes `/lidar_imu`; treat separately from S100 body ASM330.

## Evidence To Collect

- MCAP samples for `/imu_raw`, `/imu_raw_x5`, `/lidar_imu` around the fault time.
- `/s100/vlog` and `/x5/vlog` lines around the same time.
- `acc_norm`, individual accel axes, gyro axes, header stamp, log time.
- Neighbor samples before/after the fault sample.
- SPI/read errors, register dump evidence, or missing source-side logs.

## Code Improvements To Consider During Debug

- Propagate SPI transfer failure from low-level register reads.
- Drop or mark a single impossible all-axis accel frame before publishing `/imu_raw`.
- Log raw register bytes when `acc_raw.norm()` is outside expected range.
- In SLAM, consider gating on consecutive abnormal primary IMU frames and avoid feeding bad frames into `AddImuMeas()`.
