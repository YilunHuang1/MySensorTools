# MySensorTools

Curated sensor analysis and diagnosis tools for Vita robot work.

This repository is organized by sensor type and contains only maintainable tool code, small configuration templates, calibration tables, and documentation. Raw captures, generated reports, model files, binary packages, and local debug artifacts are intentionally excluded from git.

## Structure

| Directory | Contents |
| --- | --- |
| `uwb/` | UWB smoke tests, BLE tools, MCAP conversion, accuracy analysis, vendor comparison, plotting. |
| `lidar/` | Vanjee WLR-722Z packet parsing, PCD extraction, timestamp checks, realtime health checks. |
| `camera/` | Distortion/intrinsic helpers, ISP JSON comparison, EEPROM parser, SC230AI reference snippets. |
| `imu/` | IMU MCAP anomaly analysis and vibration comparison. |
| `infrared/` | Infrared RAW conversion and driver reference snippets. |
| `common/` | Cross-sensor utilities. |
| `docs/` | Tool guide, migration notes, and Codex sensor skill references. |

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

See [docs/TOOLS_GUIDE.md](docs/TOOLS_GUIDE.md) for tool locations, usage examples, and maintenance rules.
