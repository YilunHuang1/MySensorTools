# Per-tool migration and verification matrix

Baseline: vita-robot remote master `291b58055b54a924735604f26b840ab1f22b5427`,
rechecked against the remote on 2026-09-17. Dog 199 deployment is separately
`85ef4703b00afc3f090d08ef0fca7975a4581d62`. This matrix describes coverage,
not a blanket statement that every hardware operation passed.

Evidence classes: **L** bounded live data; **R** real recording/dataset replay;
**S** synthetic regression; **C** compile/import/help; **P** device or decision
pending. Private evidence is in ignored `.validation/` and is not a public fixture.

| Tool / entry | Migration decision and behavior | Verification / limitation |
|---|---|---|
| `sensor_tools/mcap.py`, `flatbuffer.py` | Shared embedded-schema CDR/BFBS/JSON decoder, aliases, group ambiguity errors, distinct timestamps | S + R: 2905 messages / 7 BFBS schemas in passive 199 recording; malformed and mixed encodings tested |
| `sensor_tools/aorta.py` | Deployed environment, bounded CLI, explicit record topics, integer duration and process cleanup | S + L: camera, LiDAR, UWB captures; float duration issue found and fixed |
| `common/parse_mcap_log.py` | Decode ROS logs and Aorta vlog batches; atomic output; no-data error | S + R: X5/S100 logs exported |
| `common/create_debug_case.py` | Resolve sibling vita-robot and current tool repository; generated cases ignored by Git | Workflow: generated ignored case with data symlink, issue YAML and report stub |
| `imu/mcap_analysis/analyze_imu_mcap.py` and packaged skill wrapper | Shared reader, units preserved, logs and empty-data status | S + R: body/LiDAR IMU and logs; wrapper delegates to maintained entry |
| `imu/vibration/analyze_vibration.py` | Explicit data/config paths and units; MCAP/DB3 adapter | R: statistics CSV and three plots; no claim of sensor acceptance from a short recording |
| `imu/imu_reg_tools/imu_diag.cpp` | Retain existing user changes for range configuration; validate register values and restoration | C: S100 ARM64 clean build and help; P: live SPI reads/writes and controlled restoration |
| `camera/capture_stereo_isp.sh`, `.py` | Passive Aorta capture with configuration manifest, message decoding and checksums | L: ISP 8/8 streams; full 14/17 (missing full NV12 L/R and right half NV12), correctly INCOMPLETE |
| `camera/distortion/stereo_intrinsic.py` | Current cameras-list and legacy calibration, correct distortion model, truthful failed-file reporting | S + workflow: calibration summary CSV and plots |
| `camera/distortion/visualize_distortion_ring.py`, `_fisheye.py` | YAML/text input, explicit dimensions, model checks, output errors | S + workflow: radial and equidistant plots |
| `camera/distortion/visualize_distortion_ring_test.py` | Keep standalone synthetic demonstration; remove import-time plotting | C; synthetic demo only |
| `camera/distortion/motion_blur_calculator.py` | Transport-independent optical approximation; no Aorta adaptation required | Source review / example run; uniform pixels-per-degree approximation, not calibrated image-plane prediction |
| `camera/eeprom/parse_eeprom.py` | Strict hex/header checks; configurable serial offset; heuristic candidate labeled | S + C; P: hardware EEPROM read (tool consumes a dump only) |
| `camera/isp_json/compare_json.py` | Transport-independent JSON comparison; malformed roots fail | Source review / C; no device ISP mutation |
| `infrared/raw_tools/read_local_raw.py` | Explicit mono/YUYV/UYVY/NV12/RGB encoding, dimensions and stride | S + L/R: padded buffers, bad sizes; 199 mono8 RAW and MCAP exports match pixel-for-pixel |
| `infrared/raw_tools/IrConverter.py` | MCAP image/metadata exporter replaces ROS republisher | S + L/R: after authorized enable, 25 actual 1536x1160 mono8 images exported; disable restored and zero subsequent frames |
| `infrared/ir_qr_bench/ir_qr_bench.py` | Buildable passive circle21h7 detector, frame CSV/report/images, optional calibrated tag-in-camera pose | S: real detector on generated tag + blank, pose finite and forward; L/R: processed 25 actual IR frames with zero target-ID-2 detections; physical tag/pose accuracy unmeasured |
| old IR QR executable documentation | Historical artifact; replaced by buildable Python source | Not treated as a portable or current executable |
| `uwb/truth_value_analysis/mcap_to_csv_cdr_correct.py`, same entry in `mcap_tools/uwb_data_b1_b2_compare` | Shared CDR/BFBS conversion; no firmware inference from angles | S + R: 273-message historical CDR sample |
| `uwb/mcap_tools/vis_ansys/mcap_to_csv.py` | Shared reader, strict boolean config, metadata, atomic streaming output | R: streaming and normal output match |
| `uwb/mcap_tools/vis_ansys/visualization.py` | Validate nonempty finite XY; retain transport-independent plotting | R: PNG and GIF export |
| `uwb/truth_value_analysis/uwb_analysis_pipeline.py`, `install.sh` | Unknown firmware remains unknown; explicit output root; no stale-input reuse or basename collision; errors propagate | R: 216 inputs discovered, height=0 selects 72; per-file and aggregate reports generated; self-test available |
| `uwb/mcap_tools/uwb_data_b1_b2_compare/batch_mcap_analysis.py` | Explicit paths, filename ground truth validation, failed-file exit status | R: 216 MCAPs / 51354 records, CSVs and charts |
| `uwb/mcap_tools/uwb_data_b1_b2_compare/uwb_analysis_visualization_latest.py` | Explicit input/output, unique dataset names, unknown-version plots, no implicit CSV repair or fixed success conclusions | R: 273 records, report and plots in unknown group |
| `uwb/visualization/plot_uwb_csv.py` | Shared CSV aliases; empty data errors and output directories | R/S workflow; estimated Z requires the documented geometry, not true 3D ground truth |
| `uwb/vendor_compare/main_analysis.py`, `uwb_data_analyzer.py`, `uwb_visualizer.py`, `run_analysis.sh` | No Aorta dependency; keep documented historical scenes and +60° Quanji mounting correction; current plotting API and empty-vendor rejection | R: historical Feirui/Quanji dataset, full report/plots/JSON |
| `uwb/vendor_compare/verify_quanji_1_2m_static.py` | Explicit CSV/output/prior-report paths; retains unadjusted source-angle audit | R: Quanji static CSV, recomputed JSON and charts |
| `uwb/rosbag_tools/uwb.py` | No ROS runtime; preserve original MCAP, add derived channels; wrapped angles, unequal intervals, duplicate timestamp handling | S + R: 273 originals and 813 derivatives; insufficient data and ambiguous channels rejected |
| `uwb/smoke_test/uwb_smoke_test.py`, `checks_online.py`, `report.py` | Passive Aorta firmware/state/ranging/FaultMgr checks; FAIL/INCOMPLETE propagation | S + L: versions/state/FaultMgr readable; no ranging -> INCOMPLETE, not PASS |
| `uwb/smoke_test/checks_standalone.py`, `serial_comm.py`, `protocol.py`, `ble_comm.py` | Serial remains separate; exclusive open, CRC/C5 parser, cleanup, explicit control opt-in | S + C; P: isolated Anchor reboot, serial commands and BLE pairing |
| `uwb/ble_tools/PacketParser.py`, `CmdBuilder.py`, `crc16_utils.py` | Shared multi-TLV/C5 parser, lengths/CRC, extended RSSI layout, malformed command rejection | S: fragmented stream, corrupt CRC, short/extended C5, Apple configuration |
| `uwb/ble_tools/SerialHandlerStandalone.py`, `SerialHandler.py`, `libubitrap.py` | Shared serial-only path, no ROS message dependency; default passive, circular angle statistics, cleanup | S: statistics/logging and passive-control guard; P: physical serial session |
| `uwb/ble_tools/run_uwb_ble.py`, `linux_ble_uart.py`, `start_uwb.sh` | Explicit device control, no killall/service restart, startup error propagation | C on 199 Linux; P: iPhone/Anchor radio workflow |
| `uwb/ble_tools/deploy.py`, `deploy.sh` | Explicit SSH target, new isolated directory, isolated dependencies, no auto-start | L: staged in new 199 temp directory, imports and --help passed; no BLE/serial activity |
| `uwb/ble_tools/test_logging.py` | Replace hardware-dependent pseudo-test with deterministic statistics/CSV tests | S: two tests passed |
| `uwb/ble_tools/analyze_uwb_logs.py`, `analyze_angle_all.py`, `analyze_angle_test6.py` | Explicit input/output, current pandas/matplotlib, wrapped derivatives, no fixed capture path | S workflow: 100-row serial fixture produced all plots/statistics |
| `uwb/desai_ble/run_uwb_ble.py` | Bounded explicit port/baud, multi-TLV parser, correct RSSI/confidence, clean close, OK code not counted as error | S parser + C; P: physical serial capture |
| `uwb/bench_control/uwb_bench.sh` and README | User explicitly retains the old ROS bench system; excluded from Aorta migration | Original script and README unchanged; no bench redesign or robot endpoint needed |
| `uwb/ble_tools/uwb_msg` | Incomplete historical ROS interface package is excluded from colcon; current serial tools need no ROS message package | Metadata review; no invented missing message schema |
| `uwb/ble_tools/iOS` | Only Qorvo SDK reference README is present, no buildable Xcode application | External prerequisite; no iOS build or phone session claimed |
| `lidar/realtime_check/lidar_realtime_check.py` | Passive Aorta / offline MCAP, full fields/stride/endian support, packet reassembly and exact boundary definition | S + L: latest 3-second sample 728 transport messages, 8995 point packets, 10 clouds; zero CRC/sequence/timestamp regressions |
| `lidar/packets_parse/extract_lidar_pcd.py` | Shared reassembly, explicit paths and calibration, frame timestamp reset, no-data errors | R: XYZI PCD extraction |
| `lidar/packets_parse/extract_lidar_pcd_with_ts.py` | Resolution locking, correct last-valid-channel anchor, placeholders, order-preserving PCD and ordered boundary CSV | S + R: three complete 600-packet/9600-point frames; current-model two boundaries have no regression |
| `lidar/packets_parse/extract_with_timestamp_range_example.py` | CLI forwarding replaces fixed incident path/time | C; timestamp-range flags validated by extraction entry |
| `lidar/packets_parse/compare_timestamp_modes.py` | Bounded unique frame alignment, partial/unmatched reporting, reversed endpoints | R: three timestamp models compared; historical model can regress within a frame, not current-driver equivalence |
| `lidar/packets_parse/scripts/extract.py`, `src/core/{calibration,decoder,extractor}.py` | Shared transport reader; retained geometric decoder and explicit input; fixed frame boundaries | R: three preview PCD frames; modular preview does not establish current production timestamp equivalence |
| `lidar/packets_parse/scripts/check_sequence.py` | Shared transport reader, explicit MCAP/topic | S + R: CRC-invalid counter excluded; one discontinuity remains in the earlier sample; no UDP-loss inference |
| `lidar/packets_parse/analyze_calibration.py` | Summarize actual 16x2 coefficients; remove unsupported accuracy/model inference | Workflow: bundled table, finite/shape validation |
| `lidar/packets_parse/analyze_pcd_quality.py` | Shared ASCII/binary PCD reader, finite statistics, explicit nominal rate, no hardware health score | R: three extracted scans; invalid return placeholders retained in counts |
| `lidar/packets_parse/point_cloud_tools.py` | Correct PCD fields/types, explicit merge/downsample/PLY/LAS | R: merge/downsample/LAS; XYZ/intensity export does not preserve extra timestamp/ring fields |
| `lidar/packets_parse/visualize_pcd.py` | Shared reader, finite filtering, headless PNG output | R: preview PNG; interactive Open3D UI not exercised |
| `lidar/packets_parse/foxglove/mcap_add_lidar_points.py` | Preserve source MCAP; unique JSON preview topic; atomic no-overwrite output | R: all 728 original message payloads, schemas and timestamps match; three previews added |
| `lidar/packets_parse/foxglove/vanjee_722z_converter.ts` | Decoded Aorta input, cross-message buffering, chunk preview | C strict TypeScript; R: 728 chunks -> 727 outputs / 139360 valid points; Foxglove GUI integration remains untested |
| `lidar/packets_parse/timestamp_utils.py`, `src/utils/timestamp.py` | Transport-independent historical timestamp helpers | Source review; current extraction uses explicit validated source timestamp path |
| camera/infrared `driver_reference`, calibration/ISP examples | Historical reference only; no production source copied during migration | Source/deployment labels added; not build/flash targets |
| `docs/codex_sensor_skills`, LiDAR debug guide | Aorta contracts and current source maps; historical ROS commands labeled | Documentation review; installed global skills unchanged |

## Validation boundaries and publication

- The user explicitly keeps the legacy UWB bench unchanged. Online smoke remains
  passive. CONNECTED without ranging is supported; ranging acceptance is incomplete
  in this device state, not a migration failure. Actual ranging parsers and analysis
  are additionally tested with recordings and synthetic protocol fixtures.
- The authorized infrared enable/capture/disable cycle succeeded on 199. It yielded
  25 raw and 25 H.265 messages at 14.9999 Hz, with no timestamp regressions; H.265
  decoded successfully. The following two-second capture contained zero images.
- Serial/BLE radio operation, SPI writes/restoration, physical AprilTag pose accuracy
  and GUI integrations have the limitations identified in their rows. Protocol
  simulation, build or replay evidence is not relabeled as physical acceptance.
- Clean-environment installation and 83 regression tests (81 core plus two BLE logging checks) passed. Final publication
  review and GitHub synchronization are recorded in AORTA_MIGRATION_STATUS.md.

No private raw fixture, robot configuration or capture is committed. Existing local
`lidar/realtime_check/Untitled` is intentionally left untouched and excluded.
