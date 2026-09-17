# stereo-debug source map

Baseline: remote master `291b58055b54a924735604f26b840ab1f22b5427` (2026-09-17).
Paths below are relative to vita-robot. Read them at that revision with `git show`;
recheck remote master and deployed revision before a new investigation.

- `src/middleware/sensor/stereo/stereo_aorta_publisher.cpp` — Image, video and metadata publication.
- `src/middleware/sensor/stereo/stereo_aorta_config.cpp` — Aorta stream configuration parsing.
- `src/middleware/sensor/stereo/stereo_aorta_context.cpp` — Control context consumption.
- `src/middleware/sensor/stereo/config/nodes/stereo_aorta.json` — Publisher stream names and enable flags.
- `src/middleware/sensor/stereo/config/nodes/stereo_camera.json` — Pipeline outputs; compare with publisher configuration and actual deployed values.

Record exact channel/schema, source/publish/log timestamps, counts and configuration.
Topic registration, static code and an old sample do not establish current device health.
See [Aorta contract](../../AORTA.md).
