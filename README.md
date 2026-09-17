# MySensorTools

Curated sensor analysis and diagnosis tools for Vita robot work.

This repository is organized by sensor type and contains only maintainable tool code, small configuration templates, calibration tables, and documentation. Raw captures, generated reports, model files, binary packages, and local debug artifacts are intentionally excluded from git.

The migration targets `vita-robot` remote master, recorded in
[the migration status](docs/AORTA_MIGRATION_STATUS.md). MCAP tools decode embedded
ROS CDR or Aorta FlatBuffers schemas; no local ROS installation is required for
these readers. Live tools use the deployed `aorta` and `aorta-record` executables.

**Aorta migration:** see the status record and per-tool matrix for live, replay,
synthetic and build verification coverage. The legacy UWB bench stays unchanged
for its old ROS system. A tool receiving no data must not be treated as a passing
sensor test; physical acceptance limits are recorded separately.

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

## 使用方式：按工具文件夹复制

每个工具独立使用，无需安装整个仓库。复制目标文件夹时包含其中的
`sensor_tools`、配置文件等子目录，在该文件夹执行：

```bash
python3 -m pip install -r requirements.txt
python3 <工具脚本>.py --help
```

例如只复制 `uwb/smoke_test`，即可安装依赖并运行 `uwb_smoke_test.py`。
[独立工具目录清单](docs/INDEPENDENT_TOOLS.md)列明每个复制单位及特殊系统依赖。
根目录 `pyproject.toml` 仅供维护者开发/回归测试使用，不是用户部署前提。

See [docs/TOOLS_GUIDE.md](docs/TOOLS_GUIDE.md) for commands and verification limits.
