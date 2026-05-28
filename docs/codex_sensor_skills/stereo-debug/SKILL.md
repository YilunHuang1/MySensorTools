---
name: stereo-debug
description: Debug Vita robot stereo camera issues using vita-robot code-grounded checks. Use for X5 stereo topics, /image_left_raw and /image_right_raw streams, H265/NV12 output, HDR versus linear mode, ISP status, exposure/gain, frame timing, encoder runtime config, camera calibration/GDC, or stereo data used by SLAM/VLN/cloud paths.
---

# Stereo Debug

Use this skill for X5 dual-camera/stereo issues. Verify current code and config first; do not rely on old Copilot conclusions without checking the repo.

## Workflow

1. Identify whether the symptom is capture, encoding, topic publication, calibration/rectification, timing, or downstream consumption.
2. Read [references/code-map.md](references/code-map.md) for current topic and code locations.
3. Check live or bag evidence for left/right symmetry: topic presence, rate, timestamp delta, resolution, encoding, and frame drops.
4. For HDR/linear questions, inspect X5 sample code and current `stereo` config/code before deciding whether runtime switching is supported.
5. For SLAM/VLN questions, verify whether that downstream module is actually subscribed to stereo topics in its current config.
6. Report which layer is proven good and where evidence stops.

## Live Checks

```bash
ros2 topic list | grep -Ei 'image_left|image_right|stereo|camera|isp'
ros2 topic hz /image_left_raw/h265_quarter
ros2 topic hz /image_right_raw/h265_quarter
ros2 topic hz /image_left_raw/nv12_quarter
ros2 topic echo /stereo/left/isp_status --once
ros2 topic echo /stereo/right/isp_status --once
```

For recording focused data:

```bash
ros2 bag record -s mcap \
  /image_left_raw/h265_quarter /image_right_raw/h265_quarter \
  /image_left_raw/nv12_quarter /image_right_raw/nv12_quarter \
  /stereo/left/isp_status /stereo/right/isp_status
```

## Interpretation Rules

- Treat H265 streams and NV12 raw image streams as different evidence surfaces. H265 can fail while capture still works.
- Check both left and right topics; one-sided failures often indicate sensor/pipeline/channel config rather than global ROS transport.
- Use `Isp2AStatus` topics for exposure/gain clues; avoid guessing exposure behavior from image brightness alone.
- `vita_slam` camera use depends on `slam.yaml` camera enable and configured topics. The checked config has camera disabled, so stereo may be irrelevant to SLAM unless config changes.
- VLN code references `/image_left_raw/nv12_quarter` for visualization in `traj_to_cmd_task`, not necessarily as core localization input.

## Output

Give a concise diagnosis with:

- A verified topic/config table.
- Layer-by-layer status: capture, encode, publish, downstream.
- The most likely fault layer and why.
- Exact commands or code locations for the next check.
