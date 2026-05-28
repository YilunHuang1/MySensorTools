# Stereo Code Map

## Current Verified Paths

- `src/middleware/sensor/stereo/config/node_config.json`
  - Node name: `stereo_camera`.
  - Task: `camera_encode_task`, class `CameraEncodeTask`, period `30ms` unless overridden by `codec_config.fps`.
  - Publishes H265 topics:
    - `/image_left_raw/h265`
    - `/image_right_raw/h265`
    - `/image_left_raw/h265_half`
    - `/image_right_raw/h265_half`
    - `/image_left_raw/h265_quarter`
    - `/image_right_raw/h265_quarter`
    - `/image_left_raw/h265_undistort`
  - Publishes NV12 image topics:
    - `/image_left_raw/nv12_half`
    - `/image_right_raw/nv12_half`
    - `/image_left_raw/nv12_quarter`
    - `/image_right_raw/nv12_quarter`
  - Publishes ISP status:
    - `/stereo/left/isp_status`
    - `/stereo/right/isp_status`
- `src/middleware/sensor/stereo/stereo_camera_node.*`
  - Node wrapper and runtime config/service surface.
- `src/middleware/sensor/stereo/camera_encode_task.cpp`
  - Starts `DualCameraPipeline`.
  - Applies runtime encoder config updates from `StereoCameraNode`.
  - Publishes raw VSE frames and encoded streams according to `DualCameraPipeline` outputs.
  - Handles optional video dump config.
- `src/middleware/sensor/stereo/dual_camera_pipeline.*`
  - Main dual-camera pipeline; inspect for sensor init, VSE outputs, sync, and frame acquisition.
- `src/middleware/sensor/stereo/gdc_gen.*`
  - Calibration/GDC/rectification artifact generation.
- `src/application/vita_slam/vs_cfg/slam/slam.yaml`
  - Checked config has `camera.en: false` and topics `/image_left_raw/h264`, `/image_right_raw/h264`.
- `src/application/vln/traj_to_cmd_task.h`
  - `kImageTopic = "/image_left_raw/nv12_quarter"` for visualization.

## Common Evidence To Collect

- Topic rates and header stamps for left/right matching streams.
- Actual message type and encoding: `foxglove_msgs/CompressedVideo` versus `sensor_msgs/Image`.
- Resolution and data length for NV12 topics.
- H265 decoder/playback evidence if the symptom is cloud/video display.
- `/stereo/left/isp_status` and `/stereo/right/isp_status` for exposure/gain.
- Logs containing `stereo`, `CameraEncodeTask`, `DualCameraPipeline`, `VSE`, `H265`, `codec`, `ISP`, `HDR`.
