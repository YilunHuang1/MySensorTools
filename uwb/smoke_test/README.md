# UWB 冒烟测试工具

供应商交付新 UWB 固件（Anchor D6）和信令固件（Tag D5）后的冒烟测试工具。

## 两种模式

| 模式 | 说明 | 使用场景 |
|------|------|----------|
| `standalone` | 停止 `uwb` 服务，直接串口验证 Anchor | 新固件首次验证、产线测试 |
| `online` | 利用 ROS2 接口，不停服务 | 日常巡检、持续监控 |

## 依赖

```bash
pip install pyserial pyyaml
```

## 使用方式

### Standalone 模式（需停服务，仅验证 Anchor）

```bash
# 先停止 uwb 服务
systemctl stop uwb

# 运行测试（默认串口 /dev/ttyS7）
python3 uwb_smoke_test.py --mode standalone

# 指定串口
python3 uwb_smoke_test.py --mode standalone --serial-port /dev/ttyS7

# 测试完成后重启服务
systemctl start uwb
```

### Online 模式（不停服务，需 source 环境）

```bash
source /app/script/env.sh
python3 uwb_smoke_test.py --mode online

# 指定测距采集时长（秒）
python3 uwb_smoke_test.py --mode online --ranging-duration 15
```

### 通用选项

```bash
# 指定报告输出目录
python3 uwb_smoke_test.py --mode standalone --output-dir ./reports

# 显示详细日志
python3 uwb_smoke_test.py --mode online -v
```

## 检查项

| # | 检查项 | standalone | online |
|---|--------|:---:|:---:|
| 1 | 串口通信 | ✅ | - |
| 2 | Anchor 版本 | ✅ | ✅ |
| 3 | Anchor 重启恢复 | ✅ | - |
| 4 | 心跳检测 | ✅ | - |
| 5 | 错误状态 | ✅ | ✅ |
| 6 | CRC 校验完整性 | ✅ | - |
| 7 | Tag 版本 | - | ✅ |
| 8 | Tag 状态/电量 | - | ✅ |
| 9 | 测距功能 | - | ✅ |
| 10 | 数据质量 | - | ✅ |

## 报告

测试完成后会在终端输出结果摘要，并生成 JSON 报告文件：
`smoke_test_report_YYYYMMDD_HHMMSS.json`



online测试说明
1. Anchor 版本 — 5.1.35
调用 ROS2 service uwb/get_device_info，传参 {target_device_type: 3}（3 = Anchor），解析响应里的 sw_version 字段，与最低版本 5.0.24 比较。

2. Tag 版本 — SW 0.2.22
同上调用 uwb/get_device_info，传参 {target_device_type: 2}（2 = Tag），解析 sw_version，与最低版本 0.1.15 比较。

3. Tag 状态/电量 — 电量 77%, 状态 RANGING
订阅 ROS2 topic uwb/tag_status，读取一帧，提取：
battery_level：电量百分比，低于 20% 告警
state：枚举值映射为文字（IDLE / RANGING / ERROR 等），不为 ERROR 即 PASS

4. 测距功能 — 帧率 20.8Hz
订阅 uwb/uwb_data topic，采集 10 秒（可 --ranging-duration 调整），统计收到的帧数： 
帧率 ≥ 10Hz 即 PASS，验证 Anchor ↔ Tag 测距链路正常工作。

5. 数据质量 — 230帧; 距离均值 0.45m; 角度均值 -31.4°; confidence 98; 标准差 0.00m
同样用采集到的 uwb/uwb_data 帧，计算：

距离均值/标准差：标准差 > 0.5m 告警（数据抖动太大）
confidence 均值：< 50 告警（信号质量差）
角度均值：仅展示，不判断（取决于摆放位置）
标准差 0.00m + confidence 98 说明信号质量极好（Tag 就在 Anchor 旁边）。

6. 错误状态 — 无异常状态上报
订阅 uwb/error_status topic，监听 3 秒，检查是否有错误帧上报（error_code ≠ 0）。
与 standalone 的区别：standalone 直接从串口抓 0xC7 TLV，online 是从 uwb_node 解析后透传出来的 ROS2 topic，验证的是软件栈端到端的错误传递链路。

standalone测试说明
1. 串口通信 — 响应延迟 23ms
发送一个 Reboot 命令帧（TLV type=0x05）到串口，然后计时等待 Anchor 回复 DeviceRestartInfo（0x53）。

从发送到收到回复的时间 = 响应延迟。说明串口物理链路通，且 Anchor 固件在响应命令。

2. Anchor 版本 — 5.1.35 (≥ 5.0.24)
解析第 1 步收到的 0x53 DeviceRestartInfo TLV 里的版本字段（sw_version），与代码里内置的最低版本常量 MIN_ANCHOR_VERSION = "5.0.24" 做语义版本比较（major.minor.patch）。

3. Anchor 重启恢复 — 重启后 0.0s 恢复
再次主动发 Reboot 命令（0x05），记录发送时间，然后监听串口等待新的 0x53 DeviceRestartInfo。

收到的时刻 − 发送时刻 = 恢复耗时。验证固件重启后能正常自举并上报版本信息。

4. Anchor 心跳 — 5 个心跳 (1.0Hz)
监听串口 5 秒，统计收到的 0x59 Heartbeat TLV 数量，并计算实际频率。

Anchor 固件规格是 1Hz 心跳，收到 ≥ 4 个且频率在 0.8~1.2Hz 范围内即 PASS。验证固件运行稳定、没有卡死。

5. 错误状态 — 无错误
同样在监听串口期间，检查是否收到 0xC7 Error Status TLV。

该 TLV 是 Anchor 固件主动上报的异常包（如测距超时、硬件故障等）。5 秒内没有收到 = 无错误。

6. CRC 校验完整性 — 0/7 CRC 失败
对监听期间收到的所有帧，用 CRC-16-XMODEM 算法重新计算帧内容的校验值，与帧尾附带的 CRC 字段对比。

失败帧数/总帧数 = CRC 错误率。不为 0 说明串口存在误码（线缆质量差、波特率偏差、EMI 干扰等）。
