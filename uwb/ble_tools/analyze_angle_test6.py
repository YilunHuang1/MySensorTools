#!/usr/bin/env python3
"""
分析测试6（不同姿态）的角度变化
"""
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
matplotlib.rcParams['axes.unicode_minus'] = False

# 加载最后一组数据
LOG_FILE = Path(__file__).parent / "log_iphone_uwb" / "uwb_log_20260211_155150.csv"
OUTPUT_DIR = Path(__file__).parent / "log_iphone_uwb" / "analysis_results"

def load_data():
    df = pd.read_csv(LOG_FILE)
    df['time_rel'] = df['elapsed_s'] - df['elapsed_s'].iloc[0]
    return df

def plot_angle_analysis(df, output_path):
    """综合角度分析图"""
    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)
    
    # 1. 角度随时间变化
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(df['time_rel'], df['angle_deg'], color='#1abc9c', linewidth=2, alpha=0.8)
    ax1.set_xlabel('时间 (秒)', fontsize=12)
    ax1.set_ylabel('角度 (°)', fontsize=12)
    ax1.set_title('角度随时间变化', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color='red', linestyle='--', alpha=0.5, label='0°参考线')
    ax1.legend()
    
    # 2. 角度分布直方图
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.hist(df['angle_deg'], bins=50, color='#3498db', alpha=0.7, edgecolor='black')
    ax2.axvline(df['angle_deg'].mean(), color='red', linestyle='--', linewidth=2, 
                label=f'均值: {df["angle_deg"].mean():.1f}°')
    ax2.axvline(df['angle_deg'].median(), color='orange', linestyle='--', linewidth=2, 
                label=f'中位数: {df["angle_deg"].median():.1f}°')
    ax2.set_xlabel('角度 (°)', fontsize=12)
    ax2.set_ylabel('频次', fontsize=12)
    ax2.set_title('角度分布', fontsize=13, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    
    # 3. 角度变化率（角速度）
    ax3 = fig.add_subplot(gs[1, 1])
    angle_diff = df['angle_deg'].diff()
    time_diff = df['time_rel'].diff()
    angular_velocity = angle_diff / time_diff  # 度/秒
    
    ax3.plot(df['time_rel'][1:], angular_velocity[1:], color='#e74c3c', alpha=0.6, linewidth=1)
    ax3.set_xlabel('时间 (秒)', fontsize=12)
    ax3.set_ylabel('角速度 (°/s)', fontsize=12)
    ax3.set_title('角度变化率（角速度）', fontsize=13, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    ax3.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    
    # 4. 角度 vs 距离散点图
    ax4 = fig.add_subplot(gs[2, 0])
    scatter = ax4.scatter(df['distance_m'], df['angle_deg'], 
                         c=df['time_rel'], cmap='viridis', 
                         alpha=0.6, s=30, edgecolors='none')
    ax4.set_xlabel('距离 (米)', fontsize=12)
    ax4.set_ylabel('角度 (°)', fontsize=12)
    ax4.set_title('角度 vs 距离（颜色=时间）', fontsize=13, fontweight='bold')
    ax4.grid(True, alpha=0.3)
    cbar = plt.colorbar(scatter, ax=ax4)
    cbar.set_label('时间 (秒)', fontsize=10)
    
    # 5. 角度稳定性分析（滚动窗口标准差）
    ax5 = fig.add_subplot(gs[2, 1])
    window_size = 10  # 10帧滚动窗口
    rolling_std = df['angle_deg'].rolling(window=window_size).std()
    
    ax5.plot(df['time_rel'], rolling_std, color='#9b59b6', linewidth=2, alpha=0.8)
    ax5.set_xlabel('时间 (秒)', fontsize=12)
    ax5.set_ylabel('角度标准差 (°)', fontsize=12)
    ax5.set_title(f'角度稳定性（{window_size}帧滚动窗口标准差）', fontsize=13, fontweight='bold')
    ax5.grid(True, alpha=0.3)
    ax5.fill_between(df['time_rel'], rolling_std, alpha=0.3, color='#9b59b6')
    
    plt.suptitle('测试6 - 不同姿态角度分析', fontsize=16, fontweight='bold', y=0.995)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 保存: {output_path}")
    plt.close()

def analyze_angle_segments(df):
    """分析角度变化的不同阶段"""
    print("\n" + "="*80)
    print("  角度变化阶段分析")
    print("="*80)
    
    # 计算角度变化率
    angle_diff = df['angle_deg'].diff().abs()
    
    # 定义阶段：角度变化率阈值
    stable_threshold = 1.0  # 度/帧，低于此为稳定
    changing_threshold = 5.0  # 度/帧，高于此为快速变化
    
    stable_frames = (angle_diff < stable_threshold).sum()
    moderate_frames = ((angle_diff >= stable_threshold) & (angle_diff < changing_threshold)).sum()
    changing_frames = (angle_diff >= changing_threshold).sum()
    
    total = len(df) - 1  # 减去第一帧（无diff）
    
    print(f"\n角度稳定阶段 (<{stable_threshold}°/帧): {stable_frames} 帧 ({stable_frames/total*100:.1f}%)")
    print(f"角度缓慢变化 ({stable_threshold}-{changing_threshold}°/帧): {moderate_frames} 帧 ({moderate_frames/total*100:.1f}%)")
    print(f"角度快速变化 (>{changing_threshold}°/帧): {changing_frames} 帧 ({changing_frames/total*100:.1f}%)")
    
    # 角度范围分析
    print(f"\n角度统计:")
    print(f"  最小值: {df['angle_deg'].min():.2f}°")
    print(f"  最大值: {df['angle_deg'].max():.2f}°")
    print(f"  范围: {df['angle_deg'].max() - df['angle_deg'].min():.2f}°")
    print(f"  均值: {df['angle_deg'].mean():.2f}°")
    print(f"  中位数: {df['angle_deg'].median():.2f}°")
    print(f"  标准差: {df['angle_deg'].std():.2f}°")
    
    # 找出角度变化最剧烈的时刻
    max_change_idx = angle_diff.idxmax()
    if pd.notna(max_change_idx):
        max_change = angle_diff[max_change_idx]
        time_at_max = df.loc[max_change_idx, 'time_rel']
        angle_before = df.loc[max_change_idx-1, 'angle_deg']
        angle_after = df.loc[max_change_idx, 'angle_deg']
        
        print(f"\n最大角度变化:")
        print(f"  时刻: {time_at_max:.1f}秒")
        print(f"  变化量: {max_change:.2f}°")
        print(f"  从 {angle_before:.1f}° 变到 {angle_after:.1f}°")
    
    print("="*80 + "\n")

def main():
    print("="*80)
    print("  测试6 - 不同姿态角度分析")
    print("="*80)
    
    df = load_data()
    print(f"✅ 加载数据: {len(df)} 帧")
    print(f"   时长: {df['time_rel'].max():.1f} 秒")
    
    # 生成综合分析图
    output_path = OUTPUT_DIR / "6_angle_detailed_analysis.png"
    plot_angle_analysis(df, output_path)
    
    # 文字分析
    analyze_angle_segments(df)
    
    print(f"✅ 分析完成！图表已保存到: {output_path}")
    print("="*80)

if __name__ == "__main__":
    main()
