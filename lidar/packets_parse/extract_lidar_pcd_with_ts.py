#!/usr/bin/env python3
"""
万集 WLR-722Z 激光雷达点云提取工具（带时间戳对比版本）

支持三种时间戳模式（可在配置区切换）：

  MODE A: "driver_original" —— 复刻旧驱动代码逻辑（已弃用）
    - 正常分帧: first_point_ts = last_pkt_ts - 固定200ms
    - 每个点绝对时间戳 = first_point_ts + lookup_table[col*16+chan]
    - 缺陷: 假设帧周期恒为200ms，电机震动时会出错

  MODE B: "per_packet" —— 每包独立时间戳（简单方案）
    - 每个点绝对时间戳 = 该包的 pkt_lidar_ts + 行内偏移(chan * 20.8μs)
    - 不依赖固定200ms假设，但分帧逻辑仅用方位角零点

  MODE C: "new_driver" —— 精确复刻新驱动逻辑（v2.2.7+ / commit e914041）
    - 每个点绝对时间戳 = pkt_ts - intra_block_offset[15-chan]
      (pkt_ts 代表包内最后一个通道的发射时刻)
    - 分帧: 同时检测方位角零点穿越 AND azimuth 回跳(split_strategy_->newBlock)
    - 帧时间戳: first_point_ts = 第一个点的时间戳, last_point_ts = 最后一个点的时间戳
    - 与 SLAM 日志中 "ldr ts: xxx - yyy" 完全一致

PCD 输出字段: x, y, z, intensity, timestamp
  timestamp = 点的绝对时间戳（Unix秒，float64）

参考: decoder_vanjee_722z.hpp (commit e914041 "Fix Vanjee 722Z point cloud timestamping")
"""

import struct
import math
import os
import sys
import time
import calendar
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

import numpy as np

# ============================================================
# 配置区
# ============================================================

MCAP_FILE = 'mcap_data/input.mcap'
TOPIC = '/lidar_packets'
OUTPUT_DIR = 'pcd_output_with_ts'
ANGLE_CSV = 'config/calibration/Vanjee_722z_VA.csv'

# ---- 时间戳范围过滤 ----
# 设为 None 表示不过滤，解析全部数据
# 设为 (start_ts, end_ts) 表示只解析该范围内的包（Unix秒）
# 例: (1778051474.0, 1778051475.0) 表示只解析 15:11:14 ~ 15:11:15 这 1 秒
# TIMESTAMP_RANGE = None  # 或 (start_ts, end_ts)
# TIMESTAMP_RANGE = (1778051472.048, 1778051478.170)

# ---- 时间戳模式 ----
# "driver_original" : 复刻旧驱动的 200ms 倒推逻辑（已弃用）
# "per_packet"      : 每包独立时间戳（简单方案）
# "new_driver"      : 精确复刻新驱动逻辑（推荐，与 SLAM 日志一致）
TIMESTAMP_MODE = "new_driver"
TIMESTAMP_RANGE = None

# ---- 驱动参数（对应 config.yaml）----
TS_FIRST_POINT = True   # ts_first_point: true
USE_LIDAR_CLOCK = True  # use_lidar_clock: true（使用 LiDAR 硬件时间）

# ---- 输出格式 ----
OUTPUT_BINARY = False   # True=PCD Binary(快), False=PCD ASCII
SAVE_PCD = False         # False=只统计时间戳，不写 PCD 文件（速度更快）

# ---- 其他 ----
MAX_FRAMES = None
DISTANCE_MIN = 0.01
DISTANCE_MAX = 100.0
DISTANCE_RES = 0.002

# ---- 丢包检测 ----
LIDAR_FREQ_HZ = 5                 # LiDAR 转速 5Hz，每帧 200ms
PKT_PER_FRAME = 600               # 正常每帧包数（599 或 600）
FRAME_INTERVAL_MS = 1000.0 / LIDAR_FREQ_HZ   # = 200ms
FRAME_INTERVAL_TOL_MS = 15.0     # 帧间隔容忍偏差（±15ms 内算正常）
PKT_COUNT_MIN = 598               # 每帧最少包数，低于此视为丢包严重

# 光心偏移参数 (来自 C++ 源码)
OPTCENT_2_LIDAR_ARG = 21570
OPTCENT_2_LIDAR_L = 2.067e-2
OPTCENT_2_LIDAR_Z = 7.95e-3

# ============================================================
# 时间偏移量预计算（对应 initLdLuminousMoment）
# ============================================================

LUMINOUS_PERIOD_OF_LD = 3.33333e-4          # 相邻方位角包间隔（秒）= 1/3000s
LUMINOUS_PERIOD_OF_ADJACENT_LD = 2.08333e-5  # 同包内相邻通道间隔（秒）≈ 20.8μs

def build_luminous_moment_table(n_cols: int = 600, n_rows: int = 16) -> np.ndarray:
    """
    构建发光时刻查找表，对应 C++ initLdLuminousMoment()。
    table[col * 16 + row] = col * 3.33333e-4 + row * 2.08333e-5  (秒)
    最后一个元素 [9599] ≈ 200ms，即一帧的总时长。
    """
    cols = np.arange(n_cols, dtype=np.float64)
    rows = np.arange(n_rows, dtype=np.float64)
    table = (cols[:, None] * LUMINOUS_PERIOD_OF_LD +
             rows[None, :] * LUMINOUS_PERIOD_OF_ADJACENT_LD).flatten()
    return table  # shape: (9600,)

LUMINOUS_TABLE = build_luminous_moment_table()
FRAME_DURATION_FIXED = LUMINOUS_TABLE[-1]  # ≈ 0.19998s ≈ 200ms

# ============================================================
# 新驱动 intra-block 时间偏移表
# 对应 C++ all_points_luminous_moment_serial_[resolution_index][offset]
# pkt_ts 代表包内最后一个通道(chan=15)的发射时刻
# timestamp_point = pkt_ts - INTRA_BLOCK_OFFSET[15 - chan]
# ============================================================
INTRA_BLOCK_OFFSET = np.array([i * LUMINOUS_PERIOD_OF_ADJACENT_LD for i in range(16)], dtype=np.float64)
# INTRA_BLOCK_OFFSET[0] = 0 (chan=15, last channel, = pkt_ts)
# INTRA_BLOCK_OFFSET[15] = 15 * 20.8μs ≈ 312μs (chan=0, first channel)

# ============================================================
# 角度校准 & 三角函数表
# ============================================================

def load_angle_calibration(csv_path: str):
    vert_angles, horiz_angles = [], []
    with open(csv_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            vert_angles.append(int(float(parts[0]) * 1000))
            horiz_angles.append(int(float(parts[1]) * 1000))
    return vert_angles, horiz_angles


_cos_table = None
_sin_table = None

def init_trig_tables():
    global _cos_table, _sin_table
    angles_rad = np.arange(360000) * math.pi / 180000.0
    _cos_table = np.cos(angles_rad).astype(np.float32)
    _sin_table = np.sin(angles_rad).astype(np.float32)

def COS(a): return _cos_table[a % 360000]
def SIN(a): return _sin_table[a % 360000]

# ============================================================
# CRC (MPEG-2 variant, table-accelerated)
# ============================================================

def _build_crc32_mpeg2_table():
    table = []
    for i in range(256):
        crc = i << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
        table.append(crc)
    return table

_CRC32_MPEG2_TABLE = _build_crc32_mpeg2_table()

def crc32_mpeg2_padded(data: bytes, length: int) -> int:
    crc = 0xFFFFFFFF
    table = _CRC32_MPEG2_TABLE
    for i in range(length):
        crc = ((crc << 8) ^ table[((crc >> 24) ^ data[i]) & 0xFF]) & 0xFFFFFFFF
    return crc

# ============================================================
# 包解析（带时间戳）
# ============================================================

def parse_pkt_lidar_ts(pkt: bytes) -> Optional[float]:
    """
    从 80 字节点云包中解析 LiDAR 硬件时间戳。
    对应 C++:
        WJTimestampYMD tm{ (uint8_t)(datetime[0]-100), ... }
        usec = timestamp[0..3] * 1e-6
        pkt_lidar_ts = parseTimeYMD(&tm) * 1e-6 + usec
    
    返回 None 表示时间戳解析失败（数据损坏）
    """
    try:
        year  = pkt[6] - 100 + 2000  # datetime[0] - 100 得到年份后两位，+2000
        month = pkt[7]
        day   = pkt[8]
        hour  = pkt[9]
        minute = pkt[10]
        second = pkt[11]

        # 数据合法性检查
        if not (2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31 and 
                0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
            return None

        # 转为 Unix 时间戳（秒）
        # 注意：Vanjee 722Z datetime 字段存储的是北京时间（CST=UTC+8），
        # 用 calendar.timegm 按 UTC 解析后需减去 8 小时（28800s）
        t = calendar.timegm((year, month, day, hour, minute, second, 0, 0, 0))

        # 微秒字段（小端 uint32）
        usec = struct.unpack_from('<I', pkt, 12)[0] * 1e-6

        return float(t) + usec - 28800  # CST -> UTC 修正
    except (struct.error, ValueError, OverflowError):
        return None


@dataclass
class PointWithTs:
    x: float
    y: float
    z: float
    intensity: float
    timestamp: float   # 绝对时间戳（秒）


def decode_point_cloud_packet_with_ts(
    pkt: bytes,
    vert_angles: List[int],
    horiz_angles: List[int],
    resolution: int = 60,
    ts_mode: str = "new_driver",
    first_point_ts: float = 0.0,   # 仅 driver_original 模式使用
) -> Optional[Tuple[int, float, List[PointWithTs]]]:
    """
    解析单个 80 字节点云包，返回 (azimuth, pkt_lidar_ts, [PointWithTs])。

    ts_mode:
      "driver_original": 每个点时间戳 = first_point_ts + lookup_table[col*16+chan]
      "per_packet"      : 每个点时间戳 = pkt_lidar_ts   + chan * 20.8μs
      "new_driver"      : 每个点时间戳 = pkt_lidar_ts   - INTRA_BLOCK_OFFSET[15-chan]
                          (pkt_ts 代表 chan=15 的发射时刻，向前推算早期通道)
    """
    if len(pkt) != 80 or pkt[0] != 0xEE or pkt[1] != 0xFF or pkt[5] != 0x00:
        return None

    crc_check = crc32_mpeg2_padded(pkt, 76)
    crc_pkg = struct.unpack_from('<I', pkt, 76)[0]
    if crc_check != crc_pkg:
        return None

    pkt_lidar_ts = parse_pkt_lidar_ts(pkt)
    if pkt_lidar_ts is None:
        return None  # 时间戳解析失败

    azimuth = struct.unpack_from('<H', pkt, 16)[0] % 36000
    col = azimuth // resolution  # 当前包是第几列（0~599）

    points = []
    for chan in range(16):
        ch_offset = 18 + chan * 3
        dist_raw = struct.unpack_from('<H', pkt, ch_offset)[0]
        reflectivity = pkt[ch_offset + 2]
        distance = dist_raw * DISTANCE_RES

        # ---- 时间戳计算 ----
        if ts_mode == "driver_original":
            # 复刻旧驱动逻辑：first_point_ts 由外部传入（帧末包 pkt_ts - 200ms），
            # 点时间戳 = first_point_ts + lookup_table[col*16+chan]
            point_id = col * 16 + chan
            if TS_FIRST_POINT:
                ts = first_point_ts + LUMINOUS_TABLE[point_id]
            else:
                ts = first_point_ts + LUMINOUS_TABLE[point_id] - FRAME_DURATION_FIXED
        elif ts_mode == "new_driver":
            # 新驱动逻辑 (v2.2.7+):
            # pkt_ts 代表包内最后一个通道 (chan=15) 的发射时刻
            # timestamp_point = pkt_ts - all_points_luminous_moment_serial_[res][15 - chan]
            ts = float(pkt_lidar_ts - INTRA_BLOCK_OFFSET[15 - chan])
        else:
            # per_packet 简单方案：
            # 点时间戳 = 该包的硬件时间戳 + 该通道在包内的时序偏移
            ts = float(pkt_lidar_ts + chan * LUMINOUS_PERIOD_OF_ADJACENT_LD)

        angle_vert = vert_angles[chan]
        angle_horiz_final = (horiz_angles[chan] + azimuth * 10 + 360000) % 360000
        optcent_angle = (azimuth * 10 + OPTCENT_2_LIDAR_ARG + 360000) % 360000

        if DISTANCE_MIN <= distance <= DISTANCE_MAX:
            xy = distance * COS(angle_vert)
            x = xy * SIN(angle_horiz_final) + OPTCENT_2_LIDAR_L * SIN(optcent_angle)
            y = xy * COS(angle_horiz_final) + OPTCENT_2_LIDAR_L * COS(optcent_angle)
            z = distance * SIN(angle_vert) + OPTCENT_2_LIDAR_Z
            points.append(PointWithTs(float(x), float(y), float(z), float(reflectivity), ts))

    return azimuth, pkt_lidar_ts, points


# ============================================================
# CDR 解析
# ============================================================

def parse_vanjee_packet_cdr(raw_data: bytes) -> Optional[bytes]:
    if len(raw_data) < 20:
        return None
    offset = 4  # skip CDR header
    offset += 4  # stamp.sec
    offset += 4  # stamp.nanosec
    str_len = struct.unpack_from('<I', raw_data, offset)[0]
    offset += 4 + str_len
    offset = (offset + 3) & ~3
    data_len = struct.unpack_from('<I', raw_data, offset)[0]
    offset += 4
    return raw_data[offset:offset + data_len]


def extract_sub_packets(data_bytes: bytes) -> List[Tuple[str, bytes]]:
    packets = []
    i = 0
    while i < len(data_bytes):
        if len(data_bytes) - i < 2:
            break
        if data_bytes[i] != 0xEE:
            i += 1
            continue
        if data_bytes[i + 1] == 0xFF:
            if len(data_bytes) - i < 6:
                break
            dt = data_bytes[i + 5]
            if dt == 0x00:
                if len(data_bytes) - i < 80:
                    break
                packets.append(('pointcloud', bytes(data_bytes[i:i+80])))
                i += 80
            elif dt == 0x01:
                if len(data_bytes) - i < 34:
                    break
                i += 34
            else:
                i += 1
        elif data_bytes[i + 1] == 0xDD:
            if len(data_bytes) - i < 41:
                break
            i += 41
        else:
            i += 1
    return packets

# ============================================================
# PCD 保存（带 timestamp 字段）
# ============================================================

def save_pcd_with_timestamp(filepath: str, points: List[PointWithTs], binary: bool = True):
    # 按 timestamp 排序，避免 UDP 乱序导致帧尾少数包先到而时间戳倒跳
    points = sorted(points, key=lambda p: p.timestamp)

    n = len(points)
    arr = np.zeros((n, 5), dtype=np.float64)
    for i, p in enumerate(points):
        arr[i] = [p.x, p.y, p.z, p.intensity, p.timestamp]

    header_lines = [
        "# .PCD v0.7 - Point Cloud Data file format",
        "VERSION 0.7",
        "FIELDS x y z intensity timestamp",
        "SIZE 8 8 8 8 8",
        "TYPE F F F F F",
        "COUNT 1 1 1 1 1",
        f"WIDTH {n}",
        "HEIGHT 1",
        "VIEWPOINT 0 0 0 1 0 0 0",
        f"POINTS {n}",
        "DATA binary" if binary else "DATA ascii",
    ]
    header = "\n".join(header_lines) + "\n"

    with open(filepath, 'wb' if binary else 'w') as f:
        if binary:
            f.write(header.encode('ascii'))
            f.write(arr.astype(np.float64).tobytes())
        else:
            f.write(header)
            for p in points:
                f.write(f"{p.x:.6f} {p.y:.6f} {p.z:.6f} {p.intensity:.0f} {p.timestamp:.9f}\n")

# ============================================================
# 帧级时间戳统计（用于对比两种模式的差异）
# ============================================================

@dataclass
class FrameTimestampStats:
    frame_idx: int
    pcd_filename: str
    first_point_ts: float
    last_point_ts: float
    duration_ms: float
    point_count: int
    ts_mode: str
    pkt_count: int = 0            # 本帧实际收到的包数
    seq_loss_count: int = 0       # 本帧内 sequence_num 跳变次数（丢包次数）
    seq_loss_pkts: int = 0        # 本帧内共丢失的包数（跳变量之和）
    abnormal_split: bool = False  # 是否由 azimuth 回跳触发的异常分帧

def print_frame_stats(stats_list: List[FrameTimestampStats]):
    print(f"\n{'='*80}")
    print(f"帧时间戳统计（模式: {stats_list[0].ts_mode if stats_list else '-'}）")
    print(f"{'帧':>4} {'first_ts':>18} {'时长(ms)':>10} {'包数':>5} {'丢包次数':>8} {'丢包量':>6} {'点数':>6}")
    print(f"{'-'*80}")
    for s in stats_list[:30]:
        loss_flag = " ⚠️" if s.seq_loss_pkts > 0 else ""
        print(f"{s.frame_idx:>4} {s.first_point_ts:>18.6f} {s.duration_ms:>10.2f} "
              f"{s.pkt_count:>5} {s.seq_loss_count:>8} {s.seq_loss_pkts:>6}{loss_flag} {s.point_count:>6}")
    if len(stats_list) > 30:
        print(f"  ... (共 {len(stats_list)} 帧)")

    # 丢包汇总
    total_loss_events = sum(s.seq_loss_count for s in stats_list)
    total_loss_pkts   = sum(s.seq_loss_pkts  for s in stats_list)
    frames_with_loss  = sum(1 for s in stats_list if s.seq_loss_pkts > 0)
    low_pkt_frames    = [s for s in stats_list if s.pkt_count < PKT_COUNT_MIN]
    print(f"\n丢包统计汇总:")
    print(f"  总丢包事件数: {total_loss_events}  总丢失包数: {total_loss_pkts}")
    print(f"  有丢包的帧:   {frames_with_loss} / {len(stats_list)} 帧")
    if low_pkt_frames:
        print(f"  ⚠️  包数 < {PKT_COUNT_MIN} 的帧: {len(low_pkt_frames)} 帧")
        for s in low_pkt_frames[:5]:
            print(f"     帧{s.frame_idx}: {s.pkt_count} 包")

    # 帧间隔统计
    if len(stats_list) >= 2:
        intervals_ms = [(stats_list[i+1].first_point_ts - stats_list[i].first_point_ts) * 1000
                        for i in range(len(stats_list)-1)]
        print(f"\n帧起始时间间隔统计 (期望 {FRAME_INTERVAL_MS:.0f}ms):")
        print(f"  均值: {np.mean(intervals_ms):.2f} ms  标准差: {np.std(intervals_ms):.2f} ms")
        print(f"  最小: {np.min(intervals_ms):.2f} ms  最大: {np.max(intervals_ms):.2f} ms")
        anomalies = [(i, v) for i, v in enumerate(intervals_ms)
                     if abs(v - FRAME_INTERVAL_MS) > FRAME_INTERVAL_TOL_MS]
        if anomalies:
            print(f"\n  ⚠️  帧间隔异常（偏离{FRAME_INTERVAL_MS:.0f}ms超过{FRAME_INTERVAL_TOL_MS:.0f}ms）: {len(anomalies)} 处")
            for idx, v in anomalies[:10]:
                print(f"     帧{stats_list[idx].frame_idx}→{stats_list[idx+1].frame_idx}: {v:.2f} ms")

# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 70)
    print("万集 WLR-722Z 激光雷达点云提取工具（带时间戳对比版）")
    print(f"时间戳模式: {TIMESTAMP_MODE}")
    if TIMESTAMP_MODE == "driver_original":
        print("  → 复刻旧驱动逻辑: first_point_ts = last_pkt_ts - 固定200ms")
    elif TIMESTAMP_MODE == "new_driver":
        print("  → 新驱动逻辑: pkt_ts - intra_block_offset[15-chan]")
        print("    分帧: 方位角零点穿越 + azimuth回跳检测 (split_strategy_->newBlock)")
    else:
        print("  → per_packet: 每个点时间戳 = 该包硬件时间戳 + 行内偏移(chan×20.8μs)")
    print(f"保存PCD: {'是 (ASCII)' if SAVE_PCD and not OUTPUT_BINARY else '是 (Binary)' if SAVE_PCD else '否（仅统计时间戳）'}")
    if TIMESTAMP_RANGE is not None:
        start_ts, end_ts = TIMESTAMP_RANGE
        print(f"时间戳范围: {start_ts:.3f} ~ {end_ts:.3f} (共 {end_ts - start_ts:.1f} 秒)")
    print("=" * 70)

    for path, name in [(MCAP_FILE, "MCAP"), (ANGLE_CSV, "角度校准文件")]:
        if not Path(path).exists():
            print(f"错误: {name} 不存在: {path}")
            sys.exit(1)

    print(f"\n加载角度校准: {ANGLE_CSV}")
    vert_angles, horiz_angles = load_angle_calibration(ANGLE_CSV)
    print(f"  通道数: {len(vert_angles)}")

    print("初始化三角函数查找表...")
    init_trig_tables()

    out_dir = os.path.join(OUTPUT_DIR, TIMESTAMP_MODE)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n读取 MCAP: {MCAP_FILE}")
    print(f"Topic: {TOPIC}")

    try:
        from mcap.reader import make_reader
    except ImportError:
        print("错误: pip install mcap")
        sys.exit(1)

    frame_points: List[PointWithTs] = []
    frame_count = 0
    total_pc_packets = 0
    crc_fail = 0
    prev_azimuth = -1
    prev_azimuth_trans = -1
    first_frame_done = False   # 第一个帧边界前的数据是不完整帧，跳过
    frame_stats: List[FrameTimestampStats] = []

    # driver_original 模式需要积累一帧的包，在帧末计算 first_point_ts
    # 用一个滚动缓冲存储当前帧的所有包，分帧时重算时间戳
    frame_pkts_buffer: List[Tuple[bytes, float]] = []  # (pkt_bytes, pkt_lidar_ts)

    # 丢包检测状态（基于 sequence_num 连续性）
    prev_seq_num: int = -1          # 上一包的 sequence_num（0~65535 循环）
    frame_pkt_count: int = 0        # 当前帧收到的包数
    frame_seq_loss_count: int = 0   # 当前帧内 sequence_num 跳变次数
    frame_seq_loss_pkts: int = 0    # 当前帧内丢失的包数（跳变量之和）
    frame_abnormal_split: bool = False  # 当前帧是否由异常分帧产生

    # new_driver 模式额外状态（精确复刻 C++ decodeMsopPktSerialPointCloud）
    pre_hor_angle_: int = -1        # C++ pre_hor_angle_
    pre_point_cloud_frame_id_: int = -1  # C++ pre_point_cloud_frame_id_ (sequence_num)
    split_strategy_prev_angle_: int = 0  # SplitStrategyByAngle::prev_angle_ 初始化为 0

    t_start = time.time()
    with open(MCAP_FILE, 'rb') as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages(topics=[TOPIC]):
            data_bytes = parse_vanjee_packet_cdr(message.data)
            if not data_bytes:
                continue

            sub_packets = extract_sub_packets(data_bytes)

            for pkt_type, pkt_data in sub_packets:
                if pkt_type != 'pointcloud':
                    continue

                # 解析方位角和硬件时间戳（不依赖模式）
                pkt_lidar_ts = parse_pkt_lidar_ts(pkt_data)
                if pkt_lidar_ts is None:
                    # 包数据损坏，时间戳解析失败，跳过
                    continue

                # ---- 时间戳范围过滤 ----
                if TIMESTAMP_RANGE is not None:
                    start_ts, end_ts = TIMESTAMP_RANGE
                    if not (start_ts <= pkt_lidar_ts <= end_ts):
                        continue

                azimuth = struct.unpack_from('<H', pkt_data, 16)[0] % 36000
                total_pc_packets += 1

                # CRC
                crc_check = crc32_mpeg2_padded(pkt_data, 76)
                crc_pkg = struct.unpack_from('<I', pkt_data, 76)[0]
                if crc_check != crc_pkg:
                    crc_fail += 1
                    continue

                # ---- sequence_num 丢包检测 ----
                seq_num = struct.unpack_from('<H', pkt_data, 74)[0]
                if prev_seq_num >= 0:
                    expected = (prev_seq_num + 1) % 65536
                    if seq_num != expected:
                        loss = (seq_num - prev_seq_num - 1) % 65536
                        frame_seq_loss_count += 1
                        frame_seq_loss_pkts += loss
                prev_seq_num = seq_num
                frame_pkt_count += 1

                # ============================================================
                # new_driver 模式: 精确复刻 C++ decodeMsopPktSerialPointCloud
                # ============================================================
                if TIMESTAMP_MODE == "new_driver":
                    # -- loss_packets_num 计算 (C++ 逻辑) --
                    loss_packets_num = (seq_num + 65536 - pre_point_cloud_frame_id_) % 65536 if pre_point_cloud_frame_id_ >= 0 else 1
                    pre_point_cloud_frame_id_ = seq_num

                    # -- pre_hor_angle_ 初始化 --
                    if pre_hor_angle_ == -1:
                        pre_hor_angle_ = azimuth
                        prev_azimuth = azimuth
                        prev_azimuth_trans = -1
                        continue

                    # -- loss_packets_num >= 300 || == 0: 跳过包 (C++ return false) --
                    if loss_packets_num >= 300 or loss_packets_num == 0:
                        pre_hor_angle_ = azimuth
                        prev_azimuth = azimuth
                        continue

                    # -- 动态 resolution 计算 --
                    resolution = ((azimuth + 36000 - pre_hor_angle_) % 36000) // loss_packets_num if loss_packets_num > 0 else 60
                    if resolution < 90:
                        resolution = 60
                    else:
                        resolution = 120

                    azimuth_trans = (azimuth + resolution) % 36000

                    # -- 分帧检测 1: split_strategy_->newBlock (azimuth回跳) --
                    # C++: if (this->split_strategy_->newBlock(azimuth_trans) && azimuth_trans >= resolution)
                    # SplitStrategyByAngle::newBlock: returns (angle < prev_angle_), 初始 prev_angle_=0
                    new_block = (azimuth_trans < split_strategy_prev_angle_)
                    split_strategy_prev_angle_ = azimuth_trans  # 总是更新

                    abnormal_split = (new_block and azimuth_trans >= resolution)

                    if abnormal_split:
                        # 触发异常分帧
                        if first_frame_done and len(frame_points) > 0:
                            frame_abnormal_split = True
                            # -- normalizeAndSplitFrame: 取 points[0] 和 points[-1] 的时间戳 --
                            frame_count += 1
                            first_ts = frame_points[0].timestamp
                            last_ts = frame_points[-1].timestamp
                            stats = FrameTimestampStats(
                                frame_idx=frame_count, pcd_filename="", first_point_ts=first_ts,
                                last_point_ts=last_ts, duration_ms=(last_ts - first_ts) * 1000,
                                point_count=len(frame_points), ts_mode=TIMESTAMP_MODE,
                                pkt_count=frame_pkt_count, seq_loss_count=frame_seq_loss_count,
                                seq_loss_pkts=frame_seq_loss_pkts, abnormal_split=True,
                            )
                            frame_stats.append(stats)
                            loss_str = f" 丢包:{frame_seq_loss_pkts}" if frame_seq_loss_pkts > 0 else ""
                            pkt_warn = f" ⚠️包数{frame_pkt_count}" if frame_pkt_count < PKT_COUNT_MIN else f" pkts:{frame_pkt_count}"
                            print(f"  帧 {frame_count:4d}: {len(frame_points):6d} 点 | "
                                  f"first={first_ts:.6f} last={last_ts:.6f} dur={stats.duration_ms:.1f}ms"
                                  f"{pkt_warn}{loss_str} ↩️角度回跳分帧 [未保存PCD]")
                            frame_pkt_count = 0
                            frame_seq_loss_count = 0
                            frame_seq_loss_pkts = 0
                            frame_abnormal_split = False
                            frame_points = []
                            frame_pkts_buffer = []
                        elif not first_frame_done:
                            first_frame_done = True
                            frame_points = []
                            frame_pkts_buffer = []
                            frame_pkt_count = 0
                            frame_seq_loss_count = 0
                            frame_seq_loss_pkts = 0

                    # -- 解码当前包的点并累积 --
                    result = decode_point_cloud_packet_with_ts(
                        pkt_data, vert_angles, horiz_angles,
                        resolution=resolution, ts_mode="new_driver",
                    )
                    if result:
                        _, _, pts = result
                        frame_points.extend(pts)
                        frame_pkts_buffer.append((pkt_data, pkt_lidar_ts))

                    # -- 分帧检测 2: 正常零点穿越 azimuth_trans < resolution --
                    if azimuth_trans < resolution:
                        # C++ guard: "1/599 packet split problem"
                        if ((pre_hor_angle_ + resolution) % 36000) < resolution:
                            # 上一包也在零点附近 → 不分帧，清空
                            frame_points = []
                            frame_pkts_buffer = []
                        else:
                            # 正常零点分帧
                            if first_frame_done and len(frame_points) > 0:
                                frame_count += 1
                                first_ts = frame_points[0].timestamp
                                last_ts = frame_points[-1].timestamp
                                stats = FrameTimestampStats(
                                    frame_idx=frame_count, pcd_filename="", first_point_ts=first_ts,
                                    last_point_ts=last_ts, duration_ms=(last_ts - first_ts) * 1000,
                                    point_count=len(frame_points), ts_mode=TIMESTAMP_MODE,
                                    pkt_count=frame_pkt_count, seq_loss_count=frame_seq_loss_count,
                                    seq_loss_pkts=frame_seq_loss_pkts, abnormal_split=False,
                                )
                                frame_stats.append(stats)
                                loss_str = f" 丢包:{frame_seq_loss_pkts}" if frame_seq_loss_pkts > 0 else ""
                                pkt_warn = f" ⚠️包数{frame_pkt_count}" if frame_pkt_count < PKT_COUNT_MIN else f" pkts:{frame_pkt_count}"
                                print(f"  帧 {frame_count:4d}: {len(frame_points):6d} 点 | "
                                      f"first={first_ts:.6f} last={last_ts:.6f} dur={stats.duration_ms:.1f}ms"
                                      f"{pkt_warn}{loss_str} [未保存PCD]")
                                frame_pkt_count = 0
                                frame_seq_loss_count = 0
                                frame_seq_loss_pkts = 0
                                frame_points = []
                                frame_pkts_buffer = []
                            elif not first_frame_done:
                                first_frame_done = True
                                frame_points = []
                                frame_pkts_buffer = []
                                frame_pkt_count = 0
                                frame_seq_loss_count = 0
                                frame_seq_loss_pkts = 0

                    pre_hor_angle_ = azimuth
                    prev_azimuth = azimuth
                    prev_azimuth_trans = azimuth_trans

                    if MAX_FRAMES and frame_count >= MAX_FRAMES:
                        break
                    continue  # new_driver 处理完毕，跳过下面的通用逻辑

                # ============================================================
                # 非 new_driver 模式: 原有逻辑 (driver_original / per_packet)
                # ============================================================
                resolution = 60
                azimuth_trans = (azimuth + resolution) % 36000

                is_frame_end = (prev_azimuth >= 0 and azimuth_trans < prev_azimuth_trans)

                if is_frame_end and len(frame_pkts_buffer) > 0:
                    # 第一个帧边界之前的数据是 MCAP 开头的不完整帧，跳过
                    if not first_frame_done:
                        # MCAP 开头的不完整帧，直接丢弃
                        first_frame_done = True
                        frame_points = []
                        frame_pkts_buffer = []
                        frame_pkt_count = 0
                        frame_seq_loss_count = 0
                        frame_seq_loss_pkts = 0
                        frame_abnormal_split = False
                    else:
                        # 正常分帧：根据模式重算时间戳
                        if TIMESTAMP_MODE == "driver_original":
                            # 复刻驱动: last_pkt_ts = 最后一包的 pkt_lidar_ts
                            last_pkt_ts = frame_pkts_buffer[-1][1]
                            computed_first_point_ts = last_pkt_ts - FRAME_DURATION_FIXED
                            # 重新对每个包计算点时间戳
                            all_points = []
                            for buf_pkt, buf_ts in frame_pkts_buffer:
                                result = decode_point_cloud_packet_with_ts(
                                    buf_pkt, vert_angles, horiz_angles,
                                    resolution=60,
                                    ts_mode="driver_original",
                                    first_point_ts=computed_first_point_ts,
                                )
                                if result:
                                    all_points.extend(result[2])
                            frame_points = all_points
                        # per_packet / new_driver 模式点已经在积累时加好时间戳

                        if len(frame_points) > 0:
                            frame_count += 1
                            ts_values = [p.timestamp for p in frame_points]
                            first_ts = min(ts_values)
                            last_ts = max(ts_values)

                            pcd_name = f"frame_{frame_count:04d}_{first_ts:.6f}.pcd"
                            pcd_path = os.path.join(out_dir, pcd_name)
                            if SAVE_PCD:
                                save_pcd_with_timestamp(pcd_path, frame_points, binary=OUTPUT_BINARY)

                            stats = FrameTimestampStats(
                                frame_idx=frame_count,
                                pcd_filename=pcd_name,
                                first_point_ts=first_ts,
                                last_point_ts=last_ts,
                                duration_ms=(last_ts - first_ts) * 1000,
                                point_count=len(frame_points),
                                ts_mode=TIMESTAMP_MODE,
                                pkt_count=frame_pkt_count,
                                seq_loss_count=frame_seq_loss_count,
                                seq_loss_pkts=frame_seq_loss_pkts,
                                abnormal_split=frame_abnormal_split,
                            )
                            frame_stats.append(stats)
                            loss_str = f" 丢包:{frame_seq_loss_pkts}" if frame_seq_loss_pkts > 0 else ""
                            pkt_warn = f" ⚠️包数{frame_pkt_count}" if frame_pkt_count < PKT_COUNT_MIN else f" pkts:{frame_pkt_count}"
                            split_flag = " ↩️角度回跳分帧" if frame_abnormal_split else ""
                            print(f"  帧 {frame_count:4d}: {len(frame_points):6d} 点 | "
                                  f"first={first_ts:.6f} last={last_ts:.6f} dur={stats.duration_ms:.1f}ms"
                                  f"{pkt_warn}{loss_str}{split_flag}"
                                  + ("" if SAVE_PCD else " [未保存PCD]"))

                        # 重置帧级计数
                        frame_pkt_count = 0
                        frame_seq_loss_count = 0
                        frame_seq_loss_pkts = 0
                        frame_abnormal_split = False
                        frame_points = []
                        frame_pkts_buffer = []

                        if MAX_FRAMES and frame_count >= MAX_FRAMES:
                            break

                # ---- 积累当前包 ----
                if TIMESTAMP_MODE == "driver_original":
                    # driver_original: 先缓存包，分帧时统一计算
                    frame_pkts_buffer.append((pkt_data, pkt_lidar_ts))
                else:
                    # per_packet: 直接计算每个点的时间戳
                    result = decode_point_cloud_packet_with_ts(
                        pkt_data, vert_angles, horiz_angles,
                        resolution=60,
                        ts_mode="per_packet",
                    )
                    if result:
                        _, _, pts = result
                        frame_points.extend(pts)
                        frame_pkts_buffer.append((pkt_data, pkt_lidar_ts))  # 仅用于帧切割

                prev_azimuth = azimuth
                prev_azimuth_trans = azimuth_trans

            if MAX_FRAMES and frame_count >= MAX_FRAMES:
                break

    # 最后一帧
    if frame_points and (MAX_FRAMES is None or frame_count < MAX_FRAMES):
        frame_count += 1
        ts_values = [p.timestamp for p in frame_points]
        first_ts = min(ts_values)
        last_ts = max(ts_values)
        pcd_name = f"frame_{frame_count:04d}_{first_ts:.6f}.pcd"
        pcd_path = os.path.join(out_dir, pcd_name)
        if SAVE_PCD:
            save_pcd_with_timestamp(pcd_path, frame_points, binary=OUTPUT_BINARY)
        frame_stats.append(FrameTimestampStats(frame_count, pcd_name, first_ts, last_ts,
                                               (last_ts - first_ts) * 1000, len(frame_points), TIMESTAMP_MODE))

    t_elapsed = time.time() - t_start

    print(f"\n{'='*70}")
    print(f"提取完成! 耗时: {t_elapsed:.1f}s")
    print(f"  总点云包数: {total_pc_packets}, CRC失败: {crc_fail}, 导出帧: {frame_count}")
    print(f"  输出目录: {out_dir}")

    # 打印时间戳统计
    if frame_stats:
        print_frame_stats(frame_stats)

    # 保存 CSV 统计
    csv_path = os.path.join(out_dir, f"frame_timestamps_{TIMESTAMP_MODE}.csv")
    with open(csv_path, 'w') as f:
        f.write("frame_idx,first_point_ts,last_point_ts,duration_ms,point_count,pkt_count,seq_loss_count,seq_loss_pkts,abnormal_split,pcd_file\n")
        for s in frame_stats:
            f.write(f"{s.frame_idx},{s.first_point_ts:.9f},{s.last_point_ts:.9f},"
                    f"{s.duration_ms:.3f},{s.point_count},{s.pkt_count},"
                    f"{s.seq_loss_count},{s.seq_loss_pkts},{int(s.abnormal_split)},{s.pcd_filename}\n")
    print(f"\n帧时间戳统计已保存: {csv_path}")
    print("\n提示: 使用 new_driver 模式时，输出的 first/last 时间戳应与 SLAM 日志中的")
    print("      'ldr ts: xxx - yyy' 完全一致。如有 ↩️角度回跳分帧 标记，说明该帧由")
    print("      azimuth 回跳触发（正常现象，非错误），两种分帧方式在驱动中等价。")


if __name__ == '__main__':
    main()
