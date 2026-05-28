# Vita 传感器 Skills 使用指南

这份文档是给人看的。仓库内 skill 参考源文件在 `docs/codex_sensor_skills`，安装后的 Codex 运行副本通常在 `~/.codex/skills`。

## 目录说明

- 仓库内 skill 参考目录：`docs/codex_sensor_skills`
- Codex 自动触发目录：`~/.codex/skills`
- IMU 分析脚本：`imu/mcap_analysis/analyze_imu_mcap.py`
- 标准化问题 case：建议放在仓库外的数据目录，避免提交原始数据

## 怎么查看 Skills

查看当前项目里有哪些 skill：

```bash
find docs/codex_sensor_skills -maxdepth 1 -type d | sort
```

查看某个 skill 的说明：

```bash
sed -n '1,220p' docs/codex_sensor_skills/vita-sensor-debug/SKILL.md
```

查看某个 skill 包含哪些文件：

```bash
find docs/codex_sensor_skills/imu-mcap-analysis -maxdepth 3 -type f | sort
```

查看已安装到 Codex 的 skill：

```bash
find ~/.codex/skills -maxdepth 2 -name SKILL.md | sort
```

## 推荐使用方式

你通常不需要手动运行 skill。更推荐先创建标准化问题 case，然后让 Codex 用 `vita-sensor-debug` 分析。

创建 case：

```bash
python3 common/create_debug_case.py \
  --time "YYYY-MM-DD HH:MM:SS.mmm" \
  --symptom "一句话描述问题" \
  /path/to/problem_data_or_screenshot_folder
```

然后让 Codex 分析：

```text
用 vita-sensor-debug 分析 debug_cases/<case_id>
```

如果你不想手动跑脚本，也可以直接把问题数据放到一个文件夹，然后告诉 Codex：

```text
帮我从 /path/to/problem_data 创建 debug case，然后用 vita-sensor-debug 分析
```

## 常用提问模板

总入口分诊：

```text
用 vita-sensor-debug 先分诊这个 mcap，问题时间是 2026-05-13 14:24:54.240 CST。
```

IMU：

```text
用 imu-mcap-analysis 分析这个 IMU_DATA_ANOMALY，确认是 /imu_raw 还是中间转换问题。
```

LiDAR：

```text
用 lidar-debug 看 /lidar_points 为什么有 200ms 时间戳异常。
```

双目：

```text
用 stereo-debug 看左右目 H265/NV12 是否同步，问题时间是 ...
```

红外：

```text
用 infrared-debug 看红外 raw 正常但 video_h265 没有输出的原因。
```

UWB：

```text
用 uwb-debug 看 /uwb/data 正常但跟随卡顿的原因。
```

## 当前 Skills 清单

| Skill | 角色 | 适合解决的问题 |
| --- | --- | --- |
| `vita-sensor-debug` | 总入口和分诊 | 不确定是哪个传感器、多个传感器同时异常、需要先判断该走哪个专项 skill |
| `robot-rosbag-log-triage` | bag/log 时间线整理 | MCAP/rosbag topic 清单、`/x5/vlog` 和 `/s100/vlog` 对齐、fault/restore 时间线 |
| `imu-mcap-analysis` | IMU 深挖 | `IMU_DATA_ANOMALY`、`/imu_raw`、`/imu_raw_x5`、`/lidar_imu`、acc norm、VQF/raw/SPI/publish 链路 |
| `lidar-debug` | LiDAR 深挖 | `/lidar_points`、`/lidar_imu`、VanJee 驱动、点云为空/稀疏、RTC/time sync |
| `stereo-debug` | X5 双目深挖 | `/image_left_raw/*`、`/image_right_raw/*`、H265/NV12、ISP 状态、左右目时间同步 |
| `infrared-debug` | 红外相机深挖 | `/infrared_camera/image_raw`、`/infrared_camera/video_h265`、SC202CS、红外补光、QR/充电感知 |
| `uwb-debug` | UWB 深挖 | `/uwb/data`、`/uwb/state`、BLE 配对、anchor/tag、帧率、link timeout、head touch |

## 推荐排查流程

1. 如果不确定问题归属，先用 `vita-sensor-debug`。
2. 如果有 MCAP、rosbag 或日志，先用 `robot-rosbag-log-triage` 建时间线。
3. 明确主嫌疑传感器后，再进入对应专项 skill。
4. 如果第一个传感器被证明正常，再回到 `vita-sensor-debug` 重新路由。

## 最好提供哪些信息

- 问题发生的精确 CST 时间，最好带毫秒。
- MCAP、rosbag 或日志路径。
- fault 名称、fault id 和附近日志。
- 机器狗当时在做什么，比如静止、走路、过减速带、碰撞、充电、跟随。
- 问题是否能现场复现，还是只在记录包里出现。
- 这台机器是否有特殊配置、固件、参数或 so 替换。

## 标准化 Case 目录

每个问题建议一个目录：

```text
debug_cases/<case_id>/
  issue.yaml
  data/
  screenshots/
  reports/
```

`issue.yaml` 由 `common/create_debug_case.py` 自动生成。你只要把问题数据放进一个文件夹，脚本会自动：

- 创建 `debug_cases/<case_id>`
- 把 MCAP、日志等放到 `data/`
- 把截图放到 `screenshots/`
- 生成 `issue.yaml`
- 生成 `reports/triage.md` 初始文件
- 根据关键词保守推断 primary skill

默认使用符号链接，不复制大 MCAP，避免重复占用磁盘。

## 后续可以新增的 Skills

这些不是现在必须做，但后续真实问题多了以后值得补。

| 候选 skill | 价值 | 触发场景 |
| --- | --- | --- |
| `vita-fault-debug` | 统一查 fault id/name、上报者、触发条件、恢复逻辑 | “这个 fault id 谁报的”，“FAULT_RESTORE 为什么马上恢复” |
| `vita-time-sync-debug` | 专门处理 header stamp、接收时间、RTC、PPS、MCAP 时间和日志时间对齐 | “时间戳跳变”，“100ms/200ms”，“MCAP 时间和日志对不上” |
| `vita-calibration-debug` | 处理 SLAM/VLN/camera/LiDAR 的内参、外参、GDC、部署参数 | “标定无效”，“换传感器后定位漂”，“左右目/雷达外参” |
| `vita-recorder-debug` | 处理 trigger_data_save、MCAP 录制 topic 缺失、丢包、证据不完整 | “包里没有 topic”，“触发包为什么没录到”，“日志和 mcap 对不上” |
| `vita-deploy-param-debug` | 处理现场机器代码、配置、so、固件、参数没有按预期部署 | “本地代码和机器上不一致”，“配置没生效”，“so 替换后没变化” |
| `vln-follow-debug` | 专门处理跟随卡顿/跟丢，横跨 UWB、LiDAR、双目、标定、function state | “跟随卡顿”，“人跟丢”，“UWB 正常但 VLN 不动” |

## 维护规则

- `docs/codex_sensor_skills` 是仓库内可编辑参考源目录。
- `~/.codex/skills` 是 Codex 自动触发的安装目录。
- 修改 skill 后，需要同步到 `~/.codex/skills` 才能在后续对话自动触发。
- `SKILL.md` 保持简洁；大段代码路径、topic 表、排查细节放进 `references/`。
- Copilot 聊天记录只能当线索，不能当结论；结论必须回到当前 `vita-robot` 代码和实际日志/MCAP 校验。
