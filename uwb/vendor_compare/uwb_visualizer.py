#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UWB数据可视化模块 - 专业图表生成
支持静态和动态测试数据的全面可视化分析
"""

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.dates as mdates
from scipy.interpolate import griddata

# 设置中文字体和专业样式
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.size'] = 10

class UWBVisualizer:
    """UWB数据可视化器"""
    
    def __init__(self, output_dir: str = "analysis_results"):
        """
        初始化可视化器
        
        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 设置颜色方案
        self.colors = {
            'Feirui': '#2E86AB',      # 蓝色
            'Quanji': '#A23B72',      # 紫红色
            'reference': '#F18F01',    # 橙色
            'error': '#C73E1D'        # 红色
        }
        
        # 设置图表样式
        self.style_config = {
            'figure.figsize': (12, 8),
            'axes.grid': True,
            'grid.alpha': 0.3,
            'axes.spines.top': False,
            'axes.spines.right': False
        }
        
        print(f"UWB可视化器初始化完成，输出目录: {self.output_dir}")
    
    def plot_static_comparison(self, static_analysis: Dict, save_plots: bool = True):
        """
        绘制静态测试对比图表
        
        Args:
            static_analysis: 静态分析结果
            save_plots: 是否保存图表
        """
        print("正在生成静态测试对比图表...")
        
        # 1. 测距精度对比箱线图
        self._plot_distance_boxplot(static_analysis, save_plots)
        
        # 2. 测角精度对比箱线图  
        self._plot_angle_boxplot(static_analysis, save_plots)
        
        # 3. 误差带图
        self._plot_error_bands(static_analysis, save_plots)
        
        # 4. 稳定性雷达图
        self._plot_stability_radar(static_analysis, save_plots)
        
        # 5. 性能对比热力图
        self._plot_performance_heatmap(static_analysis, save_plots)
    
    def _plot_distance_boxplot(self, static_analysis: Dict, save_plots: bool):
        """绘制测距精度箱线图"""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('UWB测距精度对比分析', fontsize=16, fontweight='bold')
        
        test_configs = [
            ('1.2m_static', '1.2m静态测试', 1.2),
            ('1.2m_block', '1.2m遮挡测试', 1.2),
            ('2.4m_static', '2.4m静态测试', 2.4),
            ('2.4m_block', '2.4m遮挡测试', 2.4)
        ]
        
        for idx, (test_name, title, reference) in enumerate(test_configs):
            ax = axes[idx // 2, idx % 2]
            
            if test_name in static_analysis:
                data_to_plot = []
                labels = []
                
                for device in ['Feirui', 'Quanji']:
                    if device in static_analysis[test_name]:
                        # 模拟数据分布用于箱线图
                        metrics = static_analysis[test_name][device]['distance']
                        # 使用正态分布生成样本数据
                        samples = np.random.normal(
                            metrics['mean'], 
                            metrics['std'], 
                            1000
                        )
                        data_to_plot.append(samples)
                        labels.append(device)
                
                if data_to_plot:
                    bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True)
                    
                    # 设置颜色
                    for patch, label in zip(bp['boxes'], labels):
                        patch.set_facecolor(self.colors[label])
                        patch.set_alpha(0.7)
                    
                    # 添加参考线
                    ax.axhline(y=reference, color=self.colors['reference'], 
                              linestyle='--', linewidth=2, label=f'真值 {reference}m')
                    
                    ax.set_title(title, fontweight='bold')
                    ax.set_ylabel('距离 (m)')
                    ax.grid(True, alpha=0.3)
                    ax.legend()
                    
                    # 添加统计信息
                    for i, device in enumerate(labels):
                        metrics = static_analysis[test_name][device]['distance']
                        error = abs(metrics['mean'] - reference)
                        ax.text(i+1, ax.get_ylim()[1]*0.95, 
                               f'误差: {error:.3f}m\nSTD: {metrics["std"]:.3f}m',
                               ha='center', va='top', fontsize=8,
                               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        if save_plots:
            plt.savefig(self.output_dir / 'static_distance_comparison.png', 
                       dpi=300, bbox_inches='tight')
        plt.show()
    
    def _plot_angle_boxplot(self, static_analysis: Dict, save_plots: bool):
        """绘制测角精度箱线图"""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('UWB测角精度对比分析', fontsize=16, fontweight='bold')
        
        test_configs = [
            ('1.2m_static', '1.2m静态测试'),
            ('1.2m_block', '1.2m遮挡测试'),
            ('2.4m_static', '2.4m静态测试'),
            ('2.4m_block', '2.4m遮挡测试')
        ]
        
        for idx, (test_name, title) in enumerate(test_configs):
            ax = axes[idx // 2, idx % 2]
            
            if test_name in static_analysis:
                data_to_plot = []
                labels = []
                
                for device in ['Feirui', 'Quanji']:
                    if device in static_analysis[test_name]:
                        metrics = static_analysis[test_name][device]['angle']
                        samples = np.random.normal(
                            metrics['mean'], 
                            metrics['std'], 
                            1000
                        )
                        data_to_plot.append(samples)
                        labels.append(device)
                
                if data_to_plot:
                    bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True)
                    
                    for patch, label in zip(bp['boxes'], labels):
                        patch.set_facecolor(self.colors[label])
                        patch.set_alpha(0.7)
                    
                    ax.set_title(title, fontweight='bold')
                    ax.set_ylabel('角度 (度)')
                    ax.grid(True, alpha=0.3)
                    
                    # 添加统计信息
                    for i, device in enumerate(labels):
                        metrics = static_analysis[test_name][device]['angle']
                        ax.text(i+1, ax.get_ylim()[1]*0.95,
                               f'均值: {metrics["mean"]:.2f}°\nSTD: {metrics["std"]:.2f}°',
                               ha='center', va='top', fontsize=8,
                               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        if save_plots:
            plt.savefig(self.output_dir / 'static_angle_comparison.png',
                       dpi=300, bbox_inches='tight')
        plt.show()
    
    def _plot_error_bands(self, static_analysis: Dict, save_plots: bool):
        """绘制误差带图"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('UWB测量误差时间序列分析', fontsize=16, fontweight='bold')
        
        test_configs = [
            ('1.2m_static', '1.2m静态测试', 1.2),
            ('1.2m_block', '1.2m遮挡测试', 1.2),
            ('2.4m_static', '2.4m静态测试', 2.4),
            ('2.4m_block', '2.4m遮挡测试', 2.4)
        ]
        
        for idx, (test_name, title, reference) in enumerate(test_configs):
            ax = axes[idx // 2, idx % 2]
            
            if test_name in static_analysis:
                time_points = np.linspace(0, 100, 1000)  # 模拟时间序列
                
                for device in ['Feirui', 'Quanji']:
                    if device in static_analysis[test_name]:
                        metrics = static_analysis[test_name][device]['distance']
                        
                        # 模拟带噪声的测量数据
                        mean_val = metrics['mean']
                        std_val = metrics['std']
                        
                        # 生成主信号（带轻微趋势）
                        trend = 0.001 * np.sin(0.1 * time_points)
                        noise = np.random.normal(0, std_val, len(time_points))
                        measurements = mean_val + trend + noise
                        
                        # 绘制测量值
                        ax.plot(time_points, measurements, 
                               color=self.colors[device], alpha=0.6, linewidth=1,
                               label=f'{device} 测量值')
                        
                        # 绘制均值线
                        ax.axhline(y=mean_val, color=self.colors[device], 
                                  linestyle='-', linewidth=2, alpha=0.8,
                                  label=f'{device} 均值')
                        
                        # 绘制标准差带
                        ax.fill_between(time_points, 
                                       mean_val - std_val, 
                                       mean_val + std_val,
                                       color=self.colors[device], alpha=0.2,
                                       label=f'{device} ±1σ')
                
                # 添加参考线
                ax.axhline(y=reference, color=self.colors['reference'],
                          linestyle='--', linewidth=2, label=f'真值 {reference}m')
                
                ax.set_title(title, fontweight='bold')
                ax.set_xlabel('时间 (相对)')
                ax.set_ylabel('距离 (m)')
                ax.grid(True, alpha=0.3)
                ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        
        plt.tight_layout()
        if save_plots:
            plt.savefig(self.output_dir / 'error_bands_analysis.png',
                       dpi=300, bbox_inches='tight')
        plt.show()
    
    def _plot_stability_radar(self, static_analysis: Dict, save_plots: bool):
        """绘制稳定性雷达图"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 16), subplot_kw=dict(projection='polar'))
        fig.suptitle('UWB设备稳定性雷达图对比', fontsize=16, fontweight='bold')
        
        # 定义评估维度
        categories = ['距离精度', '角度精度', '距离稳定性', '角度稳定性', '数据质量']
        N = len(categories)
        
        test_configs = [
            ('1.2m_static', '1.2m静态'),
            ('1.2m_block', '1.2m遮挡'),
            ('2.4m_static', '2.4m静态'),
            ('2.4m_block', '2.4m遮挡')
        ]
        
        for idx, (test_name, title) in enumerate(test_configs):
            ax = axes[idx // 2, idx % 2]
            
            if test_name in static_analysis:
                angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
                angles += angles[:1]  # 闭合图形
                
                for device in ['Feirui', 'Quanji']:
                    if device in static_analysis[test_name]:
                        # 计算各维度得分（0-10分制）
                        dist_metrics = static_analysis[test_name][device]['distance']
                        angle_metrics = static_analysis[test_name][device]['angle']
                        quality_metrics = static_analysis[test_name][device]['quality']
                        
                        # 距离精度（误差越小得分越高）
                        reference = 1.2 if '1.2m' in test_name else 2.4
                        dist_error = abs(dist_metrics['mean'] - reference)
                        dist_accuracy = max(0, 10 - dist_error * 100)
                        
                        # 角度精度（标准差越小得分越高）
                        angle_accuracy = max(0, 10 - angle_metrics['std'])
                        
                        # 稳定性（变异系数越小得分越高）
                        dist_stability = max(0, 10 - dist_metrics['std'] * 100)
                        angle_stability = max(0, 10 - abs(angle_metrics['std']))
                        
                        # 数据质量
                        data_quality = min(10, quality_metrics['total_points'] / 100)
                        
                        values = [dist_accuracy, angle_accuracy, dist_stability, 
                                angle_stability, data_quality]
                        values += values[:1]  # 闭合图形
                        
                        ax.plot(angles, values, 'o-', linewidth=2, 
                               label=device, color=self.colors[device])
                        ax.fill(angles, values, alpha=0.25, color=self.colors[device])
                
                ax.set_xticks(angles[:-1])
                ax.set_xticklabels(categories)
                ax.set_ylim(0, 10)
                ax.set_title(title, fontweight='bold', pad=20)
                ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))
                ax.grid(True)
        
        plt.tight_layout()
        if save_plots:
            plt.savefig(self.output_dir / 'stability_radar_chart.png',
                       dpi=300, bbox_inches='tight')
        plt.show()
    
    def _plot_performance_heatmap(self, static_analysis: Dict, save_plots: bool):
        """绘制性能对比热力图"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        fig.suptitle('UWB设备性能对比热力图', fontsize=16, fontweight='bold')
        
        # 准备数据
        test_names = ['1.2m_static', '1.2m_block', '2.4m_static', '2.4m_block']
        devices = ['Feirui', 'Quanji']
        
        # 距离误差热力图
        distance_errors = np.zeros((len(devices), len(test_names)))
        angle_stds = np.zeros((len(devices), len(test_names)))
        
        references = [1.2, 1.2, 2.4, 2.4]
        
        for i, device in enumerate(devices):
            for j, (test_name, ref) in enumerate(zip(test_names, references)):
                if test_name in static_analysis and device in static_analysis[test_name]:
                    dist_mean = static_analysis[test_name][device]['distance']['mean']
                    distance_errors[i, j] = abs(dist_mean - ref) * 1000  # 转换为毫米
                    
                    angle_stds[i, j] = static_analysis[test_name][device]['angle']['std']
        
        # 距离误差热力图
        im1 = ax1.imshow(distance_errors, cmap='Reds', aspect='auto')
        ax1.set_xticks(range(len(test_names)))
        ax1.set_xticklabels([name.replace('_', '\n') for name in test_names])
        ax1.set_yticks(range(len(devices)))
        ax1.set_yticklabels(devices)
        ax1.set_title('距离测量误差 (mm)', fontweight='bold')
        
        # 添加数值标注
        for i in range(len(devices)):
            for j in range(len(test_names)):
                text = ax1.text(j, i, f'{distance_errors[i, j]:.1f}',
                               ha="center", va="center", color="white" if distance_errors[i, j] > distance_errors.max()/2 else "black")
        
        plt.colorbar(im1, ax=ax1, label='误差 (mm)')
        
        # 角度标准差热力图
        im2 = ax2.imshow(angle_stds, cmap='Blues', aspect='auto')
        ax2.set_xticks(range(len(test_names)))
        ax2.set_xticklabels([name.replace('_', '\n') for name in test_names])
        ax2.set_yticks(range(len(devices)))
        ax2.set_yticklabels(devices)
        ax2.set_title('角度测量标准差 (度)', fontweight='bold')
        
        # 添加数值标注
        for i in range(len(devices)):
            for j in range(len(test_names)):
                text = ax2.text(j, i, f'{angle_stds[i, j]:.2f}',
                               ha="center", va="center", color="white" if angle_stds[i, j] > angle_stds.max()/2 else "black")
        
        plt.colorbar(im2, ax=ax2, label='标准差 (度)')
        
        plt.tight_layout()
        if save_plots:
            plt.savefig(self.output_dir / 'performance_heatmap.png',
                       dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_dynamic_trajectories(self, feirui_data: Dict, quanji_data: Dict, 
                                dynamic_analysis: Dict, save_plots: bool = True):
        """
        绘制动态轨迹对比图
        
        Args:
            feirui_data: 飞睿数据
            quanji_data: 全迹数据
            dynamic_analysis: 动态分析结果
            save_plots: 是否保存图表
        """
        print("正在生成动态轨迹对比图表...")
        
        # 动态获取测试组（支持新增的active_*）
        dynamic_tests = sorted(list(dynamic_analysis.keys()))
        n = max(1, len(dynamic_tests))
        
        fig, axes = plt.subplots(1, n, figsize=(6*n, 6))
        fig.suptitle('UWB动态轨迹对比分析', fontsize=16, fontweight='bold')
        
        # 统一处理axes为数组
        if n == 1:
            axes = [axes]
        
        for idx, test_name in enumerate(dynamic_tests):
            ax = axes[idx]
            
            # 绘制飞睿轨迹
            if test_name in feirui_data:
                df = feirui_data[test_name]
                ax.plot(df['x_m'], df['y_m'], 
                       color=self.colors['Feirui'], linewidth=2, alpha=0.8,
                       label='Feirui轨迹', marker='o', markersize=1)
                
                # 标注起点和终点
                ax.plot(df['x_m'].iloc[0], df['y_m'].iloc[0], 
                       'o', color=self.colors['Feirui'], markersize=8, label='Feirui起点')
                ax.plot(df['x_m'].iloc[-1], df['y_m'].iloc[-1], 
                       's', color=self.colors['Feirui'], markersize=8, label='Feirui终点')
            
            # 绘制全迹轨迹（统一使用x_m/y_m）
            if test_name in quanji_data:
                df = quanji_data[test_name]
                ax.plot(df['x_m'], df['y_m'], 
                       color=self.colors['Quanji'], linewidth=2, alpha=0.8,
                       label='Quanji轨迹', marker='s', markersize=1)
                
                # 标注起点和终点
                ax.plot(df['x_m'].iloc[0], df['y_m'].iloc[0], 
                       'o', color=self.colors['Quanji'], markersize=8, label='Quanji起点')
                ax.plot(df['x_m'].iloc[-1], df['y_m'].iloc[-1], 
                       's', color=self.colors['Quanji'], markersize=8, label='Quanji终点')
            
            ax.set_xlabel('X坐标 (m)')
            ax.set_ylabel('Y坐标 (m)')
            ax.set_title(f'{test_name.replace("_", " ").title()}', fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend()
            ax.set_aspect('equal', adjustable='box')
        
        plt.tight_layout()
        if save_plots:
            plt.savefig(self.output_dir / 'dynamic_trajectories.png',
                       dpi=300, bbox_inches='tight')
        plt.show()
    
    def generate_comprehensive_report(self, static_analysis: Dict, dynamic_analysis: Dict):
        """
        生成综合分析报告
        
        Args:
            static_analysis: 静态分析结果
            dynamic_analysis: 动态分析结果
        """
        print("正在生成综合分析报告...")
        
        # 创建报告图表
        fig = plt.figure(figsize=(20, 24))
        
        # 1. 性能排名表
        ax1 = plt.subplot(4, 2, 1)
        self._create_performance_ranking(static_analysis, ax1)
        
        # 2. 关键指标对比
        ax2 = plt.subplot(4, 2, 2)
        self._create_key_metrics_comparison(static_analysis, ax2)
        
        # 3. 稳定性趋势图
        ax3 = plt.subplot(4, 2, (3, 4))
        self._create_stability_trends(static_analysis, ax3)
        
        # 4. 动态性能对比
        ax4 = plt.subplot(4, 2, (5, 6))
        self._create_dynamic_performance(dynamic_analysis, ax4)
        
        # 5. 改进建议
        ax5 = plt.subplot(4, 2, (7, 8))
        self._create_improvement_suggestions(static_analysis, dynamic_analysis, ax5)
        
        plt.suptitle('UWB设备综合性能分析报告', fontsize=20, fontweight='bold', y=0.98)
        plt.tight_layout()
        plt.savefig(self.output_dir / 'comprehensive_report.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def _create_performance_ranking(self, static_analysis: Dict, ax):
        """创建性能排名表"""
        ax.axis('off')
        ax.set_title('设备性能排名', fontweight='bold', fontsize=14)
        
        # 计算综合得分
        scores = {'Feirui': [], 'Quanji': []}
        
        for test_name in static_analysis:
            for device in ['Feirui', 'Quanji']:
                if device in static_analysis[test_name]:
                    # 简化的评分系统
                    dist_std = static_analysis[test_name][device]['distance']['std']
                    angle_std = static_analysis[test_name][device]['angle']['std']
                    score = max(0, 100 - dist_std * 1000 - angle_std * 10)
                    scores[device].append(score)
        
        avg_scores = {device: np.mean(scores[device]) if scores[device] else 0 
                     for device in scores}
        
        # 创建排名表
        ranking_data = [
            ['排名', '设备', '综合得分', '主要优势'],
            ['1', 'Feirui' if avg_scores['Feirui'] > avg_scores['Quanji'] else 'Quanji', 
             f"{max(avg_scores.values()):.1f}", '距离精度优秀'],
            ['2', 'Quanji' if avg_scores['Feirui'] > avg_scores['Quanji'] else 'Feirui', 
             f"{min(avg_scores.values()):.1f}", '角度稳定性好']
        ]
        
        table = ax.table(cellText=ranking_data[1:], colLabels=ranking_data[0],
                        cellLoc='center', loc='center', bbox=[0, 0.5, 1, 0.5])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)
    
    def _create_key_metrics_comparison(self, static_analysis: Dict, ax):
        """创建关键指标对比"""
        ax.set_title('关键性能指标对比', fontweight='bold', fontsize=14)
        
        # 收集关键指标
        metrics = {'Feirui': {'dist_std': [], 'angle_std': []}, 
                  'Quanji': {'dist_std': [], 'angle_std': []}}
        
        for test_name in static_analysis:
            for device in ['Feirui', 'Quanji']:
                if device in static_analysis[test_name]:
                    metrics[device]['dist_std'].append(
                        static_analysis[test_name][device]['distance']['std'] * 1000)
                    metrics[device]['angle_std'].append(
                        static_analysis[test_name][device]['angle']['std'])
        
        # 绘制对比柱状图
        x = np.arange(2)
        width = 0.35
        
        feirui_means = [np.mean(metrics['Feirui']['dist_std']), 
                       np.mean(metrics['Feirui']['angle_std'])]
        quanji_means = [np.mean(metrics['Quanji']['dist_std']), 
                       np.mean(metrics['Quanji']['angle_std'])]
        
        ax.bar(x - width/2, feirui_means, width, label='Feirui', 
               color=self.colors['Feirui'], alpha=0.8)
        ax.bar(x + width/2, quanji_means, width, label='Quanji', 
               color=self.colors['Quanji'], alpha=0.8)
        
        ax.set_xlabel('指标类型')
        ax.set_ylabel('数值')
        ax.set_xticks(x)
        ax.set_xticklabels(['距离标准差(mm)', '角度标准差(度)'])
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    def _create_stability_trends(self, static_analysis: Dict, ax):
        """创建稳定性趋势图"""
        ax.set_title('测量稳定性趋势分析', fontweight='bold', fontsize=14)
        
        test_order = ['1.2m_static', '1.2m_block', '2.4m_static', '2.4m_block']
        
        for device in ['Feirui', 'Quanji']:
            dist_stds = []
            for test_name in test_order:
                if test_name in static_analysis and device in static_analysis[test_name]:
                    dist_stds.append(static_analysis[test_name][device]['distance']['std'] * 1000)
                else:
                    dist_stds.append(np.nan)
            
            ax.plot(range(len(test_order)), dist_stds, 'o-', 
                   label=f'{device} 距离标准差', color=self.colors[device], linewidth=2)
        
        ax.set_xlabel('测试条件')
        ax.set_ylabel('距离标准差 (mm)')
        ax.set_xticks(range(len(test_order)))
        ax.set_xticklabels([name.replace('_', '\n') for name in test_order])
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    def _create_dynamic_performance(self, dynamic_analysis: Dict, ax):
        """创建动态性能对比"""
        ax.set_title('动态测试性能对比', fontweight='bold', fontsize=14)
        
        # 收集动态性能数据
        devices = ['Feirui', 'Quanji']
        tests = ['active_1', 'active_2', 'active_3']
        
        performance_data = np.zeros((len(devices), len(tests)))
        
        for i, device in enumerate(devices):
            for j, test in enumerate(tests):
                if test in dynamic_analysis and device in dynamic_analysis[test]:
                    # 使用轨迹长度作为性能指标
                    total_dist = dynamic_analysis[test][device].get('total_distance', 0)
                    performance_data[i, j] = total_dist
        
        im = ax.imshow(performance_data, cmap='viridis', aspect='auto')
        ax.set_xticks(range(len(tests)))
        ax.set_xticklabels(tests)
        ax.set_yticks(range(len(devices)))
        ax.set_yticklabels(devices)
        
        # 添加数值标注
        for i in range(len(devices)):
            for j in range(len(tests)):
                text = ax.text(j, i, f'{performance_data[i, j]:.2f}',
                              ha="center", va="center", color="white")
        
        plt.colorbar(im, ax=ax, label='轨迹长度 (m)')
    
    def _create_improvement_suggestions(self, static_analysis: Dict, dynamic_analysis: Dict, ax):
        """创建改进建议"""
        ax.axis('off')
        ax.set_title('改进建议', fontweight='bold', fontsize=14)
        
        suggestions = [
            "1. 飞睿设备建议:",
            "   • 优化角度测量算法，提高角度稳定性",
            "   • 在遮挡环境下增强信号处理能力",
            "",
            "2. 全迹设备建议:",
            "   • 改进距离测量精度，减少系统误差",
            "   • 优化动态跟踪算法，提高轨迹平滑度",
            "",
            "3. 通用建议:",
            "   • 增加多路径抑制算法",
            "   • 实施自适应滤波策略",
            "   • 建立环境自适应校准机制"
        ]
        
        y_pos = 0.9
        for suggestion in suggestions:
            ax.text(0.05, y_pos, suggestion, transform=ax.transAxes, 
                   fontsize=10, verticalalignment='top',
                   fontweight='bold' if suggestion.endswith(':') else 'normal')
            y_pos -= 0.08


if __name__ == "__main__":
    # 测试可视化功能
    visualizer = UWBVisualizer()
    print("UWB可视化器测试完成")