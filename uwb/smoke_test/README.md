# UWB 冒烟测试工具

用于检查 Anchor/Tag 固件、连接状态、测距数据和串口协议。
本目录的 online 模式已迁移到 Aorta；`../bench_control` 是用户保留的旧 ROS
台架工具，两者独立，不需要为了运行冒烟测试而执行台架流程。

## 安装

在仓库根目录执行：

```bash
pip install -e '.[device]'
```

## Online：不停服务的在线检查

在机器人上加载运行环境，使用部署的 `aorta` 和 `aorta-record`：

```bash
source /app/script/env.sh
python3 uwb/smoke_test/uwb_smoke_test.py --mode online --output-dir reports
python3 uwb/smoke_test/uwb_smoke_test.py --mode online --ranging-duration 15 --output-dir reports
```

online 模式**不主动开启测距**，也不修改配对、切换机器人模式或重启服务。
仓库中迁移前的 ROS online 实现也是通过订阅 `/uwb/data` 检查测距，未发送
开启命令。Tag 与 Anchor 已连接（`CONNECTED`）不代表测距已开启（`RANGING`）。
未开启时仍可运行冒烟测试：版本、连接、电量、当前故障分别检查，测距项报告
未完成，数据项跳过；不会把这种状态误报为串口/连接故障或测距通过。

| 检查 | Aorta 接口 / 验收范围 |
|---|---|
| Anchor、Tag 版本 | `firmware_version/uwb`，请求 `target_device_type: 3`，分别按设备名称读取返回版本 |
| Tag 状态、电量 | `uwb/state`；`CONNECTED` 和 `RANGING` 均为可接受连接状态 |
| 测距帧率 | 录制 `uwb/ranging`，检查发布时钟和实际帧率；`--min-frame-rate` 应填写部署配置中的阈值 |
| 数据完整性 | 使用同一份采集数据，检查距离、角度、俯仰、滤波值和置信度；统计不等于定位精度验收 |
| 当前故障 | `software/faultmgr/get_faults_info` 的 type 3 当前快照；这是系统全量结果，不是仅 UWB 的历史故障 |

不指定 `--min-frame-rate` 时只报告测量帧率，不擅自套用旧固件的固定阈值。
零测距帧或阈值未指定时，整体结果为 `INCOMPLETE`，退出码 2。
退出码 0 表示全部检查通过；退出码 1 表示至少一项明确失败。

## Standalone：隔离后直接检查 Anchor 串口

此模式发送串口命令并重启 Anchor，需要先隔离占用串口的生产服务。
脚本本身不会停止或恢复系统服务，`--allow-device-control` 是显式操作开关。
需按现场流程记录原服务状态，并在测试完成或失败后恢复。

```bash
python3 uwb/smoke_test/uwb_smoke_test.py --mode standalone \
  --serial-port /dev/ttyS7 --allow-device-control --output-dir reports
```

入口检查串口通信、版本、重启恢复、心跳、错误状态及 CRC。
没有收到错误状态消息时报告未知，不等同于“没有硬件故障”。
底层解析器支持 CRC 校验、多 TLV、C5 扩展 RSSI 和已确认的固件长度例外。
`checks_standalone.py` 另有可调用的测距辅助检查，但当前 standalone 入口不运行它们。

## 报告与验证

终端及 `smoke_test_report_YYYYMMDD_HHMMSS.json` 均保留逐项结果。
本地回归覆盖协议错误、断连、停止测距清理及在线缺数据分支；硬件实测范围见
[逐工具验收表](../../docs/TOOL_VALIDATION_MATRIX.md)。串口模拟通过不代表已经完成
Anchor 重启、BLE 配对和射频测距的物理验收。
