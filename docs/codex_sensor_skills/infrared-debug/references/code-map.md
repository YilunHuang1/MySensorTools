# Infrared Code Map

## Current Verified Paths

- `src/middleware/sensor/infrared/config/node_config.json`
  - Node name: `infrared_camera`.
  - Task: `infrared_camera_task`, class `InfraredCameraTask`, period `100ms`.
  - Publishes:
    - `/infrared_camera/image_raw` as `sensor_msgs/Image`.
    - `/infrared_camera/video_h265` as `foxglove_msgs/CompressedVideo`.
- `src/middleware/sensor/infrared/config/nodes/infrared_camera.json`
  - Checked config:
    - Sensor `sc202cs`.
    - Resolution `1536x1160`.
    - FPS `15`.
    - `codec_config.enable_h265: false`.
  - Current checked file contains merge conflict markers around `ir_light_config`; treat it as dirty until resolved.
- `src/middleware/sensor/infrared/infrared_camera_task.cpp`
  - Reads camera, save, performance, codec, and locally edited IR-light configs.
  - Initializes `InfraredCameraPipeline`.
  - Reports `PERCEPTION_INFRARED_CAMERA_MAIN_CONNECTION_LOST` if pipeline init fails.
  - Uses optional H265 encoder only when enabled.
  - Current checked file contains merge conflict markers around IR-light logic.
- `src/middleware/sensor/infrared/infrared_camera_pipeline.*`
  - ISP/YNR/PYM pipeline implementation.
- `src/middleware/sensor/infrared/lib`
  - Contains SC202CS ISP libraries, including `lib_sc202cs_linear.so` and `libsc202cs.so*`.
- `src/middleware/sensor/infrared/legacy`
  - Older infrared implementation. Check only if the deployed service/package uses the legacy target.

## Common Evidence To Collect

- Whether the deployed robot has the same config as the checked tree.
- `ros2 topic hz /infrared_camera/image_raw`.
- Message dimensions, encoding, and data size from `/infrared_camera/image_raw`.
- H265 enabled state and `/infrared_camera/video_h265` rate if enabled.
- Logs containing `infrared`, `sc202cs`, `SC202CS`, `ISP`, `H265`, `pipeline`, `lux`, `AE`, `PERCEPTION_INFRARED`.
- For IR fill light behavior, include robot body mode/context because suppression modes may intentionally disable the light.
