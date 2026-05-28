"""
LiDAR 帧提取和处理模块
"""

import os
import numpy as np
from pathlib import Path

from .decoder import VanjeeDecoder


class FrameExtractor:
    """LiDAR 帧提取器"""
    
    def __init__(self, vert_angles, horiz_angles, output_dir='pcd_output'):
        """
        初始化帧提取器
        
        Args:
            vert_angles: 垂直角度表
            horiz_angles: 水平角度偏差表
            output_dir: 输出目录
        """
        self.vert_angles = vert_angles
        self.horiz_angles = horiz_angles
        self.output_dir = output_dir
        
        VanjeeDecoder.init_trig_tables()
        self.decoder = VanjeeDecoder()
        
        os.makedirs(output_dir, exist_ok=True)
    
    def process_message(self, mcap_message):
        """
        处理单个 MCAP 消息
        
        Args:
            mcap_message: MCAP 消息对象
            
        Returns:
            list: [(azimuth, points, timestamp_ns), ...] 列表
        """
        results = []
        
        # 获取时间戳 (纳秒)
        timestamp_ns = mcap_message.publish_time
        
        # 解析 CDR 消息
        data_bytes = self.decoder.parse_mcap_message(mcap_message.data)
        if data_bytes is None or len(data_bytes) == 0:
            return results
        
        # 提取子数据包
        sub_packets = self.decoder.extract_sub_packets(data_bytes)
        
        for pkt_type, pkt_data in sub_packets:
            if pkt_type != 'pointcloud':
                continue
            
            result = self.decoder.decode_point_cloud_packet(
                pkt_data, self.vert_angles, self.horiz_angles
            )
            if result is None:
                continue
            
            azimuth, points = result
            results.append((azimuth, points, timestamp_ns))
        
        return results
    
    def detect_frame_boundary(self, prev_azimuth, curr_azimuth, threshold=60):
        """
        检测帧边界 (方位角过零点)

        对齐驱动 SplitStrategyByAngle 逻辑:
          azimuth_trans = (curr + resolution) % 36000
          触发条件: azimuth_trans < prev_azimuth_trans  (纯回落检测)

        原条件 azimuth_trans < threshold 在 azimuth 跳过 0° 落在 (0°, 0.6°) 时
        会漏切，修复为与上一帧的 azimuth_trans 比较。
        """
        if prev_azimuth < 0:
            return False

        curr_trans = (curr_azimuth + threshold) % 36000
        prev_trans = (prev_azimuth + threshold) % 36000
        return curr_trans < prev_trans

    def save_pcd_ascii(self, filepath, points_xyz, intensities):
        """保存为 PCD ASCII 格式"""
        n = len(points_xyz)
        with open(filepath, 'w') as f:
            f.write("# .PCD v0.7 - Point Cloud Data file format\n")
            f.write("VERSION 0.7\n")
            f.write("FIELDS x y z intensity\n")
            f.write("SIZE 4 4 4 4\n")
            f.write("TYPE F F F F\n")
            f.write("COUNT 1 1 1 1\n")
            f.write(f"WIDTH {n}\n")
            f.write("HEIGHT 1\n")
            f.write("VIEWPOINT 0 0 0 1 0 0 0\n")
            f.write(f"POINTS {n}\n")
            f.write("DATA ascii\n")
            for i in range(n):
                f.write(f"{points_xyz[i][0]:.6f} {points_xyz[i][1]:.6f} {points_xyz[i][2]:.6f} {intensities[i]:.0f}\n")
    
    def save_frame(self, frame_count, frame_points, timestamp_ns):
        """
        保存一帧点云
        
        Args:
            frame_count: 帧编号
            frame_points: 点列表 [(x,y,z,intensity), ...]
            timestamp_ns: 时间戳 (纳秒)
            
        Returns:
            str: 保存的文件路径
        """
        if len(frame_points) == 0:
            return None
        
        xyz = np.array([(p[0], p[1], p[2]) for p in frame_points], dtype=np.float32)
        intensity = np.array([p[3] for p in frame_points], dtype=np.float32)
        
        # 转换时间戳为秒 (含小数)
        timestamp_sec = timestamp_ns / 1e9
        
        # 生成文件名: frame_XXXX_TTTTTTTTTT.TTTTTTTTT.pcd
        filename = f"frame_{frame_count:04d}_{timestamp_sec:.9f}.pcd"
        filepath = os.path.join(self.output_dir, filename)
        
        self.save_pcd_ascii(filepath, xyz, intensity)
        
        return filepath
