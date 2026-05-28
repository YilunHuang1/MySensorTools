"""
角度校准参数管理模块
"""

import os
from pathlib import Path


class CalibrationManager:
    """校准参数管理器"""
    
    def __init__(self, csv_path=None):
        """
        初始化校准管理器
        
        Args:
            csv_path: 校准 CSV 文件路径。若为 None，使用默认路径
        """
        self.csv_path = csv_path
        self.vert_angles = []
        self.horiz_angles = []
        self.num_channels = 0
        
        if csv_path:
            self.load(csv_path)
    
    def load(self, csv_path):
        """
        加载校准文件
        
        Args:
            csv_path: CSV 文件路径
            
        Returns:
            bool: 加载成功为 True
        """
        if not Path(csv_path).exists():
            raise FileNotFoundError(f"校准文件不存在: {csv_path}")
        
        self.csv_path = csv_path
        self.vert_angles = []
        self.horiz_angles = []
        
        with open(csv_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                vert = float(parts[0]) * 1000  # 转换为毫度
                horiz = float(parts[1]) * 1000  # 转换为毫度
                self.vert_angles.append(int(vert))
                self.horiz_angles.append(int(horiz))
        
        self.num_channels = len(self.vert_angles)
        return True
    
    def get_default_path(self, model='722z'):
        """
        获取默认校准文件路径
        
        Args:
            model: 型号代码 ('722z', '722', '720_16' 等)
            
        Returns:
            str: 文件路径
        """
        base_dir = Path(__file__).parent.parent.parent / 'config' / 'calibration'
        
        model_map = {
            '722z': 'Vanjee_722z_VA.csv',
            '722': 'Vanjee_722_VA.csv',
            '720_16': 'Vanjee_720_16_VA.csv',
            '722f': 'Vanjee_722f_VA.csv',
            '722h': 'Vanjee_722h_VA.csv',
        }
        
        filename = model_map.get(model, f'Vanjee_{model}_VA.csv')
        return str(base_dir / filename)
    
    def load_default(self, model='722z'):
        """
        加载默认校准文件
        
        Args:
            model: 型号代码
            
        Returns:
            bool: 加载成功为 True
        """
        path = self.get_default_path(model)
        return self.load(path)
    
    def validate(self):
        """
        验证校准参数的完整性
        
        Returns:
            tuple: (is_valid, error_msg)
        """
        if not self.vert_angles or not self.horiz_angles:
            return False, "校准参数为空"
        
        if len(self.vert_angles) != len(self.horiz_angles):
            return False, "垂直角度和水平偏差数量不匹配"
        
        if len(self.vert_angles) == 0:
            return False, "没有加载任何校准数据"
        
        return True, "校准参数有效"
    
    def get_angles(self, channel):
        """
        获取指定通道的角度
        
        Args:
            channel: 通道号 (0-15 等)
            
        Returns:
            (vert_angle, horiz_angle): 角度对 (毫度)
        """
        if channel < 0 or channel >= self.num_channels:
            raise IndexError(f"通道号超出范围: {channel}")
        
        return self.vert_angles[channel], self.horiz_angles[channel]
    
    def get_all_angles(self):
        """获取所有角度"""
        return self.vert_angles, self.horiz_angles
    
    def info(self):
        """获取校准参数信息"""
        return {
            'csv_path': self.csv_path,
            'num_channels': self.num_channels,
            'vert_angles': self.vert_angles,
            'horiz_angles': self.horiz_angles,
        }
