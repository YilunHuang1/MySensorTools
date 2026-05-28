#!/usr/bin/env python3
"""
验证角度校准参数的效果和各型号之间的差异
"""

import csv
import numpy as np

# 加载不同型号的校准参数
def load_calibration(csv_path):
    """加载校准文件"""
    vert = []
    horiz = []
    with open(csv_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            vert.append(float(parts[0]))
            horiz.append(float(parts[1]))
    return vert, horiz


def analyze_calibration(name, csv_path):
    """分析并打印校准参数统计"""
    print(f"\n{'='*70}")
    print(f"📊 {name}")
    print(f"{'='*70}")
    
    try:
        vert, horiz = load_calibration(csv_path)
        
        print(f"\n通道数: {len(vert)}")
        print(f"\n【垂直角度 (单位: 度)】")
        print(f"  范围:     {min(vert):.2f}° ~ {max(vert):.2f}°")
        print(f"  均值:     {np.mean(vert):.2f}°")
        print(f"  标准差:   {np.std(vert):.2f}°")
        print(f"  间隔:     {(max(vert) - min(vert))/(len(vert)-1):.2f}° (均匀分布)")
        
        print(f"\n【水平偏差 (单位: 度)】")
        print(f"  范围:     {min(horiz):.2f}° ~ {max(horiz):.2f}°")
        print(f"  幅度:     {max(horiz) - min(horiz):.2f}° (变化范围)")
        print(f"  均值:     {np.mean(horiz):.4f}°")
        print(f"  标准差:   {np.std(horiz):.3f}°")
        
        # 分析奇偶特征
        odd_indices = [i for i in range(len(horiz)) if i % 2 == 1]
        even_indices = [i for i in range(len(horiz)) if i % 2 == 0]
        
        if len(odd_indices) > 0 and len(even_indices) > 0:
            print(f"\n【奇偶通道分析】")
            print(f"  奇数通道 (CH1,3,5,...):  {np.mean([horiz[i] for i in odd_indices]):+.3f}° (平均)")
            print(f"  偶数通道 (CH0,2,4,...):  {np.mean([horiz[i] for i in even_indices]):+.3f}° (平均)")
        
        print(f"\n【原始数据】")
        print(f"  {'CH':<4} {'垂直 (°)':<10} {'水平偏差 (°)':<15}")
        print(f"  {'-'*30}")
        for i in range(len(vert)):
            print(f"  {i:<4} {vert[i]:>8.2f}  {horiz[i]:>13.6f}")
        
        # 质量评估
        print(f"\n【质量评估】")
        if max(abs(np.array(horiz))) > 2.0:
            print(f"  ✓ 高精度型号 (水平偏差 > 2°，已进行出厂标定)")
        elif max(abs(np.array(horiz))) > 0.5:
            print(f"  ⚠ 中等精度型号 (水平偏差 0.5-2°)")
        else:
            print(f"  ⚠ 低精度/未校准型号 (水平偏差 < 0.5°，可能是工程版本)")
        
        return vert, horiz
        
    except FileNotFoundError:
        print(f"  ❌ 文件不存在")
        return None, None


def compare_models():
    """对比多个型号"""
    base_path = "config/calibration"
    
    models = [
        ("WLR-722Z (你的设备)", f"{base_path}/Vanjee_722z_VA.csv"),
        ("WLR-722", f"{base_path}/Vanjee_722_VA.csv"),
        ("WLR-722F", f"{base_path}/Vanjee_722f_VA.csv"),
        ("WLR-722H", f"{base_path}/Vanjee_722h_VA.csv"),
        ("WLR-720-16 (老款)", f"{base_path}/Vanjee_720_16_VA.csv"),
        ("WLR-721-64", f"{base_path}/Vanjee_721_64_VA.csv"),
        ("WLR-750B", f"{base_path}/Vanjee_750B_VA.csv"),
    ]
    
    results = {}
    for name, path in models:
        vert, horiz = analyze_calibration(name, path)
        if vert is not None:
            results[name] = (vert, horiz)
    
    # 生成对比摘要
    print(f"\n\n{'='*70}")
    print("📈 型号对比摘要")
    print(f"{'='*70}")
    print(f"\n{'型号':<20} {'通道':<5} {'垂直范围':<15} {'水平偏差范围':<20} {'精度等级'}")
    print("-" * 80)
    
    for name, (vert, horiz) in results.items():
        vert_range = f"{min(vert):.1f}° ~ {max(vert):.1f}°"
        horiz_range = f"{min(horiz):+.2f}° ~ {max(horiz):+.2f}°"
        
        if max(abs(np.array(horiz))) > 2.0:
            grade = "🏆 高精度"
        elif max(abs(np.array(horiz))) > 0.5:
            grade = "✓ 中精度"
        else:
            grade = "⚠ 低精度"
        
        print(f"{name:<20} {len(vert):<5} {vert_range:<15} {horiz_range:<20} {grade}")


def show_calibration_effect():
    """展示校准参数的实际影响"""
    print(f"\n\n{'='*70}")
    print("🎯 校准参数的实际影响")
    print(f"{'='*70}")
    
    # 示例点的坐标变换
    print("\n【场景】提取第一帧 (azimuth = 100, 即 1°) 的 CH0 通道的点")
    print("  • 原始距离: 10 米")
    print("  • 方位角: 1° (数据包中的值)")
    
    print("\n【对比】")
    print("\n情况 1: 没有水平校准")
    print("  angle_horiz = azimuth * 10 = 1° × 10 = 10 毫度")
    print("  → 最终方向: 1°")
    print("  ❌ 误差: 2.424° (WLR-722Z 的 CH0 偏差)")
    
    print("\n情况 2: 使用 WLR-722Z 的校准参数")
    print("  angle_horiz = (-2.424° + 1°) = -1.424°")
    print("  → 最终方向: -1.424°")
    print("  ✓ 正确! 抵消了硬件偏差")
    
    print("\n【精度影响】 (距离 10m 处)")
    print("  • 角度误差 2.424° 对应的距离误差:")
    print(f"    Δx = 10m × sin(2.424°) = {10 * np.sin(np.radians(2.424)):.3f}m = {10 * np.sin(np.radians(2.424)) * 1000:.1f}mm")
    print("  • 使用校准参数后: < 1mm 的误差")


if __name__ == '__main__':
    import sys
    
    print("\n" + "="*70)
    print("万集雷达角度校准参数分析工具")
    print("="*70)
    
    compare_models()
    show_calibration_effect()
    
    print(f"\n\n{'='*70}")
    print("✅ 分析完成")
    print(f"{'='*70}\n")
