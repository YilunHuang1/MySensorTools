# infrared-debug source map

Baseline: remote master `291b58055b54a924735604f26b840ab1f22b5427` (2026-09-17).
Paths below are relative to vita-robot. Read them at that revision with `git show`;
recheck remote master and deployed revision before a new investigation.

- `src/middleware/sensor/infrared/infrared_aorta.cpp` — Aorta publication and control integration.
- `src/middleware/sensor/infrared/infrared_aorta_codec.cpp` — Raw-image and video encoding contract; verify encoding, dimensions, stride and timestamp.
- `src/middleware/sensor/infrared/infrared_camera_task.cpp` — Pipeline operation and enable conditions.
- `src/middleware/sensor/infrared/infrared_camera_pipeline.cpp` — Sensor capture and image processing.
- `src/middleware/sensor/infrared/config/nodes/infrared_camera.json` — Source defaults, not deployed configuration proof.
- `src/application/vita_slam/vs_calib/infrared_verify.cpp` — Production detector/pose behavior; the standalone bench only reports tag-in-camera pose.

Record exact channel/schema, source/publish/log timestamps, counts and configuration.
Topic registration, static code and an old sample do not establish current device health.
See [Aorta contract](../../AORTA.md).
