# LiDAR 时间戳异常排查 Skill

## 适用场景

- vita_slam 报 `Drop LiDAR frame: ldr_beg < imu_boundary`
- LiDAR 帧时间戳重叠
- 点云帧持续时间异常（不是标准 200ms）
- `point cloud loss N packets` / `1/599 packet split problem` 频繁出现

## 设备信息

| 项目 | 值 |
|------|-----|
| LiDAR 型号 | Vanjee 722Z（万集） |
| 通道数 | 16 |
| 标准帧包数 | 600（实际可能599，编码器偏心导致） |
| 标准帧时间 | 200ms |
| 方位角范围 | 0 ~ 35999（分辨率60，即 0/60/120/.../35940） |
| 时钟源 | use_lidar_clock: true → 使用 LiDAR 硬件 PPS/NMEA 同步时钟 |

## 关键配置参数

```yaml
# vanjee_lidar config.yaml
use_lidar_clock: true        # 使用LiDAR硬件时钟
ts_first_point: true         # 点时间戳从帧起始算起
use_offset_timestamp: false  # 不使用偏移模式，绝对时间戳
dense_points: false          # 无效点设NAN

# vita_slam slam.yaml
timestamp_unit: 0            # kSec, time_unit_scale_ = 1e3
```

## 核心代码路径

### 1. LiDAR 驱动解码器
**文件**: `src/third_party/sensors/vanjee_lidar/.../decoder_vanjee_722z.hpp`

#### 分帧逻辑（两种路径）

**Line 685 - 异常分帧**（azimuth=0 跨帧触发）：
```cpp
if (this->split_strategy_->newBlock(azimuth_trans) && azimuth_trans >= resolution) {
    // 触发条件：azimuth_trans 跨过了0°且>=resolution
    // 说明当前包的 azimuth 接近0但帧末尾不在35940
    uint32_t point_gap_num = (azimuth / resolution) * 16;
    this->last_point_ts_ = pkt_ts - all_points[point_gap_num];
    this->first_point_ts_ = last_point_ts_ - all_points[size-1];
    this->cb_split_frame_(...);
}
```

**Line 784 - 正常分帧**（azimuth_trans < resolution，即正常到帧尾）：
```cpp
if (azimuth_trans < resolution) {
    if (((pre_hor_angle_ + resolution) % 36000) < resolution) {
        // 1/599 问题：上一包也在帧尾附近 → clear
        this->point_cloud_->points.clear();
    } else {
        // 正常帧结束
        this->last_point_ts_ = pkt_ts;
        this->first_point_ts_ = pkt_ts - all_points[size-1];
        this->cb_split_frame_(...);
    }
}
```

#### 时间戳公式的核心问题

`first_point_ts_ = last_point_ts_ - all_points[size-1]`

- `all_points[size-1]` 是**固定值 ≈ 199.98ms**（预计算的最后一个点相对帧起始的时间偏移）
- 这意味着 **帧起始时间 = 帧结束时间 - 固定200ms**
- **如果实际帧持续时间 ≠ 200ms，倒推出的 first_point_ts_ 就是错的**

### 2. vita_slam 消费端
**文件**: `src/application/vita_slam/vs_ego/ego_motion.cpp`

```cpp
// Line 672-676: Drop 判断
if (ldr_buf.front()->stamp_ < imu_boundary_ts) {
    // Drop! 帧的起始时间 < IMU 边界
}

// Line 689-696: 帧结束时间
// 使用 points.back().curvature/1000 作为帧持续时间
// 如果 < 0.5*mean_scantime 则用 mean_scantime 替代
```

**文件**: `src/application/vita_slam/vs_base/vs_sensor/lidar/ldr_model.hpp`

```cpp
// Line 96: 判断点云是否有时间戳
given_offset_time_ = pl_orig->points[plsize-1].timestamp > DBL_EPSILON

// Line 121-122: curvature = (points[i].timestamp - pl_start_time) * time_unit_scale_
// 存储的是相对帧起始的时间(ms)

// Line 125-128: 过滤
// if (i % point_filter_num_ == 0) AND if (x²+y²+z² > blind²)
// blind 过滤会导致 pcl_out 的最后一个点不一定是帧的最后时刻
```

### 3. 驱动 → SLAM 的时间戳转换
**文件**: `src/third_party/sensors/vanjee_lidar/.../lidar_driver_impl.hpp`

```cpp
// Line 539: splitFrame() 中
// use_offset_timestamp=false 时，每个点的时间戳转为绝对时间：
// setTimestamp(pt, first_point_ts_ + relative_ts)
```

## 排查流程

### Step 1: 确认症状

从日志中搜索关键字：
```bash
grep -n "Drop LiDAR frame\|point cloud loss\|1/599\|ldr ts:" <logfile>
```

关注：
- `Drop LiDAR frame: ldr_beg=X < imu_boundary=Y` → 帧起始时间异常
- `ldr ts: A - B, imu_size: N` → 帧时间范围和IMU数量
- 两帧 ldr_beg 间隔是否 ≈ 200ms

### Step 2: 区分两种 loss 报警

| 报警 | 含义 | 影响时间戳？ |
|------|------|------------|
| `point cloud: loss N packets` (line 617) | sequence_num 不连续，真正传输丢包 | ❌ 不影响 |
| `point cloud loss N packets` (line 687) | azimuth=0 触发异常分帧 | ⚠️ **触发 bug 公式** |
| `1/599 packet split problem` (line 785) | 连续两包都在帧尾，清空点云 | ❌ 清空后重来 |

**注意**：line 687 打印的 `loss_packets_num` 是复用序号差，不代表真丢包。

### Step 3: 分析时间戳重叠

从 `ldr ts:` 日志提取连续帧信息：
```
帧1: ldr ts: A1 - B1   → first_point_ts = A1, 实际beg用points[0]
帧2: ldr ts: A2 - B2
```

检查：
- `A2 - A1` 是否 ≈ 200ms？如果 < 200ms → 时间戳重叠
- `B1` 和 `A2` 是否有间隙？如果 `A2 < B1` → 帧重叠

### Step 4: 确认根因

#### 4a. 电机转速不均（已确认的根因）

LiDAR 电机受震动影响，某一帧实际转了不到200ms：
```
正常: 帧N结束时刻=T, 帧N+1结束时刻=T+200ms
异常: 帧N结束时刻=T, 帧N+1结束时刻=T+150ms（转快了）

倒推公式:
帧N   first_point_ts = T - 200ms = T-200ms ✓
帧N+1 first_point_ts = (T+150ms) - 200ms = T-50ms  ← 与帧N重叠！
```

**佐证**：
- 日志中有碰撞/大幅动作
- IMU 数据异常 `acc_norm` 偏离
- 连续帧间隔 < 200ms
- 电机调速 jitter 增大

#### 4b. 系统调度延迟（加重因素）

- lowlevel 崩溃/重启导致 CPU 负载
- 解码线程积压，多帧连续处理
- 不改变 LiDAR 时间戳本身，但导致 vita_slam 处理延迟，imu_boundary 推进

### Step 5: 验证

1. 检查 Drop 前后是否有 `point cloud loss 1 packets`（line687）
2. 检查是否同时有 lowlevel/locomotion 异常
3. 计算两次 line687 触发的 pkt_ts 差值是否 < 200ms
4. 检查 PPS/NMEA 同步是否正常（每秒一次，不应跳变）

## 已确认的问题与解决方案

### 问题本质

LiDAR 驱动用**固定 200ms** 倒推帧起始时间，但电机实际转速可能因震动而波动，导致帧实际持续时间 ≠ 200ms。

### 解决方案（待万集实施）

1. **驱动侧**：不再用 `pkt_ts - 固定偏移` 倒推，改为给每个点赋予**真实绝对时间戳**
2. **固件侧**：LiDAR 固件提供每包的精确时间（当前每包已有时间戳字段，确认精度是否足够）
3. **验证**：升级后检查连续帧 `first_point_ts` 间隔是否贴合实际

### 临时规避

- vita_slam 侧可增加帧重叠检测：如果 `ldr_beg < 上一帧 ldr_end`，跳过而非 drop
- 或放宽 `imu_boundary` 的计算，增加容忍度

## 参考日志模式

### 正常帧
```
ldr ts: 1778051474.700000 - 1778051474.900000  (200ms)
ldr ts: 1778051474.900000 - 1778051475.100000  (200ms, 无间隙)
```

### 异常帧（时间戳重叠导致 Drop）
```
[vanjee_lidar] point cloud loss 1 packets        ← line687 异常分帧
ldr ts: 1778051474.898089 - 1778051475.097943   (≈200ms)
[vanjee_lidar] point cloud loss 1 packets        ← 又一次异常分帧
Drop LiDAR frame: ldr_beg=1778051474.904293 < imu_boundary=1778051474.994741
ldr ts: 1778051475.000307 - 1778051475.194202   (≈194ms)
Drop LiDAR frame: ldr_beg=1778051475.009723 < imu_boundary=1778051475.096221
```

关键信号：两次分帧间隔 ≈ 100ms（应为 200ms），说明第二帧实际只转了约 100ms。

## 厂商信息

- 厂商确认 599 包帧是编码器偏心导致的正常现象
- `point cloud: loss N packets`（序号不连续）是驱动层检测，丢包不影响时间戳解析
- `point cloud loss N packets`（line687）是帧分割逻辑，与 599 包帧无关
- 时间戳问题根因是驱动倒推公式假设帧持续时间恒定 200ms

## 工具与命令

```bash
# 搜索关键事件
grep -n "Drop LiDAR\|point cloud loss\|1/599\|ldr ts:" logfile

# 统计各类事件次数
grep -c "point cloud loss" logfile        # line687 异常分帧次数
grep -c "1/599 packet split" logfile      # line785 清空次数
grep -c "Drop LiDAR frame" logfile        # vita_slam丢帧次数

# 提取帧时间戳序列分析
grep "ldr ts:" logfile | awk '{print $6, $8}' > frame_timestamps.txt

# 查找事件前后的系统异常
grep -B5 -A5 "Drop LiDAR" logfile | grep -i "error\|fail\|jitter\|crash"
```

## 相关文件清单

| 文件 | 作用 |
|------|------|
| `decoder_vanjee_722z.hpp` | LiDAR 解码器，分帧+时间戳计算 |
| `lidar_driver_impl.hpp` | 驱动层，点云发布+时间戳转换 |
| `ego_motion.cpp` | vita_slam，帧消费+Drop判断 |
| `ldr_model.hpp` | vita_slam，点云预处理+blind过滤 |
| `config.yaml` (vanjee) | LiDAR 驱动配置 |
| `slam.yaml` | vita_slam 配置 |
