---
name: uwb-debug
description: Debug Vita robot UWB issues using vita-robot code-grounded checks. Use for /uwb/data, /uwb/state, /uwb/head_touch, anchor/tag BLE pairing, serial port questions, low frame rate, UWB link timeout, firmware version faults, VLN follow stutter, head touch, sentry radar velocity invalid faults, or UBITRAQ protocol/log analysis.
---

# UWB Debug

Use this skill for UWB anchor/tag, BLE, ranging, and head-touch issues. Always verify current code and robot config before relying on old notes.

## Workflow

1. Identify the feature path: ranging/follow, head touch, BLE pairing, firmware version, or serial/protocol.
2. Read [references/code-map.md](references/code-map.md) before drawing conclusions.
3. Collect live/bag evidence for `/uwb/data`, `/uwb/state`, `/uwb/neighbors`, relevant services, and `/x5/vlog`/`/s100/vlog`.
4. For follow/VLN stutter, correlate UWB frame rate, `/uwb/data` continuity, function context follow status, and VLN logs. Normal topic rate alone does not prove usable data.
5. For pairing/link issues, separate BLE tag discovery/connection from serial anchor communication.
6. For faults, map the exact fault ID/name to the code path and state machine that reports it.

## Live Checks

```bash
ros2 topic list | grep -Ei 'uwb|function/context'
ros2 topic hz /uwb/data
ros2 topic echo /uwb/data --once
ros2 topic echo /uwb/state --once
ros2 topic echo /uwb/neighbors --once
ros2 service list | grep uwb
grep -RniE 'uwb|UWB|BLE|bled|anchor|tag|ranging|low frame|timeout|firmware|radar' /log/usr/archive
```

Common services:

```bash
ros2 service call /uwb/find_tag std_srvs/srv/Trigger
ros2 service call /uwb/remove_tag std_srvs/srv/Trigger
ros2 service call /firmware_version/uwb firmware_version_msgs/srv/GetFirmwareVersion
```

## Interpretation Rules

- `/uwb/data` is published from AOA/ranging callbacks; check continuity and content, not just topic existence.
- `/uwb/state` is periodic status; use it to understand mode/link state.
- Pairing uses `/uwb/pair_tag` and persists config to `/app_param/uwb/config.yaml`.
- `min_frame_rate` in `/app_param/uwb/config.yaml` gates low-frame-rate fault behavior if configured.
- Faults include low frame rate, anchor link timeout, incompatible anchor/tag firmware, and sentry radar velocity invalid. Confirm the exact fault name in code/logs.
- Head touch is tied to both `/uwb/head_touch` publication and function context synchronization; check `head_touch_enable` and context snapshot behavior.
- Do not identify a serial port from assumptions. Confirm with deployed config, process open files, device tree/dmesg, or service logs.

## Output

Return:

- UWB subsystem path under test.
- Topic/service/log evidence.
- Code-grounded fault logic.
- Likely root cause and next check.
