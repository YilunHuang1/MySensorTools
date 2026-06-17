# ir_qr_bench_tool 使用手册

红外相机二维码（AprilTag）识别率测试工具。用于评估红外 ISP 画质、补光灯策略和 AprilTag 识别性能。

---

## 工具位置

| 项目 | 路径 |
|------|------|
| 本地备份（macOS） | `~/Desktop/exec/ir_qr_bench_tool/ir_qr_bench_exec` |
| 打包压缩包 | `~/Desktop/exec/ir_qr_bench_tool.tar.gz` |
| 架构 | ARM aarch64（只能在 S100 机器人上运行） |

---

## 红外相机开关控制

### ROS Service 接口

红外相机通过 ROS 2 Service 控制开关，服务名：

```
/infrared_camera/enable   （类型：std_srvs/srv/SetBool）
```

```bash
# 开启红外相机
ros2 service call /infrared_camera/enable std_srvs/srv/SetBool "{data: true}"

# 关闭红外相机
ros2 service call /infrared_camera/enable std_srvs/srv/SetBool "{data: false}"

# 查询当前是否有数据（判断是否已开启）
ros2 topic hz /infrared_camera/image_raw
```

### 话题列表

| 话题 | 类型 | 说明 |
|------|------|------|
| `/infrared_camera/image_raw` | `sensor_msgs/Image` | 原始图像（YUV422/mono8） |
| `/infrared_camera/video_h265` | `foxglove_msgs/CompressedVideo` | H.265 压缩流（Foxglove 可视化用） |

### 当前默认行为（`infrared_camera.json`）

```json
"infrared_camera_config": {
    "initial_enabled": false    ← 配置文件默认关闭
}
```

**⚠️ 但实际上 S100 启动后红外是开着的**，原因是代码中有产线模式判断：

```
EEPROM factory_flag != 0x01（未完成产线下线）
    → 强制 enabled = true，忽略 initial_enabled 配置
    → 日志输出：Factory not offline, forcing infrared enabled
```

也就是说：
- **出货前机器（factory_flag 未写入）**：红外强制开启，`/infrared_camera/enable false` 也**无法关闭**
- **出货后机器（factory_flag = 0x01）**：按 `initial_enabled` 配置决定，且 Service 可以正常控制开关

### 补光灯（IR Light）开关

补光灯由单独的 `ir_light_config` 控制，默认**关闭**，由 lux 阈值自动控制：

```json
"ir_light_config": {
    "enable": false,           ← false = 关闭补光灯功能，灯永远不亮
    "lux_on_threshold": 30,    ← 环境亮度 < 30 时开灯
    "lux_off_threshold": 700,  ← 环境亮度 > 700 时关灯
    "debounce_count_threshold": 3   ← 连续 3 次满足条件才触发，防抖
}
```

如需开启补光灯自动控制，修改配置文件：
```bash
# 在 S100 上找到并修改配置（路径因部署方式而异）
# 将 "enable": false 改为 "enable": true，重启红外节点生效
```

> **注意**：bench 工具的 `--ir-light=on/off/auto` 参数直接控制 GPIO 456，独立于红外节点的自动控制逻辑。

---

## 快速上手

### 1. 部署到 S100

```bash
# 方法 A：直接拷贝目录
scp -r ~/Desktop/exec/ir_qr_bench_tool/ home-s100:/tmp/

# 方法 B：拷贝压缩包后解压
scp ~/Desktop/exec/ir_qr_bench_tool.tar.gz home-s100:/tmp/
ssh home-s100 "cd /tmp && tar -xzf ir_qr_bench_tool.tar.gz"
```

### 2. 在 S100 上运行（最简用法）

```bash
# ssh 进入机器人
ssh home-s100

# 进入工具目录
cd /tmp/ir_qr_bench_tool

# 最基本的一次测试（30 秒，补光灯关闭）
./ir_qr_bench_exec --duration=30 --tag=my_test_01
```

---

## 命令行参数

### 基础参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--tag <name>` | `default` | 本次测试的标签名，会写入 CSV 文件名和报告 |
| `--duration <秒>` | `30` | 测试持续时长（秒），到时自动打印报告 |
| `--target-tag-id <id>` | `2` | 目标 AprilTag ID（充电桩贴纸默认是 id=2） |
| `--margin-threshold <值>` | `50` | 有效检测的 margin 阈值，**与 odom_qr_controller 生产代码一致** |

### 补光灯控制

| 参数 | 说明 |
|------|------|
| `--ir-light=on` | 强制打开 IR 补光灯 |
| `--ir-light=off` | 强制关闭 IR 补光灯（默认） |
| `--ir-light=auto` | 由工具自动根据 lux 阈值控制（模拟生产行为） |

### 图像保存（Debug 用）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--save-failed-frames` | 关闭 | 开启后，保存所有**未检测到目标 tag** 的帧 |
| `--save-annotated` | 关闭 | 开启后，保存带标注框的图像 |
| `--annotated-interval <N>` | `1` | 每 N 帧保存一张标注图（节省磁盘） |
| `--image-save-dir <路径>` | `/tmp/ir_bench_debug` | 图像输出目录 |

---

## 输出说明

### 实时日志（每 1 秒打印一次）

```
[Bench] T=8.1s | total=52 det=52 rate=100.0% (all: 52/52=100.0%) | margin: avg=125.1 min=122.3 max=129.5 std=1.6 | pose: X=0.270±0.171 Y=-0.045±0.036 θ=98.6±7.0 | IR=OFF | AE: exp=3466 again=0 dgain=0 isp=0 lux=18120
```

| 字段 | 含义 |
|------|------|
| `T=8.1s` | 已运行时间 |
| `total=52` | 累计处理总帧数 |
| `det=52` | 检测到目标 tag 的帧数（margin ≥ threshold） |
| `rate=100.0%` | 当前窗口识别率 |
| `margin avg/min/max/std` | AprilTag 检测置信度统计（越高越好，生产阈值 ≥50） |
| `pose X/Y/θ` | 检测到的机器人相对位姿（均值±标准差），X/Y 单位 m，θ 单位 deg |
| `IR=OFF/ON` | 当前补光灯状态 |
| `AE exp/again/dgain/isp/lux` | 相机自动曝光参数（曝光时间、模拟增益、数字增益、ISP 增益、环境亮度） |

### 最终报告（Ctrl+C 或达到 duration 后自动打印）

```
╔══════════════════════════════════════════════════╗
║          IR QR Bench - Final Report             ║
╠══════════════════════════════════════════════════╣
║ Tag label : normal_lux_ir_off                    ║
║ Target ID : 2                                    ║
║ Duration  : 30.0                                 ║
║ Total     : 272                                  ║
║ Detected  : 272                                  ║
║ Rate      : 100.0                              % ║
╠══════════════════════════════════════════════════╣
║ Margin  avg=102.2    min=100.8    max=103.5       ║
║         std=0.5                                  ║
╠══════════════════════════════════════════════════╣
║ Pose X  avg=0.108    std=0.000    (m)             ║
║ Pose Y  avg=0.005    std=0.000    (m)             ║
║ Pose θ  avg=88.7     std=0.0      (deg)           ║
╠══════════════════════════════════════════════════╣
║ Max consecutive loss : 0                         ║
╚══════════════════════════════════════════════════╝

========== Margin Threshold Scan ==========
Threshold | Detected | Total | Rate
       20 |      272 |   272 | 100.0%
       30 |      272 |   272 | 100.0%
       40 |      272 |   272 | 100.0%
       50 |      272 |   272 | 100.0%
       60 |      272 |   272 | 100.0%
       70 |      272 |   272 | 100.0%
       80 |      272 |   272 | 100.0%
       90 |      272 |   272 | 100.0%

CSV saved: /tmp/bench_normal_off.csv (272 records)
```

| 字段 | 说明 |
|------|------|
| `Max consecutive loss` | 最大连续丢帧数（0 = 无任何连续丢帧，最佳） |
| `Margin Threshold Scan` | 自动扫描 20~90 各阈值下的识别率，用于评估 ISP 画质裕量 |
| `CSV saved` | 原始数据导出路径，每条记录含时间戳、margin、位姿等 |

---

## 典型测试方案

### 场景一：基准测试（正常光照，补光灯关）

```bash
./ir_qr_bench_exec \
  --ir-light=off \
  --duration=30 \
  --tag=normal_lux_ir_off
```

### 场景二：正常光照下开补光灯

```bash
./ir_qr_bench_exec \
  --ir-light=on \
  --duration=30 \
  --tag=normal_lux_ir_on
```

### 场景三：低光/遮光环境下开补光灯（最真实的回充场景）

```bash
# 先用遮光布遮住机器人顶部，模拟低光环境
./ir_qr_bench_exec \
  --ir-light=on \
  --duration=30 \
  --tag=low_lux_ir_on
```

### 场景四：Auto 模式（模拟生产行为）

```bash
./ir_qr_bench_exec \
  --ir-light=auto \
  --duration=60 \
  --tag=auto_mode_validation
```

### 场景五：带图像保存的完整 Debug 测试

```bash
./ir_qr_bench_exec \
  --ir-light=on \
  --duration=60 \
  --save-failed-frames \
  --save-annotated \
  --annotated-interval=5 \
  --image-save-dir=/tmp/ir_debug \
  --tag=full_debug_run
```

---

## 标注图解读（`--save-annotated` 模式）

| 颜色 | 含义 |
|------|------|
| 🟢 绿框 | 目标 tag（id=2），margin ≥ threshold，**有效检测** |
| 🟡 黄框 | 目标 tag（id=2），但 margin < threshold，被过滤 |
| 🔴 红框 | 非目标 tag（干扰 tag，被忽略） |
| 左上角文字 | 当前 `IR=ON/OFF`、位姿 X/Y/θ 信息 |
| 框内文字 | `id=X m=125.3`（tag ID 和 margin 值） |

---

## 结果拷贝回本地

```bash
# 拷贝图片
scp -r home-s100:/tmp/ir_debug ~/Downloads/ir_debug_$(date +%Y%m%d_%H%M%S)

# 拷贝 CSV 数据
scp home-s100:/tmp/bench_*.csv ~/Downloads/
```

---

## 判断标准参考

| 指标 | 优秀 | 可接受 | 需关注 |
|------|------|--------|--------|
| 识别率（margin≥50） | ≥ 99% | ≥ 95% | < 95% |
| Margin 均值 | ≥ 100 | ≥ 50 | < 50 |
| Margin 标准差 | < 5 | < 15 | ≥ 15 |
| Max consecutive loss | 0 | ≤ 2 | > 2 |

> **说明**：生产代码 `odom_qr_controller` 的硬编码阈值为 `margin ≥ 50`，因此 bench 测试也应以 `--margin-threshold=50` 作为主要指标。

---

## 背景知识

### 为什么不是普通 QR Code？

本工具识别的是 **AprilTag 3（tagCircle21h7 家族）**，不是普通二维码。

- 每个 tag 内部编码 21-bit ID（最多支持 524288 个不同 ID）
- 专为低分辨率、运动模糊、近红外等恶劣条件设计
- 输出 **亚像素精度位姿**（X、Y、θ），可直接用于导航
- 你的充电桩贴纸 = `tagCircle21h7, id=2`

### margin 是什么？

AprilTag 检测器在解码二维码时，会计算每个候选 bit 的黑白分界点置信度，`decision_margin` 是这个置信度的综合评分：
- `> 100`：图像清晰，检测可靠性极高
- `50~100`：正常范围，可用于生产
- `< 50`：图像质量差（过曝/模糊/遮挡），`odom_qr_controller` 会拒绝这帧

---

## 常见问题

**Q: 运行后没有任何输出，直接退出？**
- 检查红外相机 `/infrared_camera/image_raw` 话题是否有数据：`ros2 topic hz /infrared_camera/image_raw`

**Q: 识别率低但 margin 不低？**
- 可能是 `--target-tag-id` 设置错误，用 `--save-annotated` 查看实际检测到的 ID

**Q: margin 总是 0 或识别率 0？**
- 检查贴纸是否是 `tagCircle21h7` 格式（不是 QR Code，也不是 ArUco）
- 检查贴纸打印质量，确保使用含碳黑的油墨（普通激光打印机即可）

**Q: Pose X/Y 的 std 很大？**
- 测试时机器人或充电桩在移动，保持静止可得到更准确的 std 评估
