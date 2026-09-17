# UWB 冒烟测试工具

用于检查 Anchor/Tag 固件、连接状态、测距数据和串口协议。
本目录的 online 模式已迁移到 Aorta；`../bench_control` 是用户保留的旧 ROS
台架工具，两者独立，不需要为了运行冒烟测试而执行台架流程。

## 使用：复制文件夹、安装依赖、运行

把整个 `smoke_test` 文件夹复制到机器人，包含里面的 `sensor_tools` 子文件夹。
所有运行代码已在这个文件夹里，不需要完整 MySensorTools 仓库、项目安装或打包。

```bash
cd /app/uwb/smoke_test
python3 -m pip install -r requirements.txt
source /app/script/env.sh
python3 uwb_smoke_test.py --mode online --ranging-duration 15
```

首次使用或更新依赖后运行安装命令；平时直接运行脚本即可。
`pip install -e '.[device]'` 是完整仓库的开发安装命令，不用于这个文件夹。

## Online：不停服务的在线检查

在机器人上加载运行环境，使用部署的 `aorta` 和 `aorta-record`：

```bash
source /app/script/env.sh
python3 uwb_smoke_test.py --mode online --output-dir reports
python3 uwb_smoke_test.py --mode online --ranging-duration 15 --output-dir reports
```

online 模式**不主动开启测距**，也不修改配对、切换机器人模式或重启服务。
仓库中迁移前的 ROS online 实现也是通过订阅 `/uwb/data` 检查测距，未发送
开启命令。Tag 与 Anchor 已连接（`CONNECTED`）不代表测距已开启（`RANGING`）。
未开启时仍可运行冒烟测试：版本、连接、电量、当前故障分别检查，测距项明确显示“已连接但未开启测距”并跳过，数据项也跳过；不会把这种状态误报为串口/连接故障或测距通过。

| 检查 | Aorta 接口 / 验收范围 |
|---|---|
| Anchor、Tag 版本 | `firmware_version/uwb`，请求 `target_device_type: 3`，分别按设备名称读取返回版本 |
| Tag 状态、电量 | `uwb/state`；`CONNECTED` 和 `RANGING` 均为可接受连接状态 |
| 测距帧率 | 录制 `uwb/ranging`，检查发布时钟和实际帧率；默认最低帧率 18 Hz，可用 `--min-frame-rate` 覆盖 |
| 数据完整性 | 使用同一份采集数据，检查距离、角度、俯仰、滤波值和置信度；统计不等于定位精度验收 |
| 当前故障 | `software/faultmgr/get_faults_info` 的 type 3 系统全量当前快照；已被本轮有效测距验证覆盖的旧 UWB 超时只作参考 |

默认以 18 Hz 为最低帧率：达到或超过 18 Hz 为 PASS，低于 18 Hz 为 FAIL。
可通过 `--min-frame-rate` 指定其他阈值。
采集前后均为 `CONNECTED` 且零帧时，测距项为 `SKIP`，整体 `INCOMPLETE`（退出码 2）。
若采集前后均为 `RANGING` 却零帧，测距项为 `FAIL`（退出码 1）；状态不明或变化则保留 `WARN`。
退出码 0 表示全部检查通过；退出码 1 表示至少一项明确失败。

### 旧 UWB 超时记录不阻塞本轮验收

对 `0x40060102`（UWB 测距链路超时），当故障时间早于本轮采集开始，且本轮
测距帧率和数据完整性两项均为 PASS 时，该记录仅供参考，不影响整体 PASS。
采集期间新上报的超时、时间不明的记录、其他故障仍参与原有判定；本轮无数据、
帧率不达标或字段异常时也不会忽略旧超时。
JSON 的 `faults` 保留完整快照，`non_blocking_faults` 列出不影响本轮结果的旧记录，
`blocking_faults` 列出仍参与判定的记录。脚本不清除或修改 FaultMgr 中的故障。

## Standalone：隔离后直接检查 Anchor 串口

此模式发送串口命令并重启 Anchor，需要先隔离占用串口的生产服务。
脚本本身不会停止或恢复系统服务，`--allow-device-control` 是显式操作开关。
需按现场流程记录原服务状态，并在测试完成或失败后恢复。

```bash
python3 uwb_smoke_test.py --mode standalone \
  --serial-port /dev/ttyS7 --allow-device-control --output-dir reports
```

入口检查串口通信、版本、重启恢复、心跳、错误状态及 CRC。
按当前固件约定，监听窗口内未收到错误状态上报视为正常，错误状态项为 PASS。
收到严重错误仍为 FAIL，非致命错误仍为 WARN；心跳与 CRC 分别判定。
底层解析器支持 CRC 校验、多 TLV、C5 扩展 RSSI 和已确认的固件长度例外。
`checks_standalone.py` 另有可调用的测距辅助检查，但当前 standalone 入口不运行它们。

## 报告与验证

终端及 `smoke_test_report_YYYYMMDD_HHMMSS.json` 均保留逐项结果。
本地回归覆盖协议错误、断连、停止测距清理及在线缺数据分支；硬件实测范围见
[逐工具验收表](../../docs/TOOL_VALIDATION_MATRIX.md)。串口模拟通过不代表已经完成
Anchor 重启、BLE 配对和射频测距的物理验收。

## 维护说明

`./sensor_tools` 内置本工具使用的六个共享运行模块，以保证复制目录即可运行。
修改仓库根目录对应模块时同步更新这些文件；回归测试检查两份源码一致，避免
单目录版本和开发环境使用不同逻辑。用户无需执行同步或构建步骤。
