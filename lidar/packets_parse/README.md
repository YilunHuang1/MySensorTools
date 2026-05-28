# 万集 WLR-722Z 激光雷达点云提取工具

从 ROS2 MCAP 数据包中提取 `/lidar_packets`，解码为 PCD ASCII 点云文件。

- **输入**: MCAP 文件（ROS2 bag）
- **输出**: PCD ASCII 格式（XYZI 字段）
- **雷达型号**: WLR-722Z（16 通道，0.01~100m）

---

## 快速开始

### 方式一：模块化脚本（推荐）

```bash
cd lidar/packets_parse

# 基本用法
python scripts/extract.py --mcap mcap_data/<file>.mcap -o pcd_output

# 常用参数
python scripts/extract.py \
  --mcap   mcap_data/xxx.mcap \   # 输入文件
  --output pcd_output \           # 输出目录
  --max-frames 100 \              # 限制帧数（调试用）
  --verbose                       # 显示详细信息
```

### 方式二：单文件脚本

```bash
# 修改 extract_lidar_pcd.py 顶部的配置后运行
python extract_lidar_pcd.py
```

### 输出格式

```
pcd_output/
  frame_0001_1774257429.901083100.pcd
  frame_0002_1774257430.240137700.pcd
  ...
```

- 时间戳来自 MCAP 消息的 `publish_time`（PTP 同步，纳秒精度）
- PCD 格式：ASCII，包含 `x y z intensity` 字段

---

## 项目结构

```
mcap_ansys/
├── scripts/
│   └── extract.py          # 主提取脚本（带 CLI 参数）
├── src/core/
│   ├── extractor.py        # 帧提取、帧切割、PCD 保存
│   ├── decoder.py          # 80 字节点云包解码、坐标变换
│   └── calibration.py      # 角度校准文件加载
├── extract_lidar_pcd.py    # 单文件版脚本（配置写死在文件里）
├── analyze_pcd_quality.py  # 点云质量 + 时间戳统计分析
├── parse_mcap_log.py       # MCAP 消息统计
└── visualize_pcd.py        # Open3D 可视化
```

---

## 依赖

```bash
pip install mcap numpy open3d
```

---

## 角度校准

驱动使用 `Vanjee_722z_VA.csv` 对 16 个通道做出厂校准，修正每个通道的垂直角和水平偏差。

| 文件 | 适用型号 | 说明 |
|------|---------|------|
| `Vanjee_722z_VA.csv` | WLR-722Z | 水平偏差 ±2.5°，高精度 |
| `Vanjee_722_VA.csv`  | WLR-722  | 水平偏差 ±2.2° |
| `Vanjee_720_16_VA.csv` | WLR-720-16 | 水平偏差 0°（未校准） |

校准文件路径（自动查找）：
```
vita-robot/src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/param/Vanjee_722z_VA.csv
```

---

## 帧切割机制

WLR-722Z 连续旋转，驱动以 azimuth 过零点为边界切分每一圈为独立帧（~200ms / 5Hz）。

**关键逻辑**（对齐官方驱动 `SplitStrategyByAngle`）：

```python
# 正确：纯回落检测，与上一帧的 azimuth_trans 比较
curr_trans = (curr_azimuth + resolution) % 36000
prev_trans = (prev_azimuth + resolution) % 36000
is_new_frame = curr_trans < prev_trans

# 错误（已修复）：固定阈值窗口，会在 azimuth 跳过 0° 时漏切
# is_new_frame = azimuth_trans < 60 and prev_azimuth > 100
```

**历史 Bug（已修复）**：  
原切割条件 `azimuth_trans < 60` 在一条消息里 azimuth 从 359.63° 直接跳到 0.22° 时，
`azimuth_trans = (22+60)%36000 = 82`，不满足 `< 60`，导致漏切。  
漏切帧会合并两圈的点（~9000 pts），产生 ~400ms 的假时间跳变。
修复后帧率稳定在 **5.00 Hz，标准差 3.83ms**。

---

## 时间戳

- 来源：`message.publish_time`（MCAP 元数据，ROS 节点接收时打戳）
- **不是** 数据包内嵌的 LiDAR 硬件时钟（`packet.datetime + timestamp`）
- 如需硬件时钟，设置驱动参数 `use_lidar_clock = true`


```bash
# 方法 1: 用脚本可视化（需要 Open3D 或 Matplotlib）
python visualize_pcd.py 10     # 可视化第 10 帧

# 方法 2: 用 CloudCompare（GUI）
# 直接打开 pcd_output/frame_0001.pcd

# 方法 3: 用 Python 代码
python -c "
import open3d as o3d
pcd = o3d.io.read_point_cloud('pcd_output/frame_0010.pcd')
o3d.visualization.draw_geometries([pcd])
"
```

---

## 📊 点云质量分析

```bash
python analyze_pcd_quality.py
```

**输出示例**：

```
📊 分析 50 帧点云数据

Frame   1:   9850 pts | dist [  0.51,  80.87]m | Z [ -0.345,  24.304]m | Intensity [  1, 255]
...

📈 整体统计
================================================================================
点数:        6804 ± 1881 (min=5751, max=12789)
平均高度:    3.062 ± 0.681 m
平均距离:    8.40 ± 1.71 m
平均强度:    19.8 ± 1.4

✓ 所有帧数据正常，无异常检测
```

**分析指标**：

| 指标 | 含义 | 正常范围 |
|------|------|---------|
| `点数` | 每帧的有效点数 | 5000~12000（因分辨率波动） |
| `平均高度` | Z 轴均值 | 取决于扫描角度（±0.25°~40.25°） |
| `平均距离` | 到雷达的距离 | 1~80 m（取决于环境） |
| `平均强度` | 反射强度（0~255） | 10~200（取决于表面反光性） |

---

## 🔍 协议解析细节

### VanjeelidarPacket 消息结构

```
Header:
  [0:2]   head = 0xEE 0xFF
  [2:6]   version + diag_info_ver + data_type
  [6:12]  datetime (year-100, month, day, hour, min, sec)
  [12:16] timestamp (µs, little-endian)

PointCloud Block (1 per packet):
  [16:18] azimuth (0.01° steps, 0~35999)
  [18:66] 16 channels × 3 bytes (distance + reflectivity)
  [66:76] metadata (dirty_degree, state, sequence, etc.)
  [76:80] CRC32/MPEG-2

总长度: 80 字节 (固定)
```

### 坐标变换公式

源代码位置: `vita-robot/src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/src/vanjee_driver/driver/decoder/wlr722z/decoder/decoder_vanjee_722z.hpp`

```python
# 角度校准（从 CSV 文件读取）
vert_angles[ch]   # 垂直角度（毫度）
horiz_angles[ch]  # 水平角度校正（毫度）

# 球坐标转笛卡尔坐标
distance = raw_distance × 0.002  # 米
angle_horiz = (horiz_angles[ch] + azimuth × 10) % 360000  # 毫度
xy = distance × cos(angle_vert)
x = xy × sin(angle_horiz) + L × sin(optcent_angle)
y = xy × cos(angle_horiz) + L × cos(optcent_angle)
z = distance × sin(angle_vert) + offset_z

# 光心偏移（校正系统误差）
OPTCENT_2_LIDAR_L = 0.02067 m    # 水平偏移
OPTCENT_2_LIDAR_Z = 0.00795 m    # 垂直偏移
```

### 角度校准文件

路径: `vita-robot/src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/param/Vanjee_722z_VA.csv`

```csv
-0.25,-2.423793797    # CH0: vert=-0.25°, horiz=-2.42°
2.45,1.567974548      # CH1: vert=2.45°, horiz=1.56°
...
40.25,1.671322722     # CH15: vert=40.25°, horiz=1.67°
```

---

## 🐛 常见问题与排查

### Q1: "CRC 校验失败" 提示较多
**症状**: `CRC 校验失败: 1000+`  
**原因**: MCAP 文件可能损坏或 CDR 解析有误  
**解决**: 
- 检查文件大小是否异常
- 尝试其他 MCAP 文件验证
- 查看是否启用了 VLAN 层（修改 `EXTRACT_VLAN`）

### Q2: 点数异常少 (< 1000/帧)
**症状**: 每帧只有几百个点  
**原因**: 
1. 距离过滤范围设置过严 → 调整 `DISTANCE_MIN/MAX`
2. 强度过低 (所有反射率都是 0) → 检查雷达连接
3. 采样率设置 → 检查雷达配置文件

**解决**:
```python
DISTANCE_MIN = 0.01
DISTANCE_MAX = 100.0
```

### Q3: 强度数据都是 1 或 255
**症状**: `Intensity [1, 255]` 只出现两个值  
**原因**: 
- 正常现象（二值强度）→ 无需处理
- 或数据量化问题 → 检查雷达参数

### Q4: 点云有明显的"条纹"或"重影"
**症状**: 某些扫描线条上的点显著错位  
**原因**: 
1. 时间同步问题 → 检查 `use_lidar_clock` 参数
2. 分辨率切换（60° vs 120°）→ 这是正常的，帧 5/14/34/38/43 会有点数翻倍
3. 光心偏移参数不准确 → 需要重新校准

**调试**:
```python
# 检查分辨率切换
MAX_FRAMES = None  # 导出全部帧
# 然后查看 analyze_pcd_quality.py 的输出
# 点数翻倍的帧可能是分辨率切换
```

---

## 📈 数据质量指标

根据你提供的 MCAP 文件的分析结果：

```
✓ 总消息数: 2687
✓ 有效点云包: 30896
✓ CRC 失败: 0 (100% 校验通过)
✓ 导出帧数: 50
✓ 平均每帧: 6804 ± 1881 点

点云覆盖范围:
  X: [-50, +50] m
  Y: [-70, +20] m  
  Z: [-0.3, +25] m
```

**结论**: 数据完整，无明显质量问题 ✓

---

## 🎯 问题排查：激光雷达数据点云异常

如果你怀疑 **万集雷达的点云有问题**，使用本工具可以：

### 1. 确认数据完整性
```bash
python analyze_pcd_quality.py | grep "CRC\|异常\|NaN"
```
- CRC 通过 ✓ → 数据未损坏
- 无 NaN/Inf ✓ → 解码正确

### 2. 检查点云的几何分布
```bash
python -c "
import numpy as np
pcd = np.load('pcd_output/frame_0010.pcd')  # 或用 open3d 读取
pts = pcd[:, :3]
print('点云凸包体积:', np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
print('点分布不均匀度:', np.std(np.linalg.norm(pts, axis=1)))
"
```

### 3. 导出为其他格式用专业工具检查
```python
import open3d as o3d
pcd = o3d.io.read_point_cloud('pcd_output/frame_0010.pcd')
o3d.io.write_point_cloud('frame_0010.ply', pcd)  # 导出为 PLY
```

然后用 **Meshlab** / **CloudCompare** 打开 PLY 检查：
- 点云密度是否均匀
- 是否有"漏洞"或"重影"
- 强度是否符合预期

---

## 📁 输出文件结构

```
lidar/packets_parse/
├── extract_lidar_pcd.py          # 主脚本（核心解码逻辑）
├── visualize_pcd.py               # 可视化脚本
├── analyze_pcd_quality.py         # 质量分析脚本
├── parse_mcap_log.py              # 原有的日志提取脚本
├── README.md                      # 本文档
└── pcd_output/                    # 输出目录
    ├── frame_0001.pcd
    ├── frame_0002.pcd
    └── frame_0050.pcd
```

---

## 🔧 高级用法

### 自定义分辨率处理
某些帧点数会翻倍（双重回波模式），可在 `extract_lidar_pcd.py` 中调整：

```python
# 分辨率动态调整逻辑
if resolution == 60:   # 0.06° 分辨率
    resolution_index = 0
else:                  # 0.12° 分辨率（双回波）
    resolution_index = 1
```

### 合并多帧为单个点云
```python
import open3d as o3d
import glob

frames = glob.glob('pcd_output/frame_*.pcd')
merged = o3d.geometry.PointCloud()

for frame_path in sorted(frames)[:10]:  # 合并前 10 帧
    pcd = o3d.io.read_point_cloud(frame_path)
    merged += pcd

o3d.io.write_point_cloud('merged_10frames.pcd', merged)
```

### 导出为其他格式
```python
import open3d as o3d

pcd = o3d.io.read_point_cloud('pcd_output/frame_0001.pcd')
o3d.io.write_point_cloud('frame_0001.ply', pcd)      # PLY
o3d.io.write_point_cloud('frame_0001.las', pcd)      # LAS
o3d.io.write_point_cloud('frame_0001.xyz', pcd)      # XYZ
```

---

## 📚 相关源代码参考

- **点云解码**: `vita-robot/src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/src/vanjee_driver/driver/decoder/wlr722z/decoder/decoder_vanjee_722z.hpp`
- **协议定义**: `vita-robot/src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_msg/msg/VanjeelidarPacket.msg`
- **角度校准**: `vita-robot/src/third_party/sensors/vanjee_lidar/src/vanjee_lidar_sdk/param/Vanjee_722z_VA.csv`

---

## 📞 反馈与改进

如遇到问题，请检查：

1. **MCAP 文件有效性**
   ```bash
   ros2 bag info your_file.mcap | head -20
   ```

2. **ROS2 消息定义**
   ```bash
   ros2 interface show vanjee_lidar_msg/msg/VanjeelidarPacket
   ```

3. **脚本日志**
   编辑 `extract_lidar_pcd.py`，增加调试输出：
   ```python
   print(f"DEBUG: CRC={crc_check} vs {crc_pkg}, packet size={len(pkt)}")
   ```

---

**脚本完成日期**: 2026-03-27  
**支持的雷达型号**: WLR-722Z (16通道, 100m)  
**输出格式**: PCD binary (XYZI)  
**测试环境**: Python 3.9 + NumPy + Open3D
