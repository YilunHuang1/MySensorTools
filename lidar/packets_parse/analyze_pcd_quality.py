#!/usr/bin/env python3
"""
点云质量分析工具 - 检测万集 WLR-722Z 数据问题

包含：
  1. 点云数据质量检查 (NaN, 距离, 强度等)
  2. 时间戳合理性验证 (帧率稳定性, 时间跳变)
  3. 性能评估 (数据丢失, 延迟等)
"""
import os
import glob
import re
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime


def analyze_frame(pcd_path):
    """分析单帧点云，支持 ASCII 和 binary 格式"""
    from sensor_tools.pcd import xyzi
    points = xyzi(pcd_path)
    n_points = len(points)
    if not n_points:
        return None

    xyz = points[:, :3]
    intensity = points[:, 3]
    
    finite_xyz = xyz[np.isfinite(xyz).all(axis=1)]
    finite_intensity = intensity[np.isfinite(intensity)]
    distances = np.linalg.norm(finite_xyz, axis=1)
    def bounds(values):
        return (float(values.min()), float(values.max())) if len(values) else (float('nan'), float('nan'))
    def mean(values):
        return float(values.mean()) if len(values) else float('nan')
    stats = {
        'n_points': n_points,
        'finite_points': len(finite_xyz),
        'x_range': bounds(finite_xyz[:, 0]),
        'y_range': bounds(finite_xyz[:, 1]),
        'z_range': bounds(finite_xyz[:, 2]),
        'dist_range': bounds(distances),
        'dist_mean': mean(distances),
        'intensity_range': bounds(finite_intensity),
        'intensity_mean': mean(finite_intensity),
        'nan_count': np.isnan(xyz).any(axis=1).sum(),
        'inf_count': np.isinf(xyz).any(axis=1).sum(),
        'z_mean': mean(finite_xyz[:, 2]),
    }

    # 检测异常
    anomalies = []
    if stats['nan_count'] > 0:
        anomalies.append(f"包含 {stats['nan_count']} 个 NaN")
    if stats['inf_count'] > 0:
        anomalies.append(f"包含 {stats['inf_count']} 个 Inf")
    if stats['intensity_mean'] < 10:
        anomalies.append(f"平均强度过低 ({stats['intensity_mean']:.1f})")
    if stats['z_mean'] < -1:
        anomalies.append(f"平均高度异常低 ({stats['z_mean']:.3f}m)")
    if stats['dist_range'][1] > 150:
        anomalies.append(f"最大距离超过预期 ({stats['dist_range'][1]:.1f}m)")
    
    stats['anomalies'] = anomalies
    return stats


def extract_timestamp_from_filename(filename):
    """
    从 PCD 文件名中提取时间戳

    支持两种格式:
      frame_0001_1774257429.901083231.pcd   (标准格式)
      frame_0001_1774257429.901083231s.pcd  (旧格式，兼容)
    返回: (frame_num, timestamp_sec)
    """
    match = re.search(r'frame_(\d+)_(\d+\.\d+)s?\.pcd', filename)
    if match:
        return int(match.group(1)), float(match.group(2))
    return None, None


def analyze_timestamps(pcd_dir, expected_hz=5.0):
    """
    分析时间戳的合理性
    
    检查项:
      1. 帧率是否稳定 (期望 ~5 Hz = 0.2 秒间隔)
      2. 是否有时间跳变 (突然的大间隔)
      3. 是否有时间倒序 (数据乱序)
      4. 时间戳精度 (纳秒级)
    """
    files = sorted(glob.glob(os.path.join(pcd_dir, 'frame_*.pcd')))
    
    if not files:
        return None
    
    # 提取所有时间戳
    timestamps = []
    frame_nums = []
    
    for pcd_file in files:
        filename = os.path.basename(pcd_file)
        frame_num, timestamp_sec = extract_timestamp_from_filename(filename)
        
        if timestamp_sec is not None:
            timestamps.append(timestamp_sec)
            frame_nums.append(frame_num)
    
    if len(timestamps) < 2:
        return None
    
    timestamps = np.array(timestamps)
    frame_nums = np.array(frame_nums)
    
    # 计算帧间隔 (秒)
    intervals_sec = np.diff(timestamps)
    intervals_ms = intervals_sec * 1000  # 转换为毫秒
    
    # 期望帧率 (5 Hz)
    if expected_hz <= 0:
        raise ValueError("expected_hz must be positive")
    expected_interval_ms = 1000 / expected_hz
    
    # 统计分析
    analysis = {
        'num_frames': len(timestamps),
        'total_duration_sec': timestamps[-1] - timestamps[0],
        
        # 帧率统计
        'mean_interval_ms': np.mean(intervals_ms),
        'std_interval_ms': np.std(intervals_ms),
        'min_interval_ms': np.min(intervals_ms),
        'max_interval_ms': np.max(intervals_ms),
        'median_interval_ms': np.median(intervals_ms),
        
        # 计算实际帧率
        'actual_framerate_hz': 1000.0 / np.mean(intervals_ms) if np.mean(intervals_ms) > 0 else float('nan'),
        'expected_framerate_hz': expected_hz,
        
        # 偏差分析
        'interval_deviation_pct': np.std(intervals_ms) / np.mean(intervals_ms) * 100 if np.mean(intervals_ms) > 0 else float('nan'),
        
        # 时间戳质量
        'has_backward_time': np.any(intervals_sec < 0),
        'max_time_jump_ms': np.max(intervals_ms),
        'num_large_jumps': np.sum(intervals_ms > expected_interval_ms * 1.5),  # 大于 1.5 倍期望
        'num_small_intervals': np.sum(intervals_ms < expected_interval_ms * 0.5),  # 小于 0.5 倍期望
        
        # 所有间隔
        'intervals_ms': intervals_ms,
        'timestamps': timestamps,
        'frame_nums': frame_nums,
    }
    
    return analysis


def report_timestamp_analysis(analysis):
    """Filename timestamps describe frame spacing, not point-boundary continuity."""
    print('\nFrame timestamp statistics (from filenames):')
    for key in ['num_frames', 'total_duration_sec', 'expected_framerate_hz',
                'actual_framerate_hz', 'mean_interval_ms', 'std_interval_ms',
                'min_interval_ms', 'max_interval_ms', 'has_backward_time',
                'num_large_jumps', 'num_small_intervals']:
        print(f'  {key}: {analysis[key]}')
    print('Large/small intervals mean >1.5x/<0.5x the requested nominal period.')
    print('These statistics do not identify packet loss, clock faults or hardware health.')
    print('Use timestamp extraction for next-frame first-point < previous-frame last-point checks.')


def main():
    parser = argparse.ArgumentParser(description="Analyze PCD frame quality and timestamp stability")
    parser.add_argument("pcd_dir", nargs="?", default="pcd_output", help="PCD output directory")
    parser.add_argument("--expected-hz", type=float, default=5.0)
    args = parser.parse_args()
    if args.expected_hz <= 0:
        parser.error("--expected-hz must be positive")
    pcd_dir = args.pcd_dir
    
    if not os.path.exists(pcd_dir):
        print(f"❌ 目录不存在: {pcd_dir}")
        raise SystemExit(1)
    
    files = sorted(glob.glob(os.path.join(pcd_dir, '*.pcd')))
    if not files:
        print(f"❌ 没有找到 .pcd 文件")
        raise SystemExit(1)
    
    print(f"📊 分析 {len(files)} 帧点云数据\n")
    
    all_stats = []
    for index, pcd_path in enumerate(files):
        parsed_index, _ = extract_timestamp_from_filename(Path(pcd_path).name)
        frame_idx = parsed_index if parsed_index is not None else index
        stats = analyze_frame(pcd_path)
        if stats is None:
            continue
        
        all_stats.append((frame_idx, stats))
        
        # 打印单帧信息
        print(f"Frame {frame_idx:3d}: {stats['n_points']:6d} pts | "
              f"dist [{stats['dist_range'][0]:6.2f}, {stats['dist_range'][1]:6.2f}]m | "
              f"Z [{stats['z_range'][0]:7.3f}, {stats['z_range'][1]:7.3f}]m | "
              f"Intensity [{stats['intensity_range'][0]:3.0f}, {stats['intensity_range'][1]:3.0f}]")
        
        if stats['anomalies']:
            for anom in stats['anomalies']:
                print(f"  ⚠️  {anom}")
    
    print("\n" + "=" * 80)
    print("📈 点云数据整体统计")
    print("=" * 80)
    
    if not all_stats:
        raise SystemExit('No non-empty PCD frames')
    point_counts = [s[1]['n_points'] for s in all_stats]
    z_means = [s[1]['z_mean'] for s in all_stats]
    dist_means = [s[1]['dist_mean'] for s in all_stats]
    intensity_means = [s[1]['intensity_mean'] for s in all_stats]
    
    print(f"点数:        {np.mean(point_counts):.0f} ± {np.std(point_counts):.0f} (min={min(point_counts)}, max={max(point_counts)})")
    print(f"平均高度:    {np.mean(z_means):.3f} ± {np.std(z_means):.3f} m")
    print(f"平均距离:    {np.mean(dist_means):.2f} ± {np.std(dist_means):.2f} m")
    print(f"平均强度:    {np.mean(intensity_means):.1f} ± {np.std(intensity_means):.1f}")
    
    # 检查是否有异常帧
    anomaly_frames = [(f, s) for f, s in all_stats if s['anomalies']]
    if anomaly_frames:
        print(f"\n⚠️  检测到 {len(anomaly_frames)} 帧异常:")
        for frame_idx, stats in anomaly_frames[:10]:  # 只显示前 10 个
            print(f"   Frame {frame_idx}: {', '.join(stats['anomalies'])}")
        if len(anomaly_frames) > 10:
            print(f"   ... 还有 {len(anomaly_frames) - 10} 帧异常")
    else:
        print("\n✓ 本次启发式检查未检出异常（不等于硬件健康证明）")
    
    # 时间戳分析
    ts_analysis = analyze_timestamps(pcd_dir, args.expected_hz)
    if ts_analysis:
        report_timestamp_analysis(ts_analysis)
    
    print('Non-finite placeholders may represent invalid returns; scene-dependent thresholds are descriptive only.')



if __name__ == '__main__':
    main()
