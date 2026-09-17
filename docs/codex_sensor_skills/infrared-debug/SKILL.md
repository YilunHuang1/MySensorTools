---
name: infrared-debug
description: Debug Vita robot infrared camera issues using vita-robot code-grounded checks. Use for /infrared_camera/image_raw, /infrared_camera/video_h265, SC202CS ISP libraries, infrared enable/disable, frame rate, exposure/gain/lux, IR fill-light behavior, QR/charging perception, NFC interference checks, or infrared fault reporting.
---

# Infrared Debug

Read [the Aorta contract](../AORTA.md) before these sensor-specific checks.

Use this skill for infrared camera issues. Verify pinned master source and deployed configuration separately.

## Workflow

1. Record source revision and deployed service/configuration; do not treat historical worktree conflicts as current faults.
2. Read [references/code-map.md](references/code-map.md) for current topic/config/code paths.
3. Separate the symptom into capture/pipeline, Aorta publication, H265 encode, ISP/AE metadata, IR fill light, or downstream QR/charging usage.
4. Check live/bag evidence for `/infrared_camera/image_raw` first; then check `/infrared_camera/video_h265` only if H265 is enabled in config.
5. For lighting/lux behavior, verify whether the checked code has IR-light logic compiled cleanly before interpreting logs.
6. Report verified facts and call out any blocked conclusions caused by dirty/conflicted code.

## Live Checks

```bash
python infrared/ir_qr_bench/ir_qr_bench.py --duration 5 --image-save-dir /tmp/ir_check
```

A bounded sample with no frames is incomplete. Check the deployed camera service,
pipeline enable conditions and current context before deciding the camera failed.
Do not enable IR lighting or change GPIO merely to obtain a passing report.

## Interpretation Rules

- `/infrared_camera/image_raw` is the primary raw image evidence. Do not debug H265 first unless raw frames are already healthy.
- Verify deployed `codec_config.enable_h265`; disabled H265 makes absence of its video topic expected.
- `infrared_camera_task.cpp` reports `PERCEPTION_INFRARED_CAMERA_MAIN_CONNECTION_LOST` when pipeline init fails.
- Replacing ISP `.so` can be a runtime deployment issue or a build/package issue; inspect `BUILD.bazel`, installed files, and service restart behavior before deciding.

## Output

Return:

- Current code/config sanity status.
- Topic health table.
- Pipeline versus encode versus downstream conclusion.
- Exact next check or patch needed.
