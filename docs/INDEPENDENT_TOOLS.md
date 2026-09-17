# 独立工具目录清单

下面每一行都是可单独复制的使用单位。Python 工具统一在复制后的文件夹执行
`python3 -m pip install -r requirements.txt`，然后运行入口脚本；不安装仓库根项目。

| 复制文件夹 | 入口示例 |
|---|---|
| `common` | `parse_mcap_log.py` |
| `camera` | `capture_stereo_isp.py` |
| `camera/distortion` | `stereo_intrinsic.py` |
| `camera/eeprom` | `parse_eeprom.py` |
| `camera/isp_json` | `compare_json.py old.json new.json` |
| `imu/mcap_analysis` | `analyze_imu_mcap.py` |
| `imu/vibration` | `analyze_vibration.py` |
| `infrared/raw_tools` | `IrConverter.py` |
| `infrared/ir_qr_bench` | `ir_qr_bench.py` |
| `lidar/realtime_check` | `lidar_realtime_check.py` |
| `lidar/packets_parse` | `extract_lidar_pcd.py` |
| `lidar/packets_parse/foxglove` | `mcap_add_lidar_points.py` |
| `uwb/ble_tools` | `analyze_angle_all.py` |
| `uwb/desai_ble` | `run_uwb_ble.py` |
| `uwb/smoke_test` | `uwb_smoke_test.py` |
| `uwb/truth_value_analysis` | `mcap_to_csv_cdr_correct.py` |
| `uwb/mcap_tools/vis_ansys` | `mcap_to_csv.py` |
| `uwb/mcap_tools/uwb_data_b1_b2_compare` | `mcap_to_csv_cdr_correct.py` |
| `uwb/rosbag_tools` | `uwb.py` |
| `uwb/vendor_compare` | `main_analysis.py` |
| `uwb/visualization` | `plot_uwb_csv.py` |
| `docs/codex_sensor_skills/imu-mcap-analysis/scripts` | `analyze_imu_mcap.py` |

- `lidar/packets_parse` 的 `scripts`、`src`、`config` 属于一个完整工具，需一起复制；`foxglove` 则也可单独复制。
- `imu/imu_reg_tools` 本来就是独立 C++ 工具，按其 README 编译，无 Python 安装要求。
- `uwb/bench_control` 保持旧系统脚本原样，按用户要求不迁移。
- `driver_reference` 是历史源码参考，iOS 目录仅有 SDK 说明，不冒充可部署工具。
- BLE 广播需要 Linux 的 BlueZ、dbus-python、PyGObject；只有图表分析时不需要这些硬件运行条件。
- PCD 交互窗口可选装 Open3D；PNG 导出不需要。
- 包含共享模块的工具已内置所需 `sensor_tools` 文件，请连同子目录复制，不需要自行打包或同步。

维护者：根目录共享源码用于统一修复；各工具内置副本与共享源码的一致性、独立导入与命令启动由测试检查。
