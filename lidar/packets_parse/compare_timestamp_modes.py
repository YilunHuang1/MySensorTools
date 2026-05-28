#!/usr/bin/env python3
"""
对比两种时间戳模式的 CSV 输出，分析差异。

用法:
  1. 先以 driver_original 模式运行:
       TIMESTAMP_MODE = "driver_original"  # in extract_lidar_pcd_with_ts.py
       python extract_lidar_pcd_with_ts.py

  2. 再以 per_packet 模式运行:
       TIMESTAMP_MODE = "per_packet"
       python extract_lidar_pcd_with_ts.py

  3. 运行本脚本对比:
       python compare_timestamp_modes.py
"""

import os
import sys
import numpy as np
import csv
from pathlib import Path

BASE_DIR = 'pcd_output_with_ts'
CSV_DRIVER = os.path.join(BASE_DIR, 'driver_original', 'frame_timestamps_driver_original.csv')
CSV_PERPKT = os.path.join(BASE_DIR, 'per_packet',       'frame_timestamps_per_packet.csv')


def load_csv(path):
    frames = []
    with open(path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            frames.append({
                'frame_idx':      int(row['frame_idx']),
                'first_point_ts': float(row['first_point_ts']),
                'last_point_ts':  float(row['last_point_ts']),
                'duration_ms':    float(row['duration_ms']),
                'point_count':    int(row['point_count']),
            })
    return frames


def main():
    for p, name in [(CSV_DRIVER, 'driver_original'), (CSV_PERPKT, 'per_packet')]:
        if not Path(p).exists():
            print(f"❌ 找不到 {name} CSV: {p}")
            print("   请先以对应模式运行 extract_lidar_pcd_with_ts.py")
            sys.exit(1)

    a = load_csv(CSV_DRIVER)
    b = load_csv(CSV_PERPKT)

    n = min(len(a), len(b))
    print(f"对比帧数: {n}")
    print()

    # ---- 每帧 first_point_ts 差异 ----
    diffs_ms = [(b[i]['first_point_ts'] - a[i]['first_point_ts']) * 1000 for i in range(n)]

    print("=" * 70)
    print("first_point_ts 差异（per_packet - driver_original，单位 ms）")
    print("=" * 70)
    print(f"  均值:   {np.mean(diffs_ms):+.3f} ms")
    print(f"  标准差: {np.std(diffs_ms):.3f} ms")
    print(f"  最小:   {np.min(diffs_ms):+.3f} ms")
    print(f"  最大:   {np.max(diffs_ms):+.3f} ms")

    # 差异大于 5ms 的帧
    anomaly_thresh = 5.0
    anomalies = [(i, diffs_ms[i]) for i in range(n) if abs(diffs_ms[i]) > anomaly_thresh]
    if anomalies:
        print(f"\n⚠️  差异 > {anomaly_thresh}ms 的帧（共 {len(anomalies)} 帧）:")
        print(f"  {'帧':>5} {'driver_first':>18} {'perpkt_first':>18} {'差异(ms)':>10}")
        for i, diff in anomalies[:20]:
            print(f"  {a[i]['frame_idx']:>5} {a[i]['first_point_ts']:>18.6f} "
                  f"{b[i]['first_point_ts']:>18.6f} {diff:>+10.3f}")
    else:
        print(f"\n✅ 所有帧差异均 < {anomaly_thresh}ms，两种模式时间戳基本一致。")

    # ---- 帧间隔分析 ----
    print()
    print("=" * 70)
    print("帧起始时间间隔分析（相邻帧 first_point_ts 之差）")
    print("=" * 70)
    for label, frames in [("driver_original", a), ("per_packet", b)]:
        intervals = [(frames[i+1]['first_point_ts'] - frames[i]['first_point_ts']) * 1000
                     for i in range(len(frames)-1)]
        arr = np.array(intervals)
        print(f"\n  [{label}]")
        print(f"    均值:   {np.mean(arr):.2f} ms  (理想应接近 200ms)")
        print(f"    标准差: {np.std(arr):.2f} ms")
        print(f"    最小:   {np.min(arr):.2f} ms")
        print(f"    最大:   {np.max(arr):.2f} ms")
        bad = [(i, v) for i, v in enumerate(intervals) if abs(v - 200.0) > 10]
        if bad:
            print(f"    ⚠️ 偏离200ms超10ms的帧间隔: {len(bad)} 处")
            for i, v in bad[:5]:
                print(f"       帧{frames[i]['frame_idx']}→{frames[i+1]['frame_idx']}: {v:.2f} ms")

    # ---- 帧时长分析 ----
    print()
    print("=" * 70)
    print("帧时长分析（last_point_ts - first_point_ts）")
    print("=" * 70)
    for label, frames in [("driver_original", a), ("per_packet", b)]:
        durations = [f['duration_ms'] for f in frames]
        arr = np.array(durations)
        print(f"\n  [{label}]")
        print(f"    均值:   {np.mean(arr):.2f} ms")
        print(f"    标准差: {np.std(arr):.2f} ms")
        print(f"    最小:   {np.min(arr):.2f} ms")
        print(f"    最大:   {np.max(arr):.2f} ms")

    print()
    print("=" * 70)
    print("结论说明")
    print("=" * 70)
    print("""
  driver_original 模式:
    - first_point_ts = 帧末包时间 - 固定 200ms
    - 假设电机匀速，帧时长恒为 200ms
    - 电机震动 → 实际帧周期波动 → 相邻帧 first_point_ts 可能重叠

  per_packet 模式:
    - 每个点时间戳 = 该包的硬件时间戳 + chan × 20.8μs
    - 不依赖 200ms 假设
    - 帧起始时间 = 帧内最早点的时间戳（真实反映实际转速）
    - 相邻帧起始时间差 = 实际帧周期，不会重叠

  如果两种模式的帧起始时间差异 > 5ms，说明存在时间戳偏差风险。
  如果 driver_original 的帧间隔出现 < 190ms 或 > 210ms，
  则 vita_slam 可能会 Drop LiDAR frame。
""")


if __name__ == '__main__':
    main()
