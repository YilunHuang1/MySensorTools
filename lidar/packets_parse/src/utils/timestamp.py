"""
PCD 文件时间戳工具模块

提供时间戳提取、排序、关联等功能
"""

import os
import re
import glob
import statistics
from pathlib import Path
from typing import List, Tuple, Dict
from datetime import datetime


class TimestampUtils:
    """时间戳处理工具"""
    
    PATTERN = r'frame_(\d+)_(\d+\.\d+)s?\.pcd'
    
    @staticmethod
    def extract_from_filename(filename: str) -> Tuple[int, float, str]:
        """
        从 PCD 文件名中提取帧号和时间戳
        
        输入: "frame_0001_1774257429.901083100.pcd"
        输出: (1, 1774257429.901083100, filename)
        
        Args:
            filename: PCD 文件名
            
        Returns:
            (frame_num, timestamp_sec, filename) 或 None
        """
        match = re.search(TimestampUtils.PATTERN, filename)
        if match:
            frame_num = int(match.group(1))
            timestamp_sec = float(match.group(2))
            return (frame_num, timestamp_sec, filename)
        return None
    
    @staticmethod
    def list_sorted(directory: str) -> List[Dict]:
        """
        列出目录中的所有 PCD 文件，按时间戳排序
        
        Args:
            directory: 目录路径
            
        Returns:
            [{
                'frame': 1,
                'timestamp_sec': 1774257429.901083100,
                'filename': filename,
                'path': pcd_file
            }, ...]
        """
        pcd_files = glob.glob(os.path.join(directory, 'frame_*.pcd'))
        
        results = []
        for pcd_file in pcd_files:
            basename = os.path.basename(pcd_file)
            extracted = TimestampUtils.extract_from_filename(basename)
            
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
    
    @staticmethod
    def calculate_intervals(pcd_files: List[Dict]) -> Dict:
        """
        计算相邻帧之间的时间间隔统计
        
        Args:
            pcd_files: 文件列表 (来自 list_sorted)
            
        Returns:
            {
                'intervals': [0.2, 0.2, ...],
                'mean_interval_ms': 214.8,
                'min_interval_ms': 0.0,
                'max_interval_ms': 598.0,
                'std_dev_ms': 54.7,
                'sampling_freq_hz': 4.7
            }
        """
        if len(pcd_files) < 2:
            return None
        
        intervals = []
        for i in range(1, len(pcd_files)):
            delta = pcd_files[i]['timestamp_sec'] - pcd_files[i-1]['timestamp_sec']
            intervals.append(delta * 1000)  # 转换为毫秒
        
        mean_ms = statistics.mean(intervals)
        if len(intervals) > 1:
            stdev_ms = statistics.stdev(intervals)
        else:
            stdev_ms = 0
        
        return {
            'intervals_ms': intervals,
            'mean_interval_ms': mean_ms,
            'min_interval_ms': min(intervals),
            'max_interval_ms': max(intervals),
            'std_dev_ms': stdev_ms,
            'sampling_freq_hz': 1000.0 / mean_ms if mean_ms > 0 else 0,
        }
    
    @staticmethod
    def timestamp_to_datetime(timestamp_sec: float) -> datetime:
        """
        将秒级时间戳转换为 datetime
        
        Args:
            timestamp_sec: 秒级时间戳 (unix epoch)
            
        Returns:
            datetime 对象
        """
        return datetime.utcfromtimestamp(timestamp_sec)
    
    @staticmethod
    def format_time_range(pcd_files: List[Dict]) -> Dict:
        """
        格式化时间范围信息
        
        Args:
            pcd_files: 文件列表
            
        Returns:
            {
                'start_ts': 1774257429.901083100,
                'end_ts': 1774257692.835584164,
                'start_time': '2026-03-23 09:17:09.901083',
                'end_time': '2026-03-23 09:21:32.835584',
                'duration_sec': 262.9
            }
        """
        if not pcd_files:
            return None
        
        start_ts = pcd_files[0]['timestamp_sec']
        end_ts = pcd_files[-1]['timestamp_sec']
        duration = end_ts - start_ts
        
        start_dt = TimestampUtils.timestamp_to_datetime(start_ts)
        end_dt = TimestampUtils.timestamp_to_datetime(end_ts)
        
        return {
            'start_ts': start_ts,
            'end_ts': end_ts,
            'start_time': start_dt.strftime('%Y-%m-%d %H:%M:%S.%f'),
            'end_time': end_dt.strftime('%Y-%m-%d %H:%M:%S.%f'),
            'duration_sec': duration,
            'num_frames': len(pcd_files),
        }
