# uwb-debug source map

Baseline: remote master `291b58055b54a924735604f26b840ab1f22b5427` (2026-09-17).
Paths below are relative to vita-robot. Read them at that revision with `git show`;
recheck remote master and deployed revision before a new investigation.

- `src/middleware/sensor/uwb/src/aorta/uwb_aorta_bridge.cpp` — Aorta publishers and service adaptation; trace uwb/ranging, state and firmware responses.
- `src/middleware/sensor/uwb/src/aorta/engineer_calibration_context.cpp` — Engineering context consumption; do not assume the old SetContext service exists.
- `src/middleware/sensor/uwb/src/ros2/uwb_node.cpp` — Shared node/state-machine logic; the directory name alone does not prove the active transport.
- `src/middleware/sensor/uwb/include/uwb/uwb_config.h` — Configuration contract; inspect deployed configuration for ports, thresholds and pairing.

Record exact channel/schema, source/publish/log timestamps, counts and configuration.
Topic registration, static code and an old sample do not establish current device health.
See [Aorta contract](../../AORTA.md).
