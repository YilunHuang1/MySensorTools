#!/usr/bin/env python3
"""
批量解析 UWB MCAP 文件并计算与文件名真值的差异。

输入：目录下形如 "50_30_25_0.mcap" 的文件（单位均为厘米/度）
 1) 第一个数字：真值距离（cm）
 2) 第二个数字：真值角度（deg）
 3) 第三个数字：真值高度（cm）
 4) 第四个数字：保留位（不参与计算）

测量值提取与差异计算：
 - 距离（cm）：优先使用 distance_filtered（m），否则 distance（m）；统一转换为 cm
 - 角度（deg）：优先使用 angle_filtered，否则 angle；并计算环形上的最小有符号差值 [-180,180)
 - 高度（cm）：以 pitch（deg）与测距（m）估计高度：height = distance * sin(pitch) * 100
   注：若传感器仅提供平面 AoA，本估计为合理近似。

输出：
 - 全量数据 CSV：uwb_all_data_with_diffs.csv（包含原始字段与差异列）
 - 统计摘要 CSV：uwb_diff_stats_summary.csv（均值/标准差/最值）
 - 差异直方图：charts/comparison/{distance,angle,height}_diff_hist.png
 - 简要报告：uwb_analysis_report_latest.md
"""

import re
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from mcap_to_csv_cdr_correct import mcap_to_dataframe, detect_version_from_path
from numpy.typing import ArrayLike

DATASET_DIR = Path("UWB原始数据-216个数据")
OUTPUT_ALL_CSV = Path("uwb_all_data_with_diffs.csv")
OUTPUT_STATS_CSV = Path("uwb_diff_stats_summary.csv")
REPORT_MD = Path("uwb_analysis_report_latest.md")
CHART_DIR = Path("charts/comparison")


def parse_truth_from_filename(filename: str):
    """解析文件名获取 (distance_cm, angle_deg, height_cm)。
    允许格式："50_30_25_0.mcap" 或类似，取前3个数字。
    """
    nums = re.findall(r"-?\d+", filename)
    if len(nums) < 3:
        raise ValueError(f"文件名无法解析出3个真值参数: {filename}")
    dist_cm = int(nums[0])
    angle_deg = int(nums[1])
    height_cm = int(nums[2])
    return dist_cm, angle_deg, height_cm


def angle_signed_diff_vec(measured_deg: ArrayLike, truth_deg: float) -> np.ndarray:
    """计算角度最小有符号差值，范围 [-180, 180)。"""
    arr = np.asarray(measured_deg, dtype=float)
    return ((arr - truth_deg + 180.0) % 360.0) - 180.0


def ensure_dirs():
    CHART_DIR.mkdir(parents=True, exist_ok=True)


def process_file(mcap_path: Path) -> pd.DataFrame:
    dist_cm, angle_deg, height_cm = parse_truth_from_filename(mcap_path.name)
    version = detect_version_from_path(mcap_path)

    df = mcap_to_dataframe(mcap_path, topic_name='/uwb/data')
    if df.empty:
        return df

    # 测距（m）优先使用滤波值
    meas_dist_m = df['distance_filtered'].copy()
    if 'distance_filtered' in df.columns:
        meas_dist_m = df['distance_filtered'].fillna(df['distance'])
    else:
        meas_dist_m = df['distance']

    # 角度（deg）优先使用滤波值
    if 'angle_filtered' in df.columns:
        meas_angle_deg = df['angle_filtered'].fillna(df['angle'])
    else:
        meas_angle_deg = df['angle']

    # 高度估计（cm），基于 pitch 与测距
    pitch_rad = np.radians(df['pitch'].astype(float))
    meas_height_cm = (meas_dist_m.astype(float) * np.sin(pitch_rad) * 100.0)

    # 赋真值
    df['truth_distance_cm'] = dist_cm
    df['truth_angle_deg'] = angle_deg
    df['truth_height_cm'] = height_cm

    # 测量值（统一到 cm/deg）
    df['measured_distance_cm'] = meas_dist_m * 100.0
    df['measured_angle_deg'] = meas_angle_deg
    df['measured_height_cm'] = meas_height_cm

    # 差异（测量 - 真值）
    df['distance_diff_cm'] = df['measured_distance_cm'] - df['truth_distance_cm']
    df['angle_diff_deg'] = angle_signed_diff_vec(df['measured_angle_deg'].to_numpy(dtype=float), float(angle_deg))
    df['height_diff_cm'] = df['measured_height_cm'] - df['truth_height_cm']

    # 元信息
    df['file_name'] = mcap_path.name
    df['version'] = version

    return df


def summarize_stats(df_all: pd.DataFrame) -> pd.DataFrame:
    metrics = ['distance_diff_cm', 'angle_diff_deg', 'height_diff_cm']
    summary = {}
    for m in metrics:
        if m in df_all.columns:
            series = df_all[m].astype(float)
            summary[m] = {
                'mean': float(series.mean()),
                'std': float(series.std(ddof=1)),
                'min': float(series.min()),
                'max': float(series.max()),
                'count': series.count(),
            }
    return pd.DataFrame(summary).transpose()


def plot_histograms(df_all: pd.DataFrame):
    plt.figure(figsize=(7,5))
    plt.hist(df_all['distance_diff_cm'].dropna().astype(float), bins=50, color='steelblue', edgecolor='black')
    plt.title('Distance Difference (cm) Histogram')
    plt.xlabel('distance_diff_cm')
    plt.ylabel('count')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHART_DIR / 'distance_diff_hist.png', dpi=150)
    plt.close()

    plt.figure(figsize=(7,5))
    plt.hist(df_all['angle_diff_deg'].dropna().astype(float), bins=50, color='darkorange', edgecolor='black')
    plt.title('Angle Difference (deg) Histogram')
    plt.xlabel('angle_diff_deg')
    plt.ylabel('count')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHART_DIR / 'angle_diff_hist.png', dpi=150)
    plt.close()

    plt.figure(figsize=(7,5))
    plt.hist(df_all['height_diff_cm'].dropna().astype(float), bins=50, color='seagreen', edgecolor='black')
    plt.title('Height Difference (cm) Histogram')
    plt.xlabel('height_diff_cm')
    plt.ylabel('count')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHART_DIR / 'height_diff_hist.png', dpi=150)
    plt.close()


def write_report(stats_df: pd.DataFrame, total_rows: int, total_files: int):
    lines = []
    lines.append('# UWB差异分析简要报告')
    lines.append('')
    lines.append(f'- 总文件数: {total_files}')
    lines.append(f'- 总数据条数: {total_rows}')
    lines.append('')
    lines.append('## 差异统计摘要（全量）')
    lines.append('')
    for metric in ['distance_diff_cm', 'angle_diff_deg', 'height_diff_cm']:
        if metric in stats_df.index:
            row = stats_df.loc[metric]
            mean_val = float(row['mean']) if 'mean' in row.index else np.nan
            std_val = float(row['std']) if 'std' in row.index else np.nan
            min_val = float(row['min']) if 'min' in row.index else np.nan
            max_val = float(row['max']) if 'max' in row.index else np.nan
            count_val = row['count'] if 'count' in row.index else ''
            lines.append(f'- {metric}: 均值 {mean_val:.3f}, 标准差 {std_val:.3f}, 最小 {min_val:.3f}, 最大 {max_val:.3f}, 样本数 {count_val}')
    lines.append('')
    lines.append('## 直方图')
    lines.append(f'- 距离差异直方图: {CHART_DIR / "distance_diff_hist.png"}')
    lines.append(f'- 角度差异直方图: {CHART_DIR / "angle_diff_hist.png"}')
    lines.append(f'- 高度差异直方图: {CHART_DIR / "height_diff_hist.png"}')
    lines.append('')
    lines.append('> 说明：距离单位为厘米，角度单位为度，高度以 pitch 与测距估计（distance * sin(pitch)）。若设备仅提供平面测量，该估计用于近似评估垂直误差。')
    REPORT_MD.write_text('\n'.join(lines), encoding='utf-8')


def main():
    print(f"扫描目录: {DATASET_DIR}")
    if not DATASET_DIR.exists():
        raise FileNotFoundError(f"数据目录不存在: {DATASET_DIR}")

    ensure_dirs()

    files = sorted(DATASET_DIR.glob('*.mcap'))
    if not files:
        print("未找到任何 .mcap 文件")
        return

    print(f"共发现 {len(files)} 个 MCAP 文件，开始处理...")
    df_all_list = []

    for i, fp in enumerate(files, 1):
        try:
            print(f"[{i}/{len(files)}] 处理: {fp.name}")
            df = process_file(fp)
            if not df.empty:
                df_all_list.append(df)
            else:
                print(f"警告: {fp.name} 未解析到有效数据")
        except Exception as e:
            print(f"错误: 处理 {fp.name} 失败: {e}")

    if not df_all_list:
        print("错误: 所有文件均未解析到数据")
        return

    df_all = pd.concat(df_all_list, ignore_index=True)
    print(f"合并后总数据条数: {len(df_all)}")

    # 保存全量CSV
    df_all.to_csv(OUTPUT_ALL_CSV, index=False)
    print(f"✓ 全量CSV已保存: {OUTPUT_ALL_CSV}")

    # 统计与直方图
    stats_df = summarize_stats(df_all)
    stats_df.to_csv(OUTPUT_STATS_CSV)
    print(f"✓ 统计摘要已保存: {OUTPUT_STATS_CSV}")

    plot_histograms(df_all)
    print(f"✓ 直方图已保存到: {CHART_DIR}")

    write_report(stats_df, total_rows=len(df_all), total_files=len(files))
    print(f"✓ 简要报告已保存: {REPORT_MD}")


if __name__ == '__main__':
    main()