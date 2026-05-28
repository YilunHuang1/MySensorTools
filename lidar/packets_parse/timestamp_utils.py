#!/usr/bin/env python3
"""
PCD 文件时间戳工具

提供时间戳提取、排序、关联等功能
"""

import os
import re
import glob
from pathlib import Path
from typing import List, Tuple, Dict

def extract_timestamp_from_pcd_filename(filename: str) -> Tuple[int, float, str]:
    """
    从 PCD 文件名中提取帧号和时间戳
    
    输入: "frame_0001_1774257429.901083100.pcd"
    输出: (1, 1774257429.901083100, "frame_0001_1774257429.901083100.pcd")
    
    返回: (frame_number, timestamp_sec, full_filename)
    """
    match = re.search(r'frame_(\d+)_(\d+\.\d+)s?\.pcd', filename)
    if match:
        frame_num = int(match.group(1))
        timestamp_sec = float(match.group(2))
        return (frame_num, timestamp_sec, filename)
    return None


def list_pcd_files_sorted(directory: str) -> List[Dict]:
    """
    列出目录中的所有 PCD 文件，按时间戳排序
    
    返回: 
    [
        {
            'frame': 1,
            'timestamp_sec': 1774257429.901083100,
            'filename': 'frame_0001_1774257429.901083100.pcd',
            'path': '/full/path/to/file.pcd'
        },
        ...
    ]
    """
    pcd_files = glob.glob(os.path.join(directory, 'frame_*.pcd'))
    
    results = []
    for pcd_file in pcd_files:
        basename = os.path.basename(pcd_file)
        extracted = extract_timestamp_from_pcd_filename(basename)
        
        if extracted:
            frame_num, timestamp_sec, filename = extracted
            results.append({
                'frame': frame_num,
                'timestamp_sec': timestamp_sec,
                'filename': filename,
                'path': pcd_file
            })
    
    # 按时间戳排序
    results.sort(key=lambda x: x['timestamp_sec'])
    return results


def calculate_frame_intervals(pcd_files: List[Dict]) -> Dict:
    """
    计算相邻帧之间的时间间隔统计
    
    返回:
    {
        'mean_interval_sec': 0.2148,      # 秒
        'mean_interval_ms': 214.8,
        'min_interval_sec': 0.0,
        'max_interval_sec': 0.598,
        'std_dev': 0.0547
    }
    """
    if len(pcd_files) < 2:
        return None
    
    intervals = []
    for i in range(1, len(pcd_files)):
        delta = pcd_files[i]['timestamp_sec'] - pcd_files[i-1]['timestamp_sec']
        intervals.append(delta)
    
    import statistics
    
    mean = statistics.mean(intervals)
    if len(intervals) > 1:
        stdev = statistics.stdev(intervals)
    else:
        stdev = 0
    
    return {
        'intervals': intervals,
        'mean_interval_sec': mean,
        'mean_interval_ms': mean * 1000.0,
        'min_interval_sec': min(intervals),
        'max_interval_sec': max(intervals),
        'std_dev': stdev,
        'frequency_hz': 1.0 / mean if mean > 0 else 0
    }


def print_frame_info(pcd_files: List[Dict]):
    """打印帧信息摘要"""
    print("\n" + "=" * 110)
    print(f"{'Frame':<8} {'Timestamp (sec)':<25} {'Interval (ms)':<15} {'Filename':<60}")
    print("=" * 110)
    
    prev_ts = None
    for f in pcd_files[:50]:  # 显示前 50 帧
        interval_ms = (f['timestamp_sec'] - prev_ts) * 1000.0 if prev_ts is not None else 0
        print(f"{f['frame']:<8} {f['timestamp_sec']:<25.9f} {interval_ms:<15.2f} {f['filename']:<60}")
        prev_ts = f['timestamp_sec']
    
    if len(pcd_files) > 50:
        print(f"... ({len(pcd_files) - 50} 更多帧)")
    
    print("=" * 110)


def main():
    """示例用法"""
    import sys
    
    if len(sys.argv) > 1:
        pcd_dir = sys.argv[1]
    else:
        pcd_dir = 'pcd_output'
    
    if not os.path.exists(pcd_dir):
        print(f"❌ 目录不存在: {pcd_dir}")
        sys.exit(1)
    
    print(f"📂 扫描目录: {pcd_dir}")
    
    # 列出所有文件
    pcd_files = list_pcd_files_sorted(pcd_dir)
    
    if not pcd_files:
        print("❌ 未找到任何 PCD 文件")
        sys.exit(1)
    
    print(f"✓ 找到 {len(pcd_files)} 个 PCD 文件\n")
    
    # 计算时间间隔
    stats = calculate_frame_intervals(pcd_files)
    
    if stats:
        print("📊 时间间隔统计:")
        print(f"  • 平均间隔: {stats['mean_interval_ms']:.2f} ms ({stats['mean_interval_sec']:.6f} s)")
        print(f"  • 采样频率: {stats['frequency_hz']:.1f} Hz")
        print(f"  • 最小间隔: {stats['min_interval_sec']:.6f} s")
        print(f"  • 最大间隔: {stats['max_interval_sec']:.6f} s")
        print(f"  • 标准差:   {stats['std_dev']:.6f} s")
    
    # 打印帧信息
    print_frame_info(pcd_files)
    
    # 时间范围
    total_time_sec = pcd_files[-1]['timestamp_sec'] - pcd_files[0]['timestamp_sec']
    
    # 转换为日期时间显示
    import datetime
    sec_first = int(pcd_files[0]['timestamp_sec'])
    nsec_first = int((pcd_files[0]['timestamp_sec'] - sec_first) * 1e9)
    dt_first = datetime.datetime.fromtimestamp(sec_first, tz=datetime.timezone.utc)
    
    sec_last = int(pcd_files[-1]['timestamp_sec'])
    nsec_last = int((pcd_files[-1]['timestamp_sec'] - sec_last) * 1e9)
    dt_last = datetime.datetime.fromtimestamp(sec_last, tz=datetime.timezone.utc)
    
    print(f"\n📈 数据覆盖:")
    print(f"  • 起始时间: {dt_first.strftime('%b %d %Y %H:%M:%S')}.{nsec_first:09d} ({pcd_files[0]['timestamp_sec']:.9f} s)")
    print(f"  • 结束时间: {dt_last.strftime('%b %d %Y %H:%M:%S')}.{nsec_last:09d} ({pcd_files[-1]['timestamp_sec']:.9f} s)")
    print(f"  • 总时长: {total_time_sec:.1f} 秒")
    print(f"  • 总帧数: {len(pcd_files)}")


if __name__ == '__main__':
    main()
