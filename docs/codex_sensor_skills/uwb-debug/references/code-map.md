# UWB Code Map

## Current Verified Paths

- `src/middleware/sensor/uwb/include/ros2/config.h`
  - Config path: `/app_param/uwb/config.yaml`.
  - Loads `tag_name`, `precode`, `angle_offset`, `mode`, `double_click_mode`, `session_id`, `min_frame_rate`, `microphone_gain`, `ranging_timeout_s`, `head_touch_cooldown_s`, `radar_threshold`, `index_threshold`, and `log_level`.
- `src/middleware/sensor/uwb/src/ros2/config.cpp`
  - Validates ranges for config values.
  - Persists tag name and pair config.
- `src/middleware/sensor/uwb/src/ros2/uwb_node.cpp`
  - Creates fault client `uwb_fault_client`.
  - Publishes:
    - `/uwb/data`
    - `/uwb/audio`
    - `/uwb/state`
    - `/uwb/neighbors`
    - `/uwb/head_touch`
    - `/uwb/audio_done`
  - Services:
    - `/uwb/pair_tag`
    - `/uwb/remove_tag`
    - `/uwb/find_tag`
    - `/firmware_version/uwb`
    - `/uwb/head_touch_enable`
  - Subscribes to function context snapshot for follow/head-touch state sync.
  - Reports faults:
    - `PERCEPTION_UWB_ANCHOR_LOW_FRAME_RATE`
    - `PERCEPTION_UWB_ANCHOR_UWB_LINK_TIMEOUT`
    - `PERCEPTION_UWB_ANCHOR_FIRMWARE_VERSION_INCOMPATIBLE`
    - `PERCEPTION_UWB_TAG_FIRMWARE_VERSION_INCOMPATIBLE`
    - `PERCEPTION_UWB_ANCHOR_SENTRY_RADAR_V_INVALID`
- `src/middleware/sensor/uwb/include/ble` and `src/middleware/sensor/uwb/src/uwb/ble_runtime.cpp`
  - BLE discovery/connection and tag transport path.
- `src/middleware/sensor/uwb/include/serial` and `src/middleware/sensor/uwb/src/uwb/serial_runtime.cpp`
  - Anchor serial transport path.
- `src/middleware/sensor/uwb/src/uwb/interaction_service.cpp`
  - State transitions and UWB interaction logic.
- `src/application/vln/common_def.h`
  - Defines `kUwbTopic = "/uwb/data"` for VLN paths.

## Common Evidence To Collect

- `/uwb/data` rate, timestamp continuity, and payload fields.
- `/uwb/state` mode/link state.
- `/uwb/neighbors` contents if neighbor/ranging quality is suspected.
- `/app_param/uwb/config.yaml` from the robot.
- Logs containing `UWB`, `uwb`, `BLE`, `bled`, `ranging timeout`, `low frame`, `firmware`, `head_touch`, `radar`.
- Active serial usage:
  ```bash
  lsof /dev/ttyS* /dev/ttyUSB* 2>/dev/null
  dmesg | grep -Ei 'tty|uwb|usb|serial'
  ```
- Fault manager output around the issue time.
