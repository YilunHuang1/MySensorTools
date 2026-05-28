# LiDAR 时间戳范围过滤使用指南

## 功能说明

`extract_lidar_pcd_with_ts.py` 现已支持按时间戳范围过滤数据，方便在大型 MCAP 文件中快速提取特定时间段的 LiDAR 数据。

## 配置方法

在文件中修改 `TIMESTAMP_RANGE` 参数：

```python
# 选项1：解析全部数据（默认）
TIMESTAMP_RANGE = None

# 选项2：只解析指定时间范围的数据
TIMESTAMP_RANGE = (start_unix_ts, end_unix_ts)
```

其中 `start_unix_ts` 和 `end_unix_ts` 是 Unix 时间戳（秒为单位，支持小数）。

## 常见用例

### 用例1：提取问题时间段（S100 LiDAR 掉帧事件）

日志中出现掉帧：
```
[1778051475.170906915] [INFO] [vita_slam]: Drop LiDAR frame: ldr_beg=1778051474.904293 < imu_boundary=1778051474.994741
```

问题发生时间段：15:11:14.048 ~ 15:11:15.170（UTC+8）

对应 Unix 时间戳（已转换为 UTC）：
```python
TIMESTAMP_RANGE = (1778051474.048, 1778051475.170)
```

### 用例2：提取 1 秒的数据用于分析

```python
# 只提取 1778051474.0 ~ 1778051474.1 这 0.1 秒的数据
TIMESTAMP_RANGE = (1778051474.0, 1778051474.1)
```

### 用例3：禁用过滤，解析全部数据

```python
# 这是默认行为，可不设置此项
TIMESTAMP_RANGE = None
```

## 时间戳转换参考

**日志中的时间戳示例：**
```
[1778051474.000301585] [INFO] [vanjee_lidar]: [20260506 15:11:14.000] time_sync.cpp:258
```

- 方括号前：`1778051474.000301585` 是 Unix 时间戳（单位：秒）
- 方括号内：`20260506 15:11:14` 是北京时间（CST=UTC+8）

**转换关系：**
- Unix 时间戳 = 北京时间对应的 UTC 时间戳
- 转换公式：从日期 → Unix 时间戳（使用在线工具或 Python：`import calendar; calendar.timegm(...) - 28800`）

## 工作流程

### 步骤1：从日志找到问题时间

查看日志找到出现问题的时刻：
```bash
grep -n "Drop LiDAR frame" s100_trigger_20260506_144234_0.txt
```

得到时间戳，例如 `1778051475.170906915`

### 步骤2：设置时间范围并运行

修改 `extract_lidar_pcd_with_ts.py`：
```python
TIMESTAMP_RANGE = (1778051474.0, 1778051475.3)   # 留足裕度
SAVE_PCD = True
OUTPUT_DIR = '/path/to/output'
```

### 步骤3：运行提取

```bash
python3 extract_lidar_pcd_with_ts.py
```

### 步骤4：查看结果

- CSV 统计文件：`frame_timestamps_*.csv`
- PCD 文件（如果 SAVE_PCD=True）：`frame_XXXX_*.pcd`

## 性能提示

- **大范围（>10秒）**：可能需要 10~30 秒处理时间
- **小范围（<1秒）**：通常 <1 秒完成
- 建议：先用小范围快速验证，再扩大范围

## 两种模式对比

运行两次，分别用不同的时间戳模式：
```python
# 第一次运行：driver_original 模式（驱动原始逻辑，固定200ms）
TIMESTAMP_MODE = "driver_original"
TIMESTAMP_RANGE = (1778051474.0, 1778051475.3)
# main()

# 第二次运行：per_packet 模式（推荐方案，每包独立时间戳）
TIMESTAMP_MODE = "per_packet"
TIMESTAMP_RANGE = (1778051474.0, 1778051475.3)
# main()
```

生成两个 CSV，对比 `first_point_ts` 列的差异，可直观看到两种模式的时间戳偏差。

## 常见问题

### Q：为什么没有输出任何帧？

A：检查 `TIMESTAMP_RANGE` 是否超出了 MCAP 文件包含的时间范围。
```bash
# 查看 MCAP 中第一个和最后一个包的时间戳
python3 -c "
import sys
sys.path.insert(0, '.')
from extract_lidar_pcd_with_ts import *
from mcap.reader import make_reader
with open(MCAP_FILE, 'rb') as f:
    reader = make_reader(f)
    ts_list = []
    for schema, channel, message in reader.iter_messages(topics=[TOPIC]):
        data = parse_vanjee_packet_cdr(message.data)
        if not data: continue
        for ptype, pkt in extract_sub_packets(data):
            if ptype == 'pointcloud':
                ts = parse_pkt_lidar_ts(pkt)
                if ts: ts_list.append(ts)
    print(f'时间范围: {min(ts_list):.3f} ~ {max(ts_list):.3f}')
"
```

### Q：能同时解析多个时间段吗？

A：暂不支持。如需多个时间段，建议多次运行，每次改一次 `TIMESTAMP_RANGE`。

### Q：MCAP 文件很大，解析很慢？

A：使用 `SAVE_PCD=False` 只输出统计 CSV，速度会快 10 倍。

## 实现细节

时间戳过滤逻辑（伪代码）：
```python
for each_packet in mcap:
    pkt_ts = parse_pkt_lidar_ts(pkt)
    if TIMESTAMP_RANGE is not None:
        start_ts, end_ts = TIMESTAMP_RANGE
        if not (start_ts <= pkt_ts <= end_ts):
            continue  # 跳过此包
    # 处理此包
```

- 过滤在包级别执行，不会跳过已处理的帧
- 如果帧跨越时间范围边界，会被完整处理（帧内所有包都在范围内时）
