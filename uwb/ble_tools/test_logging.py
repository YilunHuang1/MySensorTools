#!/usr/bin/env python3
"""
测试日志功能 - 简化版（不依赖serial模块）
"""
import time
import csv
from datetime import datetime
from collections import deque

class RangingStatsSimple:
    """简化的统计类"""
    def __init__(self):
        self.timestamps = deque(maxlen=50)
        self.distances = deque(maxlen=50)
        self.total_frames = 0
        self.start_time = None
        self._last_report_time = None
        self._frames_since_report = 0
        
    def update(self, distance, angle, pitch):
        now = time.time()
        if self.start_time is None:
            self.start_time = now
            self._last_report_time = now
        
        self.total_frames += 1
        self._frames_since_report += 1
        self.timestamps.append(now)
        self.distances.append(distance)
    
    def fps(self):
        if len(self.timestamps) < 2:
            return 0.0
        dt = self.timestamps[-1] - self.timestamps[0]
        return (len(self.timestamps) - 1) / dt if dt > 0 else 0.0
    
    def global_fps(self):
        if self.start_time is None or self.total_frames < 2:
            return 0.0
        dt = time.time() - self.start_time
        return self.total_frames / dt if dt > 0 else 0.0
    
    def get_summary_and_reset(self):
        fps = self.fps()
        global_fps = self.global_fps()
        frames = self._frames_since_report
        elapsed = time.time() - self._last_report_time if self._last_report_time else 0
        period_fps = frames / elapsed if elapsed > 0 else 0
        
        self._last_report_time = time.time()
        self._frames_since_report = 0
        
        return {
            'fps': fps,
            'global_fps': global_fps,
            'period_fps': period_fps,
            'total_frames': self.total_frames,
            'period_frames': frames,
        }
    
    def distance_stats(self):
        if not self.distances:
            return None
        d = list(self.distances)
        return {
            'min': min(d),
            'max': max(d),
        }

class CSVLoggerSimple:
    """简化的CSV日志类"""
    def __init__(self, filepath):
        self.filepath = filepath
        self.file = open(filepath, 'w', newline='')
        self.writer = csv.writer(self.file)
        self.writer.writerow(['timestamp', 'elapsed_s', 'frame_no', 'distance_m', 'fps'])
        self.start_time = time.time()
        self.frame_no = 0
        print(f"📝 CSV logging to: {filepath}")
    
    def log(self, distance, fps):
        now = time.time()
        elapsed = now - self.start_time
        self.frame_no += 1
        self.writer.writerow([f"{now:.6f}", f"{elapsed:.3f}", self.frame_no, f"{distance:.4f}", f"{fps:.1f}"])
        if self.frame_no % 10 == 0:
            self.file.flush()
    
    def write_summary(self, summary_text):
        log_path = self.filepath.replace('.csv', '.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(summary_text + '\n')
    
    def close(self):
        self.file.flush()
        self.file.close()
        print(f"📝 CSV saved: {self.filepath} ({self.frame_no} frames)")

def test_logging():
    print("="*60)
    print("  测试 UWB 日志功能")
    print("="*60)
    
    csv_logger = CSVLoggerSimple("/tmp/uwb_test.csv")
    stats = RangingStatsSimple()
    
    print("\n📊 模拟30帧数据...")
    
    for i in range(30):
        distance = 2.0 + 0.1 * (i % 10)
        angle = 45.0
        pitch = -10.0
        
        stats.update(distance, angle, pitch)
        fps = stats.fps()
        csv_logger.log(distance, fps)
        
        if (i + 1) % 10 == 0:
            print(f"  已处理 {i+1} 帧...")
        
        time.sleep(0.16)
        
        if (i + 1) % 10 == 0:
            summary = stats.get_summary_and_reset()
            summary_lines = []
            summary_lines.append("\n┌─────────────────── 📊 周期统计 ───────────────────┐")
            summary_lines.append(f"│ 时间: {datetime.now().strftime('%H:%M:%S')}")
            summary_lines.append(f"│ FPS: 实时={summary['fps']:.1f}  周期={summary['period_fps']:.1f}  全局={summary['global_fps']:.1f}")
            summary_lines.append(f"│ 总帧数: {summary['total_frames']}")
            summary_lines.append("└───────────────────────────────────────────────────┘\n")
            
            summary_text = '\n'.join(summary_lines)
            print(summary_text)
            csv_logger.write_summary(summary_text)
    
    elapsed = time.time() - stats.start_time if stats.start_time else 0
    d = stats.distance_stats()
    
    summary_lines = []
    summary_lines.append("\n" + "=" * 60)
    summary_lines.append("  📊 最终统计摘要")
    summary_lines.append("=" * 60)
    summary_lines.append(f"  总帧数     : {stats.total_frames}")
    summary_lines.append(f"  运行时间   : {elapsed:.1f}s")
    summary_lines.append(f"  平均 FPS   : {stats.global_fps():.1f}")
    if d:
        summary_lines.append(f"  距离范围   : {d['min']:.3f}m ~ {d['max']:.3f}m")
    summary_lines.append(f"  CSV 文件   : {csv_logger.filepath}")
    summary_lines.append("=" * 60)
    
    summary_text = '\n'.join(summary_lines)
    print(summary_text)
    csv_logger.write_summary(summary_text)
    
    csv_logger.close()
    
    print("\n✅ 测试完成！")
    print(f"   CSV 文件: {csv_logger.filepath}")
    print(f"   LOG 文件: {csv_logger.filepath.replace('.csv', '.log')}")
    print("\n查看日志内容:")
    print(f"   cat {csv_logger.filepath.replace('.csv', '.log')}")

if __name__ == "__main__":
    test_logging()
