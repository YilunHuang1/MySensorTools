# Sensor tools: Aorta and historical ROS MCAP

Use Python 3.10+ from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[analysis,device,infrared,test]'
python -m pytest -q
```

Normally the root installation is required even when running a script in a
subdirectory. UWB smoke tests are self-contained: copy the whole
[`uwb/smoke_test` folder](../uwb/smoke_test/README.md), including its `sensor_tools`
subdirectory, and run `python3 -m pip install -r requirements.txt` there.
No root project installation, archive builder or private installer is needed.
Offline readers do not need ROS. Linux BLE advertising additionally needs system
BlueZ, `dbus-python` and PyGObject; these are not portable pip-only dependencies.
Open3D is optional for interactive point-cloud windows; PNG export does not need it.

## Common data contract

MCAP messages are decoded using their embedded schema and encoding: ROS CDR,
Aorta FlatBuffers/BFBS or JSON. Unknown encodings, malformed payloads and ambiguous
short topic names fail explicitly. Specify the exact topic if a recording contains
multiple Aorta groups. A short `/uwb/data` selects the current `uwb/ranging` alias;
`/x5/vlog` and `/s100/vlog` also accept their batch variants. Aliases do not mix
two distinct channels silently.

Keep message source timestamp, MCAP publish time and MCAP log time separate.
Inspect source/deployment units before comparing IMUs; the reader does not silently
convert g to m/s² or deg/s to rad/s. Raw LiDAR packets may cross MCAP message
boundaries and must be reassembled before CRC/sequence checks.

## Bounded live tools (on the robot)

The helpers source `/app/script/env.sh` and use `/app/aorta/bin` as a fallback.
Overrides: `AORTA_ENV_SCRIPT`, `AORTA_CLI`, `AORTA_RECORDER`. Do not substitute a
stock Zenoh configuration for the deployed session configuration.

```bash
python uwb/smoke_test/uwb_smoke_test.py --mode online --ranging-duration 5
python lidar/realtime_check/lidar_realtime_check.py --mode both --timeout 5 --output lidar-check.json
python camera/capture_stereo_isp.py --mode isp --duration 5 --output-root /tmp/stereo_check
python infrared/ir_qr_bench/ir_qr_bench.py --duration 5 --image-save-dir /tmp/ir_check
```

UWB/LiDAR/camera checks distinguish PASS, FAIL and INCOMPLETE (exit 0/1/2).
No data, unknown acceptance thresholds or an unperformed check cannot establish
sensor health. IR bench reports a detection measurement, not a hardware pass.
Camera `full` requests all supported stream names; configured-but-unproduced streams
remain visible as missing, rather than changing configuration to make them appear.

Serial/BLE bench operations are separate from online checks. They require an
isolated device and explicit `--allow-device-control`; they must not compete with
production serial readers. `uwb/bench_control` is explicitly retained unchanged
for the user's old ROS bench. Online smoke tests do not start ranging; a connected
Tag without ranging still permits version/state/fault checks.

## Offline commands

```bash
python common/parse_mcap_log.py capture.mcap -o output/logs
python imu/mcap_analysis/analyze_imu_mcap.py topics capture.mcap
python imu/mcap_analysis/analyze_imu_mcap.py analyze capture.mcap --topics /imu_raw,/lidar_imu
python uwb/truth_value_analysis/mcap_to_csv_cdr_correct.py --help
python uwb/truth_value_analysis/uwb_analysis_pipeline.py -s /path/to/mcaps --output-dir output/truth
python uwb/mcap_tools/uwb_data_b1_b2_compare/batch_mcap_analysis.py /path/to/mcaps --output-dir output/batch
python uwb/mcap_tools/uwb_data_b1_b2_compare/uwb_analysis_visualization_latest.py /path/to/corrected.csv --output-dir output/uwb_plots
python uwb/vendor_compare/main_analysis.py --data-dir /path/to/vendor_dataset --output-dir output/vendor
python uwb/visualization/plot_uwb_csv.py uwb.csv --mode 2d -o output/uwb_xy.png
python lidar/realtime_check/lidar_realtime_check.py --mcap capture.mcap --mode both
python lidar/packets_parse/extract_lidar_pcd_with_ts.py capture.mcap --mode new_driver --save-pcd --output-dir output/lidar
python lidar/packets_parse/analyze_pcd_quality.py output/lidar/new_driver --expected-hz 5
python infrared/raw_tools/IrConverter.py capture.mcap --output-dir output/ir
python infrared/raw_tools/read_local_raw.py frame.raw --width 640 --height 480 --output-dir output/ir_raw
python infrared/ir_qr_bench/ir_qr_bench.py --mcap capture.mcap --image-save-dir output/ir_bench
python camera/eeprom/parse_eeprom.py --file eeprom_dump.txt
python camera/isp_json/compare_json.py before.json after.json
```

Use each entry's `--help` for options (the JSON comparison takes two positional
files). Calibration utilities accept legacy matrices and current `cameras[]` YAML;
pinhole radial/tangential and equidistant models are handled separately. Bundled
calibration tables and ISP/driver snippets are historical references, not proof of
the current robot's deployed values. EEPROM serial extraction can be heuristic and
is labeled as such.

UWB truth/batch tools use their documented filename convention as supplied ground
truth. Vendor comparison retains its historical Feirui/Quanji scene names and the
explicit +60° Quanji mounting offset. Those scene assumptions do not come from
Aorta and must match the dataset. Unknown firmware stays unknown.

LiDAR `new_driver` is the current analysis path. `per_packet` and `driver_original`
are historical comparison models; the latter can produce intra-frame regressions.
PCD exports preserve point order, including timestamp regressions. Compare first
and last points in arrival order, not sorted extrema. Preview converters use a
reference angular table and are not substitutes for factory calibration or a
production PointCloud recording.

See [migration coverage](AORTA_MIGRATION_STATUS.md) for actual verification and gaps.
Keep captures, private code/configuration, credentials and reports out of Git.
