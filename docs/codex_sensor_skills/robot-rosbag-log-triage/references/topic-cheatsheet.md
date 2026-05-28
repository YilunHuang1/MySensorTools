# Vita Topic Cheatsheet

Use this as a starting point only; verify against the current robot config and bag topic list.

## IMU

- `/imu_raw`: S100 primary IMU published by lowlevel service.
- `/imu_raw_x5`: X5/head ASM330 topic.
- `/lidar_imu`: LiDAR internal IMU.

## LiDAR

- `/lidar_points`: PointCloud2 consumed by SLAM and some VLN/guard paths.
- `/lidar_imu`: LiDAR internal IMU.
- Packet topics may come from the VanJee driver config; list bag topics before assuming a name.

## Stereo

- `/image_left_raw/h265`, `/image_right_raw/h265`
- `/image_left_raw/h265_half`, `/image_right_raw/h265_half`
- `/image_left_raw/h265_quarter`, `/image_right_raw/h265_quarter`
- `/image_left_raw/nv12_half`, `/image_right_raw/nv12_half`
- `/image_left_raw/nv12_quarter`, `/image_right_raw/nv12_quarter`
- `/stereo/left/isp_status`, `/stereo/right/isp_status`

## Infrared

- `/infrared_camera/image_raw`
- `/infrared_camera/video_h265`

## UWB

- `/uwb/data`
- `/uwb/state`
- `/uwb/neighbors`
- `/uwb/head_touch`
- `/uwb/audio`
- `/uwb/audio_done`

## Logs

- `/x5/vlog`
- `/s100/vlog`
