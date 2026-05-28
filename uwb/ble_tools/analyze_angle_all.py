#!/usr/bin/env python3
"""
分析所有6组测试的角度变化
"""
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
matplotlib.rcParams['axes.unicode_minus'] = False

# 日志文件配置
LOG_DIR = Path(__file__).parent / "log_iphone_uwb"
OUTPUT_DIR = LOG_DIR / "analysis_results"

LOGS = [
    {"file": "uwb_log_20260211_153924.csv", "label": "1-无遮挡", "color": "#2ecc71"},
    {"file": "uwb_log_20260211_154248.csv", "label": "2-屁股兜(面对)", "color": "#3498db"},
    {"file": "uwb_log_20260211_154429.csv", "label": "3-锁屏", "color": "#9b59b6"},
    {"file": "uwb_log_20260211_154755.csv", "label": "4-屁股兜(背对)", "color": "#e74c3c"},
    {"file": "uwb_log_20260211_155057.csv", "label": "5-侧兜", "color": "#f39c12"},
    {"file": "uwb_log_20260211_155150.csv", "label": "6-不同姿态", "color": "#1abc9c"},
]

def load_data(log_file):
    df = pd.read_csv(LOG_DIR / log_file)
    df['time_rel'] = df['elapsed_s'] - df['elapsed_s'].iloc[0]
    return df

def plot_all_angles_comparison(datasets, output_path):
    """对比所有测试的角度变化"""
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    for idx, data in enumerate(datasets):
        df = data['df']
        ax = axes[idx]
        
        # 角度随时间变化
        ax.plot(df['time_rel'], df['angle_deg'], 
               color=data['color'], linewidth=1.5, alpha=0.8)
        ax.axhline(y=0, color='red', linestyle='--', alpha=0.3, linewidth=1)
        
        ax.set_xlabel('时间 (秒)', fontsize=10)
        ax.set_ylabel('角度 (°)', fontsize=10)
        ax.set_title(data['label'], fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # 添加统计信息
        stats_text = f"范围: {df['angle_deg'].min():.1f}° ~ {df['angle_deg'].max():.1f}°\n"
        stats_text += f"均值: {df['angle_deg'].mean():.1f}°\n"
        stats_text += f"标准差: {df['angle_deg'].std():.1f}°"
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=8, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.suptitle('所有测试 - 角度随时间变化对比', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()

def plot_angle_distributions(datasets, output_path):
    """角度分布对比（箱线图 + 直方图）"""
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 2], hspace=0.3)
    
    # 箱线图
    ax1 = fig.add_subplot(gs[0])
    angle_data = []
    labels = []
    colors = []
    for data in datasets:
        angle_data.append(data['df']['angle_deg'])
        labels.append(data['label'])
        colors.append(data['color'])
    
    bp = ax1.boxplot(angle_data, labels=labels, patch_artist=True,
                     showmeans=True, meanline=True)
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    
    ax1.set_ylabel('角度 (°)', fontsize=12)
    ax1.set_title('角度分布对比（箱线图）', fontsize=13, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.axhline(y=0, color='red', linestyle='--', alpha=0.3)
    ax1.tick_params(axis='x', rotation=15)
    
    # 直方图（重叠）
    ax2 = fig.add_subplot(gs[1])
    for data in datasets:
        ax2.hist(data['df']['angle_deg'], bins=40, 
                alpha=0.5, label=data['label'], color=data['color'],
                edgecolor='black', linewidth=0.5)
    
    ax2.set_xlabel('角度 (°)', fontsize=12)
    ax2.set_ylabel('频次', fontsize=12)
    ax2.set_title('角度分布直方图（重叠）', fontsize=13, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.axvline(x=0, color='red', linestyle='--', alpha=0.3, linewidth=2)
    
    plt.suptitle('角度分布统计对比', fontsize=14, fontweight='bold')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()

def plot_angular_velocity_comparison(datasets, output_path):
    """角速度对比"""
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    for idx, data in enumerate(datasets):
        df = data['df']
        ax = axes[idx]
        
        # 计算角速度
        angle_diff = df['angle_deg'].diff()
        time_diff = df['time_rel'].diff()
        angular_velocity = angle_diff / time_diff
        
        ax.plot(df['time_rel'][1:], angular_velocity[1:], 
               color=data['color'], alpha=0.6, linewidth=1)
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        
        ax.set_xlabel('时间 (秒)', fontsize=10)
        ax.set_ylabel('角速度 (°/s)', fontsize=10)
        ax.set_title(data['label'], fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # 统计信息
        abs_vel = angular_velocity.abs()
        stats_text = f"最大: {abs_vel.max():.1f}°/s\n"
        stats_text += f"平均: {abs_vel.mean():.1f}°/s"
        ax.text(0.98, 0.98, stats_text, transform=ax.transAxes,
               fontsize=8, verticalalignment='top', horizontalalignment='right',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.suptitle('角速度对比（角度变化率）', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()

def analyze_all_angles(datasets):
    """生成所有测试的角度统计表"""
    print("\n" + "="*100)
    print("  所有测试角度统计对比")
    print("="*100)
    
    stats = []
    for data in datasets:
        df = data['df']
        angle_diff = df['angle_deg'].diff().abs()
        
        # 稳定性分类
        stable = (angle_diff < 1.0).sum()
        moderate = ((angle_diff >= 1.0) & (angle_diff < 5.0)).sum()
        changing = (angle_diff >= 5.0).sum()
        total = len(df) - 1
        
        stats.append({
            '测试场景': data['label'],
            '帧数': len(df),
            '角度范围': f"{df['angle_deg'].min():.1f}° ~ {df['angle_deg'].max():.1f}°",
            '跨度': f"{df['angle_deg'].max() - df['angle_deg'].min():.1f}°",
            '均值': f"{df['angle_deg'].mean():.1f}°",
            '标准差': f"{df['angle_deg'].std():.1f}°",
            '稳定(<1°/帧)': f"{stable/total*100:.1f}%",
            '缓变(1-5°/帧)': f"{moderate/total*100:.1f}%",
            '快变(>5°/帧)': f"{changing/total*100:.1f}%",
            '最大变化': f"{angle_diff.max():.2f}°/帧",
        })
    
    stats_df = pd.DataFrame(stats)
    
    # 保存CSV
    output_csv = OUTPUT_DIR / "angle_stats_all.csv"
    stats_df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"\n✅ 保存统计表: {output_csv}")
    
    # 打印表格
    print("\n" + stats_df.to_string(index=False))
    print("\n" + "="*100 + "\n")

def main():
    print("="*100)
    print("  所有测试角度分析")
    print("="*100)
    
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
    
    print(f"\n共加载 {len(datasets)} 个数据集\n")
    
    # 生成图表
    print("📊 生成角度分析图表...")
    plot_all_angles_comparison(datasets, OUTPUT_DIR / "7_all_angles_comparison.png")
    plot_angle_distributions(datasets, OUTPUT_DIR / "8_angle_distributions.png")
    plot_angular_velocity_comparison(datasets, OUTPUT_DIR / "9_angular_velocity.png")
    
    # 统计分析
    print("\n📋 生成统计分析...")
    analyze_all_angles(datasets)
    
    print(f"✅ 所有角度分析完成！结果保存在: {OUTPUT_DIR}")
    print("="*100)

if __name__ == "__main__":
    main()
