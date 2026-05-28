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
    n_points = None
    data_format = 'binary'
    header_end = 0

    with open(pcd_path, 'rb') as f:
        while True:
            line = f.readline().decode('ascii', errors='ignore').strip()
            header_end = f.tell()
            if line.startswith('POINTS'):
                n_points = int(line.split()[1])
            if line.startswith('DATA'):
                data_format = line.split()[1].lower()  # 'ascii' or 'binary'
                break

    if n_points is None or n_points == 0:
        return None

    if data_format == 'ascii':
        # ASCII 格式：逐行读取 x y z intensity
        points = []
        with open(pcd_path, 'r') as f:
            for line in f:
                if line.startswith('DATA'):
                    break
            for line in f:
                vals = line.strip().split()
                if len(vals) >= 4:
                    points.append([float(vals[0]), float(vals[1]),
                                   float(vals[2]), float(vals[3])])
        points = np.array(points, dtype=np.float32)
    else:
        # Binary 格式
        with open(pcd_path, 'rb') as f:
            f.seek(header_end)
            data = np.frombuffer(f.read(n_points * 16), dtype=np.float32)
            points = data.reshape(n_points, 4)
    
    xyz = points[:, :3]
    intensity = points[:, 3]
    
    # 计算统计量
    dist_from_origin = np.linalg.norm(xyz, axis=1)
    
    stats = {
        'n_points': n_points,
        'x_range': (xyz[:, 0].min(), xyz[:, 0].max()),
        'y_range': (xyz[:, 1].min(), xyz[:, 1].max()),
        'z_range': (xyz[:, 2].min(), xyz[:, 2].max()),
        'dist_range': (dist_from_origin.min(), dist_from_origin.max()),
        'dist_mean': dist_from_origin.mean(),
        'intensity_range': (intensity.min(), intensity.max()),
        'intensity_mean': intensity.mean(),
        'nan_count': np.isnan(xyz).sum(),
        'inf_count': np.isinf(xyz).sum(),
        'z_mean': xyz[:, 2].mean(),
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


def analyze_timestamps(pcd_dir):
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
    expected_interval_ms = 1000 / 5.0  # 200 ms
    
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
        'actual_framerate_hz': 1000.0 / np.mean(intervals_ms),
        'expected_framerate_hz': 5.0,
        
        # 偏差分析
        'interval_deviation_pct': np.std(intervals_ms) / np.mean(intervals_ms) * 100,
        
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
    """生成时间戳分析报告"""
    
    print("\n" + "=" * 80)
    print("⏱️  时间戳合理性分析")
    print("=" * 80)
    
    print(f"\n📊 基本信息")
    print(f"  总帧数:           {analysis['num_frames']} 帧")
    print(f"  总时长:           {analysis['total_duration_sec']:.2f} 秒")
    print(f"  预期帧率:         5.0 Hz (200 ms/frame)")
    print(f"  实际帧率:         {analysis['actual_framerate_hz']:.2f} Hz")
    
    print(f"\n⏲️  帧间隔统计 (单位: ms)")
    print(f"  平均间隔:         {analysis['mean_interval_ms']:.2f} ms")
    print(f"  标准差:           {analysis['std_interval_ms']:.2f} ms")
    print(f"  中位数:           {analysis['median_interval_ms']:.2f} ms")
    print(f"  最小间隔:         {analysis['min_interval_ms']:.2f} ms")
    print(f"  最大间隔:         {analysis['max_interval_ms']:.2f} ms")
    print(f"  间隔偏差:         {analysis['interval_deviation_pct']:.1f}%")
    
    # 动态异常阈值：相对平均间隔的 ±40%
    mean_ms = analysis['mean_interval_ms']
    threshold_high = mean_ms * 1.4
    threshold_low  = mean_ms * 0.6

    bad_intervals = [
        (i, iv)
        for i, iv in enumerate(analysis['intervals_ms'])
        if iv > threshold_high or iv < threshold_low
    ]

    print(f"\n⚠️  异常检测")
    print(f"  时间倒序:         {'❌ 有' if analysis['has_backward_time'] else '✓ 无'}")
    print(f"  最大时间跳变:     {analysis['max_time_jump_ms']:.2f} ms")
    print(f"  大时间跳变 (>300ms): {analysis['num_large_jumps']} 次")
    print(f"  小间隔 (<100ms):  {analysis['num_small_intervals']} 次")
    print(f"  异常间隔 (偏离均值±40%,  阈值 [{threshold_low:.1f}, {threshold_high:.1f}] ms): {len(bad_intervals)} 次")

    if bad_intervals:
        print(f"\n🔍 异常间隔明细:")
        print(f"  {'Frame A':>8}  {'Frame B':>8}  {'间隔(ms)':>10}  {'偏差':>8}  时间 A → 时间 B")
        print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*8}  {'-'*35}")
        for idx, iv_ms in bad_intervals:
            fa = analysis['frame_nums'][idx]
            fb = analysis['frame_nums'][idx + 1]
            ts_a = analysis['timestamps'][idx]
            ts_b = analysis['timestamps'][idx + 1]
            deviation_pct = (iv_ms - mean_ms) / mean_ms * 100
            sign = '+' if deviation_pct >= 0 else ''
            time_a = datetime.utcfromtimestamp(ts_a).strftime('%H:%M:%S.%f')[:-3]
            time_b = datetime.utcfromtimestamp(ts_b).strftime('%H:%M:%S.%f')[:-3]
            label = '⬆ 大' if iv_ms > threshold_high else '⬇ 小'
            print(f"  {fa:>8}  {fb:>8}  {iv_ms:>10.2f}  {sign}{deviation_pct:>6.1f}%  {label}  {time_a} → {time_b}")

    # 帧率稳定性评估
    print(f"\n🎯 稳定性评估")
    framerate_error = abs(analysis['actual_framerate_hz'] - 5.0) / 5.0 * 100
    deviation = analysis['interval_deviation_pct']
    
    if deviation < 5:
        stability = "✅ 极好 (偏差 < 5%)"
    elif deviation < 10:
        stability = "🟢 很好 (偏差 < 10%)"
    elif deviation < 20:
        stability = "🟡 中等 (偏差 < 20%)"
    else:
        stability = "🔴 较差 (偏差 > 20%)"
    
    print(f"  帧率稳定性:       {stability}")
    print(f"  帧率误差:         {framerate_error:.1f}% (目标 5 Hz, 实际 {analysis['actual_framerate_hz']:.2f} Hz)")
    
    # 详细异常分析
    if analysis['num_large_jumps'] > 0:
        print(f"\n🔍 大时间跳变详情 (>300 ms):")
        for i, interval_ms in enumerate(analysis['intervals_ms']):
            if interval_ms > 300:
                frame_a = analysis['frame_nums'][i]
                frame_b = analysis['frame_nums'][i + 1]
                ts_a = analysis['timestamps'][i]
                ts_b = analysis['timestamps'][i + 1]
                print(f"  Frame {frame_a} → {frame_b}: {interval_ms:.2f} ms 跳变")
                print(f"    时间: {datetime.utcfromtimestamp(ts_a).strftime('%H:%M:%S.%f')} → "
                      f"{datetime.utcfromtimestamp(ts_b).strftime('%H:%M:%S.%f')}")
    
    if analysis['num_small_intervals'] > 0:
        print(f"\n🔍 异常小间隔详情 (<100 ms):")
        for i, interval_ms in enumerate(analysis['intervals_ms']):
            if interval_ms < 100:
                frame_a = analysis['frame_nums'][i]
                frame_b = analysis['frame_nums'][i + 1]
                print(f"  Frame {frame_a} → {frame_b}: {interval_ms:.2f} ms (可能数据包丢失重传)")
    
    # 健康度打分
    print(f"\n📈 综合健康度")
    score = 100
    if deviation > 20:
        score -= 30
    elif deviation > 10:
        score -= 15
    
    if analysis['num_large_jumps'] > 0:
        score -= min(20, analysis['num_large_jumps'] * 5)
    
    if analysis['has_backward_time']:
        score -= 40
    
    score = max(0, score)
    
    if score >= 90:
        grade = "🟢 优秀"
    elif score >= 75:
        grade = "🟡 良好"
    elif score >= 60:
        grade = "🟠 一般"
    else:
        grade = "🔴 需要检查"
    
    print(f"  综合评分:         {score}/100 - {grade}")
    
    # 建议
    print(f"\n💡 建议:")
    if deviation > 10:
        print(f"  • 帧率波动较大，可能是:")
        print(f"    - 网络延迟或数据包丢失 (表现为大的时间跳变)")
        print(f"    - 处理延迟 (MCAP 写入速度不稳定)")
        print(f"    - 硬件时钟漂移 (需要时间同步)")
    
    if analysis['num_large_jumps'] > 0:
        print(f"  • 检测到 {analysis['num_large_jumps']} 次大时间跳变")
        print(f"    - 可能的数据包丢失或重传")
        print(f"    - 建议检查网络连接状况")
    
    if analysis['num_small_intervals'] > 0:
        print(f"  • 检测到 {analysis['num_small_intervals']} 次异常小间隔")
        print(f"    - 可能是点云数据包分片处理的误差")
        print(f"    - 或处理器缓冲区刷新不均匀")


def main():
    parser = argparse.ArgumentParser(description="Analyze PCD frame quality and timestamp stability")
    parser.add_argument("pcd_dir", nargs="?", default="pcd_output", help="PCD output directory")
    args = parser.parse_args()
    pcd_dir = args.pcd_dir
    
    if not os.path.exists(pcd_dir):
        print(f"❌ 目录不存在: {pcd_dir}")
        return
    
    files = sorted(glob.glob(os.path.join(pcd_dir, '*.pcd')))
    if not files:
        print(f"❌ 没有找到 .pcd 文件")
        return
    
    print(f"📊 分析 {len(files)} 帧点云数据\n")
    
    all_stats = []
    for pcd_path in files:
        frame_idx = int(Path(pcd_path).stem.split('_')[1])
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
        print("\n✓ 所有帧数据正常，无异常检测")
    
    # 时间戳分析
    ts_analysis = analyze_timestamps(pcd_dir)
    if ts_analysis:
        report_timestamp_analysis(ts_analysis)
    
    print("\n💡 数据质量建议:")
    print("  1. 高度波动较大 (Z-std > 0.5m)：可能是地面不平或扫描范围变化")
    print("  2. 强度低 (mean < 30)：可能是物体反光性差或距离远")
    print("  3. 点数波动大：可能是分辨率动态调整（60° vs 120°）")
    print("  4. 距离分布异常：检查是否有阴影或障碍物")
    print("  5. 帧率波动大 (>10%)：检查网络连接或处理器性能")


if __name__ == '__main__':
    main()
