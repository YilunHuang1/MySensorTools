# Aorta migration execution record

Status: software migration and listed validation finished.
Physical acceptance limits remain explicit in the per-tool matrix.

Source baseline: vita-robot master `291b58055b54a924735604f26b840ab1f22b5427`
(2026-09-17). The final remote recheck advanced from `b405fb5d78` to `291b58055b`.
The single added commit changes EDU bridge packaging/access configuration; it does
not change the sensor messages, services or source paths used by these tools.
Source checkout is not modified. Aorta dependencies and deployed robot
versions must be recorded separately; a source revision is not deployment proof.

The tool repository is public. Private production implementations, robot captures,
credentials and customer logs are not copied into it. Readers use file-embedded
schemas and public file-format specifications. Synthetic tests are publishable.

## Delivery checklist

- [x] Shared MCAP reader: ROS CDR, Aorta BFBS, aliases, timestamps, errors (scope limits in the matrix)
- [x] Common log extraction and debug-case paths (scope limits in the matrix)
- [x] UWB offline conversion, truth/batch/vendor/plot workflows (scope limits in the matrix)
- [x] UWB online smoke, BLE/serial protocols and launch/deploy scripts (coverage and limits in the matrix)
- [x] LiDAR realtime, packet extraction, timing, PCD and Foxglove (scope limits in the matrix)
- [x] IMU MCAP, vibration, register tool build and protocol/argument review (coverage and limits in the matrix)
- [x] Camera capture, calibration, distortion, EEPROM and JSON helpers (coverage and limits in the matrix)
- [x] Infrared raw images and buildable QR bench (coverage and limits in the matrix)
- [x] Reference source/version metadata, documentation and packaged skills (scope limits in the matrix)
- [x] Per-entry clean-environment and real-data verification (scope limits in the matrix)
- [x] Dog 199 bounded live validation and evidence (coverage and limits in the matrix)
- [x] Final source/diff review and publication payload checks

GitHub synchronization is verified against the published commit in the delivery
message; this file records test evidence rather than a self-referential commit hash.

Existing IMU register changes are useful and retained for verification. The untracked
`lidar/realtime_check/Untitled` path note is left untouched and excluded from commits.

The user explicitly excludes `uwb/bench_control` from migration because that
bench still runs the old ROS system. Its script and README remain unchanged.

Online defaults are passive. Service restarts, pairing changes, direct sensor-register
writes and GPIO changes need a concrete controlled test and recovery procedure.

## Verified results (2026-09-17)

- 85 regression tests (83 core plus two BLE logging checks) pass in a clean Python 3.12 environment: ROS CDR and synthetic BFBS decoding, aliases and
  ambiguity, bounded CLI parsing, missing-data reports, point fields and strides,
  image encodings, camera calibration models, serial framing/CRC/C5 extensions,
  and a real AprilTag detector with generated circle21h7 and blank frames.
- Serial fault tests cover corrupt CRCs/lengths, fragmented headers, malformed
  TLVs, short writes, disconnect cleanup and missing/rejected ranging setup ACKs.
  The current firmware's C5 34-byte declaration / 38-byte payload exception is
  handled only when its RSSI count proves the extension; an ordinary 34-byte C5
  followed by another TLV remains separate. Missing error-status responses are
  reported as unknown rather than a clean hardware result.
- Both MCAP derivative tools preserve original message order, empty registered
  channels, metadata and attachments in synthetic roundtrip tests. Non-finite
  point timestamps are rejected instead of silently changing scan boundaries.
- Dog 199 runs deployment `85ef4703b00afc3f090d08ef0fca7975a4581d62`, which is
  distinct from the master baseline. Passive UWB checks read Anchor 5.2.4,
  Tag 0.2.20, CONNECTED, battery 32%, and a successful empty current FaultMgr
  snapshot. No ranging frames were captured; the report correctly exits 2
  (INCOMPLETE), not PASS. A float-duration incompatibility found live was fixed.
- Stereo ISP capture: all eight requested topics produced decodable messages
  during a five-second sample. Full-mode live capture receives 14/17 streams;
  full NV12 left/right and right-half NV12 are missing, so the result is INCOMPLETE.
  Configured publisher names alone do not establish image production.
- LiDAR: a three-second raw stream demonstrates that serial packets span Aorta
  message boundaries. Reassembly recovers 8977 CRC-valid point packets versus
  8280 under the old per-message parser. One CRC failure/one sequence discontinuity
  remains in this sample; it is not attributed to hardware without more evidence.
  Three complete extracted scans contain 600 packets / 9600 points each, with no
  cross-frame timestamp regression in the two available scan boundaries.
  A later three-second live sample passes: 728 transport messages, 8995 point
  packets, 10 point clouds, zero CRC errors, sequence discontinuities and point
  timestamp regressions. The earlier anomalous recording remains recorded as such.
  PCD output now preserves arrival order instead of hiding regressions by sorting.
- IMU: real Aorta raw and LiDAR IMU decoded with their different source units;
  vibration CSV and plots generated. Preserved register-tool changes compile on
  S100 ARM64 without compiler warnings and `--help` works. No SPI/register writes have been tested.
- Infrared: the user confirmed it is normally disabled and authorized enabling it.
  Aorta enable and disable both returned SUCCESS. The bounded capture received
  25 mono8 1536x1160 frames plus 25 H.265 messages, at approximately 15 Hz with no
  timestamp regressions. All images exported; RAW/MCAP exports match pixel-for-pixel;
  H.265 decoded successfully. The detector processed all 25 images with zero
  target-ID-2 detections. Physical target/pose accuracy is not established by that
  scene. After restoring disabled state, a two-second recording received zero images.
- Raw captures, private logs and reports are under ignored `.validation/`, not
  public fixtures. No production service has been restarted or persistently reconfigured.
  Only the authorized temporary infrared enable/disable operation changed camera state.

## Additional completed workflows

- Clean root-package installation with analysis/device/infrared/test dependencies;
  43 CLI-help or shell-syntax checks passed. Python compilation and diff whitespace
  checks passed. Linux BLE dependencies and help validated in a new isolated 199
  directory, with no Bluetooth advertisement or serial device opened.
- UWB truth workflow processed 72 height-zero files out of 216 source files;
  batch workflow processed all 216 / 51354 records. Vendor comparison, source CSV
  recheck, serial charts, corrected-CSV PNG/GIF workflows completed.
- LiDAR preview MCAP preserves all 728 original message payloads, schemas and
  timestamps and adds three point clouds. Merge/downsample, PLY roundtrip and
  LAS quantization checked on 4310 points. Calibration table analysis and all
  three timestamp comparison modes executed.
- Full entry-by-entry coverage and limits are recorded in
  [TOOL_VALIDATION_MATRIX.md](TOOL_VALIDATION_MATRIX.md).

## Scope and remaining physical acceptance limits

- UWB bench stays on its original ROS implementation by explicit user request.
  There is no pending bench-interface decision. Historical and current online smoke
  modes only observe ranging; neither automatically starts it. A connected Tag
  with ranging disabled is not a migration failure or a passed ranging test.
- BLE radio/serial control and register-write operations were checked through
  protocol/error simulation, imports and device builds where applicable. Physical
  radio pairing and register-write/restoration acceptance have not been performed.
- Source compatibility is checked against the master baseline; 199's deployed
  revision is separately recorded. This does not assert that 199 runs that master.
- The matrix documents GUI and physical accuracy limits rather than claiming them
  as device acceptance. Public commits contain only tool code, synthetic fixtures
  and documentation; private capture files remain local.

## Deployment correction (2026-09-17)

The original smoke validation used a staged shared package and explicit PYTHONPATH,
so it did not cover a user copying only `uwb/smoke_test` into `/app/uwb/smoke_test`.
That deployment lacked both `sensor_tools` and `mcap`. The source-only bundle now
includes shared modules, a private dependency installer and an early actionable
missing-module check. Isolated tests exclude the development editable installation
and verify the deployed directory resolves both bundled source and `.deps`.
The installer installs explicit runtime requirements rather than building the root
project on the robot: the deployed packaging environment produced UNKNOWN metadata
without dependencies during the first attempt. Imports must succeed before the
installer reports success.

Verified on 199 at `/app/uwb/smoke_test`, using the user's exact command after
sourcing `/app/script/env.sh`, without a PYTHONPATH override:
`python3 uwb_smoke_test.py --mode online --ranging-duration 15`.
Anchor 5.2.4, Tag 0.2.20, CONNECTED with 30% battery, current FaultMgr zero faults;
4 PASS / 1 WARN / 1 SKIP and exit 2 because ranging is intentionally disabled.
The complete report was written successfully. No service or ranging state changed.
The original directory was backed up before repair.
