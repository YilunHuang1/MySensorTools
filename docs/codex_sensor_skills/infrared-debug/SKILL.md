---
name: infrared-debug
description: Debug Vita robot infrared camera issues using vita-robot code-grounded checks. Use for /infrared_camera/image_raw, /infrared_camera/video_h265, SC202CS ISP libraries, infrared enable/disable, frame rate, exposure/gain/lux, IR fill-light behavior, QR/charging perception, NFC interference checks, or infrared fault reporting.
---

# Infrared Debug

Use this skill for infrared camera issues. Verify the current worktree first because this module has recently carried local edits and may contain unresolved conflict markers.

## Workflow

1. Check the worktree/module state before analysis:
   ```bash
   rg -n '<<<<<<<|=======|>>>>>>>' src/middleware/sensor/infrared
   ```
2. Read [references/code-map.md](references/code-map.md) for current topic/config/code paths.
3. Separate the symptom into capture/pipeline, ROS publication, H265 encode, ISP/AE metadata, IR fill light, or downstream QR/charging usage.
4. Check live/bag evidence for `/infrared_camera/image_raw` first; then check `/infrared_camera/video_h265` only if H265 is enabled in config.
5. For lighting/lux behavior, verify whether the checked code has IR-light logic compiled cleanly before interpreting logs.
6. Report verified facts and call out any blocked conclusions caused by dirty/conflicted code.

## Live Checks

```bash
ros2 topic list | grep -Ei 'infrared|ir|qr'
ros2 topic hz /infrared_camera/image_raw
ros2 topic echo /infrared_camera/image_raw --once --no-arr
ros2 topic hz /infrared_camera/video_h265
grep -RniE 'infrared|SC202CS|H265|ISP|lux|AE|fault|PERCEPTION_INFRARED' /log/usr/archive
```

Focused recording:

```bash
ros2 bag record -s mcap /infrared_camera/image_raw /infrared_camera/video_h265
```

## Interpretation Rules

- `/infrared_camera/image_raw` is the primary raw image evidence. Do not debug H265 first unless raw frames are already healthy.
- The checked config has `codec_config.enable_h265: false`; if unchanged on the robot, absence of `/infrared_camera/video_h265` is expected.
- `infrared_camera_task.cpp` reports `PERCEPTION_INFRARED_CAMERA_MAIN_CONNECTION_LOST` when pipeline init fails.
- The current checked tree contains conflict markers in infrared config/task files; resolve or account for that before treating IR-light behavior as implemented.
- Replacing ISP `.so` can be a runtime deployment issue or a build/package issue; inspect `BUILD.bazel`, installed files, and service restart behavior before deciding.

## Output

Return:

- Current code/config sanity status.
- Topic health table.
- Pipeline versus encode versus downstream conclusion.
- Exact next check or patch needed.
