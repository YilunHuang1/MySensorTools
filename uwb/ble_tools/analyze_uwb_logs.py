#!/usr/bin/env python3
"""
UWB 测距数据分析脚本
分析不同手机姿态下的测距性能（距离、帧率、角度）
"""
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']  # macOS 中文支持
matplotlib.rcParams['axes.unicode_minus'] = False

# 日志文件配置
LOG_DIR = Path(__file__).parent / "log_iphone_uwb"
LOGS = [
    {"file": "uwb_log_20260211_153924.csv", "label": "1-无遮挡", "color": "#2ecc71"},
    {"file": "uwb_log_20260211_154248.csv", "label": "2-屁股兜(面对)", "color": "#3498db"},
    {"file": "uwb_log_20260211_154429.csv", "label": "3-锁屏", "color": "#9b59b6"},
    {"file": "uwb_log_20260211_154755.csv", "label": "4-屁股兜(背对)", "color": "#e74c3c"},
    {"file": "uwb_log_20260211_155057.csv", "label": "5-侧兜", "color": "#f39c12"},
    {"file": "uwb_log_20260211_155150.csv", "label": "6-不同姿态", "color": "#1abc9c"},
]


def load_data(log_file):
    """加载单个日志文件"""
    df = pd.read_csv(LOG_DIR / log_file)
    # 计算相对时间（从0开始）
    df['time_rel'] = df['elapsed_s'] - df['elapsed_s'].iloc[0]
    return df


def calculate_fps_rolling(df, window='1S'):
    """计算滚动窗口FPS"""
    df_copy = df.copy()
    df_copy['timestamp_dt'] = pd.to_datetime(df_copy['timestamp'], unit='s')
    df_copy = df_copy.set_index('timestamp_dt')
    # 每秒帧数
    fps_rolling = df_copy.resample(window).size()
    return fps_rolling


def plot_distance_vs_time(datasets, output_path):
    """绘制距离随时间变化"""
    fig, ax = plt.subplots(figsize=(14, 6))
    
    for data in datasets:
        df = data['df']
        ax.plot(df['time_rel'], df['distance_m'], 
                label=data['label'], color=data['color'], alpha=0.7, linewidth=1.5)
    
    ax.set_xlabel('时间 (秒)', fontsize=12)
    ax.set_ylabel('距离 (米)', fontsize=12)
    ax.set_title('UWB 测距 - 距离随时间变化', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()


def plot_fps_comparison(datasets, output_path):
    """绘制FPS对比（箱线图 + 折线图）"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # 箱线图 - FPS分布
    fps_data = []
    labels = []
    colors = []
    for data in datasets:
        df = data['df']
        # 使用 frame_gap_ms 计算瞬时FPS
        fps = 1000.0 / df['frame_gap_ms'].replace(0, np.nan)
        fps_data.append(fps.dropna())
        labels.append(data['label'])
        colors.append(data['color'])
    
    bp = ax1.boxplot(fps_data, labels=labels, patch_artist=True, 
                     showmeans=True, meanline=True)
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    
    ax1.set_ylabel('FPS', fontsize=12)
    ax1.set_title('FPS 分布对比（箱线图）', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.tick_params(axis='x', rotation=15)
    
    # 折线图 - FPS随时间变化
    for data in datasets:
        df = data['df']
        fps_rolling = calculate_fps_rolling(df, window='3S')
        ax2.plot(fps_rolling.index, fps_rolling.values, 
                label=data['label'], color=data['color'], alpha=0.7, linewidth=2)
    
    ax2.set_xlabel('时间', fontsize=12)
    ax2.set_ylabel('FPS (3秒滚动窗口)', fontsize=12)
    ax2.set_title('FPS 随时间变化', fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=9)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()


def plot_angle_pitch_scatter(datasets, output_path):
    """绘制角度-俯仰角散点图"""
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()
    
    for idx, data in enumerate(datasets):
        df = data['df']
        ax = axes[idx]
        
        # 用距离作为颜色映射
        scatter = ax.scatter(df['angle_deg'], df['pitch_deg'], 
                            c=df['distance_m'], cmap='viridis', 
                            alpha=0.6, s=20, edgecolors='none')
        
        ax.set_xlabel('角度 (°)', fontsize=10)
        ax.set_ylabel('俯仰角 (°)', fontsize=10)
        ax.set_title(data['label'], fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('距离 (m)', fontsize=9)
    
    plt.suptitle('角度 vs 俯仰角（颜色=距离）', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()


def plot_distance_fps_relationship(datasets, output_path):
    """绘制距离与FPS的关系"""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    for data in datasets:
        df = data['df']
        # 按距离分组，计算平均FPS
        df_copy = df.copy()
        df_copy['distance_bin'] = pd.cut(df_copy['distance_m'], bins=20)
        grouped = df_copy.groupby('distance_bin', observed=True).agg({
            'fps': 'mean',
            'distance_m': 'mean'
        }).dropna()
        
        ax.plot(grouped['distance_m'], grouped['fps'], 
               marker='o', label=data['label'], color=data['color'], 
               alpha=0.7, linewidth=2, markersize=6)
    
    ax.set_xlabel('距离 (米)', fontsize=12)
    ax.set_ylabel('平均 FPS', fontsize=12)
    ax.set_title('距离 vs FPS 关系', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()


def plot_frame_gap_histogram(datasets, output_path):
    """绘制帧间隔直方图（检测丢帧）"""
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()
    
    for idx, data in enumerate(datasets):
        df = data['df']
        ax = axes[idx]
        
        # 过滤掉第一帧（gap=0）
        gaps = df['frame_gap_ms'][df['frame_gap_ms'] > 0]
        
        ax.hist(gaps, bins=50, color=data['color'], alpha=0.7, edgecolor='black')
        ax.axvline(gaps.median(), color='red', linestyle='--', linewidth=2, 
                   label=f'中位数: {gaps.median():.1f}ms')
        ax.axvline(gaps.mean(), color='orange', linestyle='--', linewidth=2, 
                   label=f'平均: {gaps.mean():.1f}ms')
        
        # 标注丢帧（>200ms）
        drop_count = (gaps > 200).sum()
        ax.text(0.95, 0.95, f'丢帧(>200ms): {drop_count}', 
               transform=ax.transAxes, fontsize=9, 
               verticalalignment='top', horizontalalignment='right',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        ax.set_xlabel('帧间隔 (ms)', fontsize=10)
        ax.set_ylabel('频次', fontsize=10)
        ax.set_title(data['label'], fontsize=11, fontweight='bold')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
    
    plt.suptitle('帧间隔分布（丢帧检测）', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()


def generate_summary_stats(datasets, output_path):
    """生成统计摘要表"""
    stats = []
    
    for data in datasets:
        df = data['df']
        gaps = df['frame_gap_ms'][df['frame_gap_ms'] > 0]
        fps_inst = 1000.0 / gaps
        
        stats.append({
            '测试场景': data['label'],
            '总帧数': len(df),
            '测试时长(s)': df['time_rel'].max(),
            '距离范围(m)': f"{df['distance_m'].min():.2f} ~ {df['distance_m'].max():.2f}",
            '平均距离(m)': f"{df['distance_m'].mean():.2f}",
            '平均FPS': f"{fps_inst.mean():.1f}",
            'FPS中位数': f"{fps_inst.median():.1f}",
            '丢帧次数(>200ms)': (gaps > 200).sum(),
            '最大帧间隔(ms)': f"{gaps.max():.1f}",
        })
    
    stats_df = pd.DataFrame(stats)
    stats_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"✅ 保存统计摘要: {output_path}")
    print("\n" + "="*80)
    print(stats_df.to_string(index=False))
    print("="*80)


def main():
    print("=" * 80)
    print("  UWB 测距数据分析")
    print("=" * 80)
    
    # 加载所有数据
    datasets = []
    for log in LOGS:
        try:
            df = load_data(log['file'])
            datasets.append({
                'df': df,
                'label': log['label'],
                'color': log['color']
            })
            print(f"✅ 加载: {log['file']} ({len(df)} 帧)")
        except Exception as e:
            print(f"❌ 加载失败 {log['file']}: {e}")
    
    if not datasets:
        print("❌ 没有成功加载任何数据")
        return
    
    print(f"\n共加载 {len(datasets)} 个数据集\n")
    
    # 输出目录
    output_dir = LOG_DIR / "analysis_results"
    output_dir.mkdir(exist_ok=True)
    
    # 生成图表
    print("📊 生成图表...")
    plot_distance_vs_time(datasets, output_dir / "1_distance_vs_time.png")
    plot_fps_comparison(datasets, output_dir / "2_fps_comparison.png")
    plot_angle_pitch_scatter(datasets, output_dir / "3_angle_pitch_scatter.png")
    plot_distance_fps_relationship(datasets, output_dir / "4_distance_fps_relationship.png")
    plot_frame_gap_histogram(datasets, output_dir / "5_frame_gap_histogram.png")
    
    # 生成统计摘要
    print("\n📋 生成统计摘要...")
    generate_summary_stats(datasets, output_dir / "summary_stats.csv")
    
    print(f"\n✅ 所有分析结果已保存到: {output_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
