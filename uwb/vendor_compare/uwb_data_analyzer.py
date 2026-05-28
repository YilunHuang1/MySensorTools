#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UWB数据分析器 - 专业分析飞睿和全迹UWB测试数据
支持静态和动态测试数据的全面对比分析
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
from typing import Dict, List, Tuple, Optional
import math
from datetime import datetime
import matplotlib.dates as mdates
from scipy import stats

# 统一角度偏移设置（仅应用于 Quanji 数据）
QUANJI_AZIMUTH_OFFSET_DEG = 60.0

# 设置中文字体和样式
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.style.use('seaborn-v0_8')
warnings.filterwarnings('ignore')

class UWBDataAnalyzer:
    """UWB数据分析器主类"""
    
    def __init__(self, data_dir: str):
        """
        初始化分析器
        
        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = Path(data_dir)
        self.feirui_dir = self.data_dir / "feirui_test"
        self.quanji_dir = self.data_dir / "quanji_test"
        
        # 数据存储
        self.feirui_data = {}
        self.quanji_data = {}
        
        # 分析结果存储
        self.static_analysis = {}
        self.dynamic_analysis = {}
        
        print(f"UWB数据分析器初始化完成")
        print(f"数据目录: {self.data_dir}")
        
    def load_feirui_data(self) -> Dict[str, pd.DataFrame]:
        """
        加载飞睿测试数据
        
        Returns:
            包含所有飞睿数据的字典
        """
        print("正在加载飞睿测试数据...")
        
        feirui_files = {
            "1.2m_static": "1.2m_uwb_data_20251020_212045.csv",
            "1.2m_block": "1.2m_block_uwb_data_20251017_173116.csv", 
            "2.4m_static": "2.4m_uwb_data_20251017_170516.csv",
            "2.4m_block": "2.4m_block_uwb_data_20251020_212402.csv",
            "active_1": "active_1_uwb_data_20251017_174112.csv",
            "active_2": "active_2_uwb_data_20251020_212549.csv",
            "active_3": "active_3_uwb_data_20251020_212644.csv"
        }
        
        for test_name, filename in feirui_files.items():
            file_path = self.feirui_dir / filename
            if file_path.exists():
                df = pd.read_csv(file_path)
                
                # 数据预处理
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df['distance_m'] = df['distance_cm'] / 100.0  # 转换为米
                df['device'] = 'Feirui'
                df['test_type'] = test_name
                
                # 统一计算并校验XY坐标
                df['x_m'] = df['distance_m'] * np.sin(np.radians(df['azimuth_deg']))
                df['y_m'] = df['distance_m'] * np.cos(np.radians(df['azimuth_deg']))
                
                self.feirui_data[test_name] = df
                print(f"  ✓ 加载 {test_name}: {len(df)} 条记录")
            else:
                print(f"  ✗ 文件不存在: {filename}")
        
        # 额外发现并整合新增动态测试文件（active_*）
        for file in sorted(self.feirui_dir.glob("active_*_uwb_data_*.csv")):
            test_name = file.name.split("_uwb_data_")[0]  # 例如 active_4
            if test_name not in self.feirui_data:
                df = pd.read_csv(file)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                # 距离单位统一
                if 'distance_m' not in df.columns and 'distance_cm' in df.columns:
                    df['distance_m'] = df['distance_cm'] / 100.0
                df['device'] = 'Feirui'
                df['test_type'] = test_name
                # 统一计算XY
                df['x_m'] = df['distance_m'] * np.sin(np.radians(df['azimuth_deg']))
                df['y_m'] = df['distance_m'] * np.cos(np.radians(df['azimuth_deg']))
                self.feirui_data[test_name] = df
                print(f"  ✓ 发现新增动态测试 {test_name}: {len(df)} 条记录")
        
        return self.feirui_data
    
    def load_quanji_data(self) -> Dict[str, pd.DataFrame]:
        """
        加载全迹测试数据
        
        Returns:
            包含所有全迹数据的字典
        """
        print("正在加载全迹测试数据...")
        
        quanji_files = {
            "1.2m_static": "1.2m_log-2025_10_24-19_24_29_750.csv",
            "1.2m_block": "1.2m_block_log-2025_10_24-19_25_42_819.csv",
            "2.4m_static": "2.4m_log-2025_10_24-19_28_52_739.csv", 
            "2.4m_block": "2.4m_block_log-2025_10_24-19_27_32_050.csv",
            "active_1": "active_1_log-2025_10_23-19_56_38_370.csv",
            "active_2": "active_2_log-2025_10_23-19_57_13_080.csv",
            "active_3": "active_3_log-2025_10_23-19_59_17_178.csv"
        }
        
        for test_name, filename in quanji_files.items():
            file_path = self.quanji_dir / filename
            if file_path.exists():
                df = pd.read_csv(file_path)
                
                # 数据预处理（统一为XY坐标，不使用pitch）
                df = self._process_quanji_data(df, test_name)
                self.quanji_data[test_name] = df
                print(f"  ✓ 加载 {test_name}: {len(df)} 条记录")
            else:
                print(f"  ✗ 文件不存在: {filename}")
        
        # 额外发现并整合新增动态测试文件（active_*）
        for file in sorted(self.quanji_dir.glob("active_*_log-*.csv")):
            test_name = file.name.split("_log-")[0]  # 例如 active_4
            if test_name not in self.quanji_data:
                df = pd.read_csv(file)
                df = self._process_quanji_data(df, test_name)
                self.quanji_data[test_name] = df
                print(f"  ✓ 发现新增动态测试 {test_name}: {len(df)} 条记录")
        
        return self.quanji_data
    
    def _process_quanji_data(self, df: pd.DataFrame, test_name: str) -> pd.DataFrame:
        """
        处理全迹数据，统一采用平面极坐标→XY转换（不使用pitch）
        优先使用“车中心距离”作为距离来源
        """
        # 列重命名（仅角度统一），距离来源优先采用“车中心距离”
        df = df.rename(columns={
            '原始角度': 'azimuth_deg'
        })
        # 对Quanji角度应用固定偏移（offset=+60°），并确保数值类型
        df['azimuth_deg'] = pd.to_numeric(df['azimuth_deg'], errors='coerce')
        df['azimuth_deg'] = df['azimuth_deg'] + QUANJI_AZIMUTH_OFFSET_DEG
        # 如需限制到[-180,180]，可启用以下归一化（当前保留原范围）：
        # df['azimuth_deg'] = ((df['azimuth_deg'] + 180.0) % 360.0) - 180.0

        distance_source = 'unknown'
        if '车中心距离' in df.columns:
            df['distance_m'] = df['车中心距离']
            distance_source = 'car_center'
        elif '原始距离' in df.columns:
            df['distance_m'] = df['原始距离']
            distance_source = 'original'
        
        # 时间处理
        if '时间' in df.columns:
            df['timestamp'] = pd.to_datetime(df['时间'], format='%Y_%m_%d-%H_%M_%S_%f')
        # 统一XY坐标（与Feirui一致）
        df['x_m'] = df['distance_m'] * np.sin(np.radians(df['azimuth_deg']))
        df['y_m'] = df['distance_m'] * np.cos(np.radians(df['azimuth_deg']))
        # 标注设备与测试类型与距离来源
        df['device'] = 'Quanji'
        df['test_type'] = test_name
        df['distance_source'] = distance_source
        # 日志记录静态处理状态
        print(f"  ▸ Quanji[{test_name}] 处理完成：角度已加偏移+{QUANJI_AZIMUTH_OFFSET_DEG}°，距离来源={distance_source}，已生成x_m/y_m")
        return df
    
    def analyze_static_data(self) -> Dict:
        """
        分析静态测试数据
        
        Returns:
            静态数据分析结果
        """
        print("正在分析静态测试数据...")
        
        static_tests = ['1.2m_static', '1.2m_block', '2.4m_static', '2.4m_block']
        results = {}
        
        for test_name in static_tests:
            results[test_name] = {}
            
            # 分析飞睿数据
            if test_name in self.feirui_data:
                feirui_df = self.feirui_data[test_name]
                results[test_name]['Feirui'] = self._calculate_static_metrics(
                    feirui_df, 'distance_m', 'azimuth_deg'
                )
            
            # 分析全迹数据
            if test_name in self.quanji_data:
                quanji_df = self.quanji_data[test_name]
                results[test_name]['Quanji'] = self._calculate_static_metrics(
                    quanji_df, 'distance_m', 'azimuth_deg'
                )
        
        self.static_analysis = results
        return results
    
    def _calculate_static_metrics(self, df: pd.DataFrame, 
                                distance_col: str, angle_col: str) -> Dict:
        """
        计算静态测试指标
        
        Args:
            df: 数据框
            distance_col: 距离列名
            angle_col: 角度列名
            
        Returns:
            统计指标字典
        """
        metrics = {}
        
        # 距离统计
        distance_data = df[distance_col]
        metrics['distance'] = {
            'mean': distance_data.mean(),
            'std': distance_data.std(),
            'min': distance_data.min(),
            'max': distance_data.max(),
            'median': distance_data.median(),
            'q25': distance_data.quantile(0.25),
            'q75': distance_data.quantile(0.75)
        }
        
        # 角度统计
        angle_data = df[angle_col]
        metrics['angle'] = {
            'mean': angle_data.mean(),
            'std': angle_data.std(),
            'min': angle_data.min(),
            'max': angle_data.max(),
            'median': angle_data.median(),
            'q25': angle_data.quantile(0.25),
            'q75': angle_data.quantile(0.75)
        }
        
        # 数据质量指标
        metrics['quality'] = {
            'total_points': len(df),
            'distance_cv': metrics['distance']['std'] / metrics['distance']['mean'],
            'angle_cv': metrics['angle']['std'] / abs(metrics['angle']['mean']) if metrics['angle']['mean'] != 0 else float('inf')
        }
        
        return metrics
    
    def analyze_dynamic_data(self) -> Dict:
        """
        分析动态测试数据
        移除仅处理active_4/active_5的限制，按每组绘图
        """
        print("正在分析动态测试数据...")
        
        # 自动发现所有active_*测试组（支持新增）
        feirui_active = [k for k in self.feirui_data.keys() if k.startswith('active_')]
        quanji_active = [k for k in self.quanji_data.keys() if k.startswith('active_')]
        dynamic_tests = sorted(list(set(feirui_active + quanji_active)))
        print(f"  ▶ 发现动态组别: {', '.join(dynamic_tests) if dynamic_tests else '(无)'}")
        results = {}
        
        for test_name in dynamic_tests:
            print(f"  ▶ 正在处理动态组别: {test_name}")
            results[test_name] = {}
            feirui_df_raw: Optional[pd.DataFrame] = self.feirui_data.get(test_name)
            quanji_df_raw: Optional[pd.DataFrame] = self.quanji_data.get(test_name)

            # 分析飞睿轨迹（仅在存在 x_m/y_m 列时）
            if feirui_df_raw is not None and {'x_m', 'y_m'}.issubset(feirui_df_raw.columns) and len(feirui_df_raw) > 0:
                print(f"  ▸ Feirui[{test_name}] 使用全部数据进行分析: 行数={len(feirui_df_raw)}")
                results[test_name]['Feirui'] = self._analyze_trajectory(
                    feirui_df_raw, 'x_m', 'y_m'
                )
            else:
                print(f"  ℹ️ Feirui[{test_name}] 不含 x_m/y_m 或数据为空，跳过分析")
                results[test_name]['Feirui'] = {}

            # 分析全迹轨迹（仅在存在 x_m/y_m 列时）
            if quanji_df_raw is not None and {'x_m', 'y_m'}.issubset(quanji_df_raw.columns) and len(quanji_df_raw) > 0:
                print(f"  ▸ Quanji[{test_name}] 使用全部数据进行分析: 行数={len(quanji_df_raw)}")
                results[test_name]['Quanji'] = self._analyze_trajectory(
                    quanji_df_raw, 'x_m', 'y_m'
                )
            else:
                print(f"  ℹ️ Quanji[{test_name}] 不含 x_m/y_m 或数据为空，跳过分析")
                results[test_name]['Quanji'] = {}

            # 在图表输出前添加调试信息，并绘制当前组别（使用全部数据）
            self._plot_dynamic_group(test_name, feirui_df_raw, quanji_df_raw)
        self.dynamic_analysis = results
        return results
    
    def _plot_dynamic_group(self, test_name: str, feirui_df: Optional[pd.DataFrame], quanji_df: Optional[pd.DataFrame]) -> None:
        """为每个动态组别创建独立图表，包含完整标签、图例和标题。"""
        if (feirui_df is None or len(feirui_df) == 0) and (quanji_df is None or len(quanji_df) == 0):
            print(f"  ℹ️ 动态组别 {test_name} 无可用数据，跳过绘图")
            return
        print(f"  🖼️ 生成动态组别图表: {test_name}")
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.set_title(f"动态组别: {test_name} — UWB动态轨迹对比", fontweight='bold')
        ax.set_xlabel("X坐标 (m)")
        ax.set_ylabel("Y坐标 (m)")
        ax.grid(True, alpha=0.3)
        colors = {'Feirui': '#2E86AB', 'Quanji': '#A23B72'}
        # 绘制飞睿轨迹
        if feirui_df is not None and {'x_m', 'y_m'}.issubset(feirui_df.columns) and len(feirui_df) > 0:
            ax.plot(
                feirui_df['x_m'], feirui_df['y_m'],
                color=colors['Feirui'], linewidth=2, alpha=0.85,
                label="Feirui轨迹", marker='o', markersize=1
            )
            try:
                ax.plot(feirui_df['x_m'].iloc[0], feirui_df['y_m'].iloc[0], marker='s', color=colors['Feirui'], markersize=6, label="Feirui起点")
                ax.plot(feirui_df['x_m'].iloc[-1], feirui_df['y_m'].iloc[-1], marker='X', color=colors['Feirui'], markersize=7, label="Feirui终点")
            except Exception:
                pass
        # 绘制全迹轨迹
        if quanji_df is not None and {'x_m', 'y_m'}.issubset(quanji_df.columns) and len(quanji_df) > 0:
            ax.plot(
                quanji_df['x_m'], quanji_df['y_m'],
                color=colors['Quanji'], linewidth=2, alpha=0.85,
                label="Quanji轨迹", marker='o', markersize=1
            )
            try:
                ax.plot(quanji_df['x_m'].iloc[0], quanji_df['y_m'].iloc[0], marker='s', color=colors['Quanji'], markersize=6, label="Quanji起点")
                ax.plot(quanji_df['x_m'].iloc[-1], quanji_df['y_m'].iloc[-1], marker='X', color=colors['Quanji'], markersize=7, label="Quanji终点")
            except Exception:
                pass
        # 坐标范围调整
        xs, ys = [], []
        if feirui_df is not None and len(feirui_df) > 0 and {'x_m', 'y_m'}.issubset(feirui_df.columns):
            xs.extend(feirui_df['x_m'].astype(float).tolist())
            ys.extend(feirui_df['y_m'].astype(float).tolist())
        if quanji_df is not None and len(quanji_df) > 0 and {'x_m', 'y_m'}.issubset(quanji_df.columns):
            xs.extend(quanji_df['x_m'].astype(float).tolist())
            ys.extend(quanji_df['y_m'].astype(float).tolist())
        if xs and ys:
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            dx = x_max - x_min
            dy = y_max - y_min
            pad_x = (dx or 1.0) * 0.05
            pad_y = (dy or 1.0) * 0.05
            ax.set_xlim(x_min - pad_x, x_max + pad_x)
            ax.set_ylim(y_min - pad_y, y_max + pad_y)
        ax.set_aspect('equal', adjustable='box')
        ax.legend(loc="upper right")
        plt.tight_layout()
        # 保存到 data_tools 同级目录的 analysis_results
        try:
            out_dir = (self.data_dir.parent / "analysis_results")
        except Exception:
            out_dir = Path("analysis_results")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"dynamic_trajectory_{test_name}.png"
        plt.savefig(out_path, dpi=300, bbox_inches='tight')
        print(f"  ✅ 图表已保存: {out_path}")
        plt.close(fig)

    def _analyze_trajectory(self, df: pd.DataFrame, x_col: str, y_col: str) -> Dict:
        """
        分析轨迹数据
        
        Args:
            df: 数据框
            x_col: X坐标列名
            y_col: Y坐标列名
            
        Returns:
            轨迹分析结果
        """
        trajectory = {}
        
        # 轨迹基本统计
        trajectory['x_stats'] = {
            'mean': df[x_col].mean(),
            'std': df[x_col].std(),
            'range': df[x_col].max() - df[x_col].min()
        }
        
        trajectory['y_stats'] = {
            'mean': df[y_col].mean(),
            'std': df[y_col].std(),
            'range': df[y_col].max() - df[y_col].min()
        }
        
        # 轨迹长度计算
        dx = np.diff(df[x_col])
        dy = np.diff(df[y_col])
        distances = np.sqrt(dx**2 + dy**2)
        trajectory['total_distance'] = np.sum(distances)
        trajectory['avg_step_size'] = np.mean(distances)
        
        # 速度分析（如果有时间戳）
        if 'timestamp' in df.columns:
            dt = df['timestamp'].diff().dt.total_seconds().dropna()
            if len(dt) > 0 and len(distances) == len(dt):
                velocities = distances / dt.values
                trajectory['velocity_stats'] = {
                    'mean': np.mean(velocities),
                    'std': np.std(velocities),
                    'max': np.max(velocities)
                }
        
        return trajectory
    
    def load_all_data(self):
        """加载所有数据"""
        self.load_feirui_data()
        self.load_quanji_data()
        print(f"\n数据加载完成:")
        print(f"  飞睿数据: {len(self.feirui_data)} 组测试")
        print(f"  全迹数据: {len(self.quanji_data)} 组测试")
        # 静态/动态组统计日志
        feirui_static = sorted([k for k in self.feirui_data.keys() if not k.startswith('active_')])
        feirui_dynamic = sorted([k for k in self.feirui_data.keys() if k.startswith('active_')])
        quanji_static = sorted([k for k in self.quanji_data.keys() if not k.startswith('active_')])
        quanji_dynamic = sorted([k for k in self.quanji_data.keys() if k.startswith('active_')])
        print(f"  飞睿静态组: {len(feirui_static)} -> {feirui_static}")
        print(f"  飞睿动态组: {len(feirui_dynamic)} -> {feirui_dynamic}")
        print(f"  全迹静态组: {len(quanji_static)} -> {quanji_static}")
        print(f"  全迹动态组: {len(quanji_dynamic)} -> {quanji_dynamic}")
    
    def validate_loaded_data(self) -> Dict[str, Dict]:
        """
        验证已加载数据的字段完整性与一致性（含新增动态测试与Quanji静态字段覆盖与距离校验）
        """
        results: Dict[str, Dict] = {}
        
        def _validate_df(df: pd.DataFrame, device: str, test_name: str) -> Dict:
            required = ['distance_m', 'azimuth_deg', 'x_m', 'y_m']
            missing = [c for c in required if c not in df.columns]
            # 尝试补齐常见缺失
            if 'distance_m' in missing and 'distance_cm' in df.columns:
                df['distance_m'] = df['distance_cm'] / 100.0
                missing = [c for c in required if c not in df.columns]
            if ('x_m' in missing or 'y_m' in missing) and {'distance_m','azimuth_deg'}.issubset(df.columns):
                df['x_m'] = df['distance_m'] * np.sin(np.radians(df['azimuth_deg']))
                df['y_m'] = df['distance_m'] * np.cos(np.radians(df['azimuth_deg']))
                missing = [c for c in required if c not in df.columns]
            valid = len(missing) == 0
            details = {}
            # Quanji静态字段覆盖与距离校验
            if device == 'Quanji' and not test_name.startswith('active_'):
                expected_quanji = ['原始距离','原始角度','车中心距离','x','y','锚点偏移Y','车中心偏移Y','距离车边缘距离','距离偏移','角度偏移','尾距离偏移','尾角度偏移','滤波窗口','排除比例','index','key','时间','锚点时间ms','rx_power','rssi_fpp','rssi_np','rssi_ble','pitch']
                present = [c for c in expected_quanji if c in df.columns]
                missing_fields = [c for c in expected_quanji if c not in df.columns]
                details['field_coverage'] = {
                    'expected_count': len(expected_quanji),
                    'present_count': len(present),
                    'missing': missing_fields
                }
                # 距离计算结果验证
                details['distance_source'] = df['distance_source'].iloc[0] if 'distance_source' in df.columns else None
                if {'x','y'}.issubset(df.columns):
                    r_xy = np.sqrt(df['x']**2 + df['y']**2)
                    diff_xy = (df['distance_m'] - r_xy).abs()
                    details['distance_vs_xy_rms'] = float(np.sqrt(np.mean(diff_xy**2)))
                    details['distance_vs_xy_max'] = float(diff_xy.max())
                if '原始距离' in df.columns:
                    diff_org = (df['distance_m'] - df['原始距离']).abs()
                    details['distance_vs_original_rms'] = float(np.sqrt(np.mean(diff_org**2)))
                # 日志输出
                print(f"  ▸ Quanji[{test_name}] 字段覆盖: {len(present)}/{len(expected_quanji)}，距离来源={details['distance_source']}")
                if details.get('distance_vs_xy_rms') is not None and details['distance_vs_xy_rms'] > 0.2:
                    print(f"    ⚠️ 距离校验：distance_vs_xy_rms={details['distance_vs_xy_rms']:.3f}m 超过阈值")
                else:
                    print("    ✅ 距离校验通过")
            return {
                'device': device,
                'test_name': test_name,
                'valid': valid,
                'missing_columns': missing,
                'total_rows': len(df),
                'details': details
            }
        
        # 验证飞睿
        for test_name, df in self.feirui_data.items():
            results[f'Feirui::{test_name}'] = _validate_df(df, 'Feirui', test_name)
        # 验证全迹
        for test_name, df in self.quanji_data.items():
            results[f'Quanji::{test_name}'] = _validate_df(df, 'Quanji', test_name)
        # 汇总输出
        valid_count = sum(1 for r in results.values() if r['valid'])
        print(f"\n✅ 数据验证完成：{valid_count}/{len(results)} 组通过")
        for key, r in results.items():
            if not r['valid']:
                print(f"  ⚠️ {key} 缺失字段: {r['missing_columns']}")
        return results


if __name__ == "__main__":
    # 测试数据加载
    analyzer = UWBDataAnalyzer(".")
    analyzer.load_all_data()
    
    # 执行分析
    static_results = analyzer.analyze_static_data()
    dynamic_results = analyzer.analyze_dynamic_data()
    
    print("\n静态数据分析完成")
    print("动态数据分析完成")


# [deleted duplicate module-level _plot_dynamic_group]
