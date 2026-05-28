import os
import numpy as np
from rosbags.rosbag2 import Reader
from rosbags.serde import deserialize_cdr
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# ================= 配置区域 =================

# 每个条件：bag 路径 + 多个起始时间点（每个时间点截取 DURATION 秒）
# 多段数据会合并后统计，时域图分段展示
#
# 用法：在 Foxglove 中观察每个 bag，找到电批振动的起始时间戳，
#       填入 starts 列表中。可以填多个时间点，统计会合并所有段。
#
DATA_ROOT = os.environ.get("VIBRATION_DATA_ROOT", "./dog_imu_data")

CONFIGS = {
    "1_No_Pad": {
        "path": f"{DATA_ROOT}/group1/vibration_test_20260309_161200",
        "starts": [
            1773043936.208474816,
            1773043963.186318846,
            1773043990.760881306,
            1773044018.963569219,
        ],
    },
    "2_Shell_Pad": {
        "path": f"{DATA_ROOT}/group2/vibration_test_20260309_155402",
        "starts": [
            1773042857.215298592,
            1773042888.556934182,
            1773042898.442204541,
            1773042928.812074609,
            1773042974.910767578,
        ],
    },
    "3_Mount_Pad": {
        "path": f"{DATA_ROOT}/group3/vibration_test_20260309_163309",
        "starts": [
            1773045210.883213583,
            1773045257.396017646,
            1773045289.377710042,
            1773045319.423568936
        ],
    },
    "4_Mount_Pad_2": {
        "path": f"{DATA_ROOT}/group4/vibration_test_20260309_173803",
        "starts": [
            1773049106.534006049,
        ],
    },
}

DURATION = 1.5  # 每段截取时长 (秒)
TOPIC_NAME = '/imu_raw'
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 显示配置
COLORS = {'1_No_Pad': '#E74C3C', '2_Shell_Pad': '#3498DB', '3_Mount_Pad': '#2ECC71', '4_Mount_Pad_2': '#9B59B6'}
LABELS_DISPLAY = {
    '1_No_Pad': 'Group1: No Pad',
    '2_Shell_Pad': 'Group2: Shell Pad',
    '3_Mount_Pad': 'Group3: Mount Pad 1',
    '4_Mount_Pad_2': 'Group4: Mount Pad 2',
}

# ============================================


def extract_imu_data(bag_path, start_times, duration):
    """从 bag 中提取多个时间段的 IMU 数据，合并返回
    
    Args:
        bag_path: bag 文件夹路径
        start_times: 起始时间列表 [t1, t2, ...]，每个截取 duration 秒
        duration: 每段截取时长
    
    Returns:
        合并后的数据 dict，time 为从各段起始的相对时间 + 段偏移
        同时返回 segments 列表用于分段绘图
    """
    if not os.path.exists(bag_path):
        print(f"  ⚠️  找不到路径 {bag_path}")
        return None

    # 先读取 bag 中所有 IMU 数据（一次性读完，避免多次打开）
    all_msgs = []
    with Reader(bag_path) as reader:
        connections = [x for x in reader.connections if x.topic == TOPIC_NAME]
        if not connections:
            print(f"  ⚠️  在 {bag_path} 中找不到 topic {TOPIC_NAME}")
            return None
        for connection, timestamp, rawdata in reader.messages(connections=connections):
            t_sec = timestamp / 1e9
            msg = deserialize_cdr(rawdata, connection.msgtype)
            all_msgs.append((t_sec, msg))

    if not all_msgs:
        print(f"  ⚠️  {bag_path} 中没有 IMU 数据")
        return None

    # 从缓存中按每个时间窗口截取
    segments = []  # 每段的数据，用于分段绘图
    merged = {'time': [], 'gyro_x': [], 'gyro_y': [], 'gyro_z': [],
              'accel_x': [], 'accel_y': [], 'accel_z': []}

    for seg_idx, start_time in enumerate(start_times):
        seg = {'time': [], 'gyro_x': [], 'gyro_y': [], 'gyro_z': [],
               'accel_x': [], 'accel_y': [], 'accel_z': []}
        count = 0
        for t_sec, msg in all_msgs:
            if t_sec < start_time:
                continue
            if t_sec > start_time + duration:
                break
            # 段内相对时间
            t_rel = t_sec - start_time
            seg['time'].append(t_rel)
            seg['gyro_x'].append(msg.angular_velocity.x)
            seg['gyro_y'].append(msg.angular_velocity.y)
            seg['gyro_z'].append(msg.angular_velocity.z)
            seg['accel_x'].append(msg.linear_acceleration.x)
            seg['accel_y'].append(msg.linear_acceleration.y)
            seg['accel_z'].append(msg.linear_acceleration.z)
            count += 1

        if count == 0:
            print(f"  ⚠️  段 {seg_idx+1} (t={start_time:.3f}) 无数据，跳过")
            continue

        print(f"  📍 段 {seg_idx+1}/{len(start_times)}: t={start_time:.3f}, 提取 {count} 条")
        # 转 numpy
        for k in seg:
            seg[k] = np.array(seg[k])
        segments.append(seg)

        # 合并到总数据（time 加段偏移，使多段在时间轴上连续）
        time_offset = seg_idx * (duration + 0.2)  # 段间留 0.2s 间隔便于视觉区分
        for k in merged:
            if k == 'time':
                merged[k].extend((seg[k] + time_offset).tolist())
            else:
                merged[k].extend(seg[k].tolist())

    if not merged['time']:
        return None

    result = {k: np.array(v) for k, v in merged.items()}
    result['segments'] = segments  # 附带分段信息
    result['n_segments'] = len(segments)
    return result


def compute_stats(data):
    """计算单组数据的统计量"""
    stats = {}
    for sensor in ['gyro', 'accel']:
        unit = 'dps' if sensor == 'gyro' else 'g'
        for axis in ['x', 'y', 'z']:
            key = f"{sensor}_{axis}"
            arr = data[key]
            stats[key] = {
                'mean': np.mean(arr),
                'std': np.std(arr),
                'rms': np.sqrt(np.mean(arr**2)),
                'peak_to_peak': np.max(arr) - np.min(arr),
                'max_abs': np.max(np.abs(arr)),
                'unit': unit,
            }
    # 合成向量 RMS (三轴平方和开根号的 RMS)
    for sensor in ['gyro', 'accel']:
        unit = 'dps' if sensor == 'gyro' else 'g'
        magnitude = np.sqrt(data[f'{sensor}_x']**2 + data[f'{sensor}_y']**2 + data[f'{sensor}_z']**2)
        # 对加速度计减去静态重力 (约 1g)，计算振动分量
        if sensor == 'accel':
            magnitude_vib = magnitude - np.mean(magnitude)  # 去除直流分量
            stats[f'{sensor}_vibration_rms'] = np.sqrt(np.mean(magnitude_vib**2))
        stats[f'{sensor}_magnitude_rms'] = np.sqrt(np.mean(magnitude**2))
    return stats


def compute_fft(data, sensor, axis):
    """计算单轴 FFT"""
    arr = data[f'{sensor}_{axis}']
    dt = np.mean(np.diff(data['time'])) if len(data['time']) > 1 else 0.01
    fs = 1.0 / dt  # 采样率
    n = len(arr)
    # 去均值
    arr_centered = arr - np.mean(arr)
    # 加窗 (Hanning)
    window = np.hanning(n)
    fft_vals = np.fft.rfft(arr_centered * window)
    fft_mag = 2.0 / n * np.abs(fft_vals)
    freqs = np.fft.rfftfreq(n, d=dt)
    return freqs, fft_mag, fs


def print_stats_table(all_stats, baseline_key='1_No_Pad'):
    """打印统计对比表格，包含减振率"""
    print("\n" + "=" * 100)
    print("                       IMU 振动统计分析结果")
    print("=" * 100)

    for sensor, sensor_name in [('gyro', '陀螺仪 (Gyroscope)'), ('accel', '加速度计 (Accelerometer)')]:
        unit = 'dps' if sensor == 'gyro' else 'g'
        print(f"\n{'─' * 100}")
        print(f"  {sensor_name}  [单位: {unit}]")
        print(f"{'─' * 100}")
        print(f"  {'条件':<20} {'轴':>4}  {'均值':>10}  {'标准差':>10}  {'RMS':>10}  {'峰峰值':>10}  {'最大|值|':>10}  {'RMS减振率':>10}")
        print(f"  {'─' * 94}")

        for cond_name, stats in all_stats.items():
            for axis in ['x', 'y', 'z']:
                key = f'{sensor}_{axis}'
                s = stats[key]
                # 计算减振率
                if baseline_key in all_stats and cond_name != baseline_key:
                    baseline_rms = all_stats[baseline_key][key]['rms']
                    reduction = (1.0 - s['rms'] / baseline_rms) * 100 if baseline_rms > 0 else 0
                    reduction_str = f"{reduction:+.1f}%"
                else:
                    reduction_str = "baseline"

                print(f"  {LABELS_DISPLAY.get(cond_name, cond_name):<20} {axis.upper():>4}"
                      f"  {s['mean']:>10.4f}  {s['std']:>10.4f}  {s['rms']:>10.4f}"
                      f"  {s['peak_to_peak']:>10.4f}  {s['max_abs']:>10.4f}  {reduction_str:>10}")
            print()

        # 合成向量 RMS 对比
        print(f"  {'--- 三轴合成 ---'}")
        print(f"  {'条件':<20} {'合成 RMS':>10}", end="")
        if sensor == 'accel':
            print(f"  {'振动 RMS (去重力)':>18}", end="")
        print(f"  {'RMS减振率':>10}")
        for cond_name, stats in all_stats.items():
            mag_key = f'{sensor}_magnitude_rms'
            mag_rms = stats[mag_key]
            if baseline_key in all_stats and cond_name != baseline_key:
                baseline_mag = all_stats[baseline_key][mag_key]
                reduction = (1.0 - mag_rms / baseline_mag) * 100 if baseline_mag > 0 else 0
                reduction_str = f"{reduction:+.1f}%"
            else:
                reduction_str = "baseline"
            print(f"  {LABELS_DISPLAY.get(cond_name, cond_name):<20} {mag_rms:>10.4f}", end="")
            if sensor == 'accel':
                vib_rms = stats.get(f'{sensor}_vibration_rms', 0)
                print(f"  {vib_rms:>18.4f}", end="")
            print(f"  {reduction_str:>10}")

    print(f"\n{'=' * 100}\n")


def plot_time_domain(all_data, save_path):
    """绘制时域波形对比图：上3行陀螺仪，下3行加速度计"""
    fig, axs = plt.subplots(6, 1, figsize=(14, 16), sharex=True)
    fig.suptitle('IMU Vibration: Time-Domain Comparison (Gyro + Accel)', fontsize=16, fontweight='bold')

    plot_configs = [
        ('gyro_x',  'Gyro X (dps)',   'Pitch'),
        ('gyro_y',  'Gyro Y (dps)',   'Roll'),
        ('gyro_z',  'Gyro Z (dps)',   'Yaw'),
        ('accel_x', 'Accel X (g)',    'Fore-Aft'),
        ('accel_y', 'Accel Y (g)',    'Lateral'),
        ('accel_z', 'Accel Z (g)',    'Vertical'),
    ]

    for idx, (key, ylabel, desc) in enumerate(plot_configs):
        ax = axs[idx]
        for cond_name, data in all_data.items():
            if data is None:
                continue
            label = LABELS_DISPLAY.get(cond_name, cond_name)
            ax.plot(data['time'], data[key], label=label,
                    color=COLORS[cond_name], alpha=0.75, linewidth=1.0)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(desc, fontsize=10, loc='left', pad=2, fontstyle='italic', color='gray')
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.legend(loc='upper right', fontsize=8)
        # 在陀螺仪和加速度计之间加分隔
        if idx == 2:
            ax.axhline(y=0, color='black', linewidth=0.3)

    axs[5].set_xlabel('Time (seconds) from screwdriver start', fontsize=11)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"  📊 时域波形图已保存: {save_path}")


def plot_fft(all_data, save_path):
    """绘制频谱对比图"""
    fig, axs = plt.subplots(2, 3, figsize=(16, 8))
    fig.suptitle('IMU Vibration: Frequency Spectrum (FFT)', fontsize=16, fontweight='bold')

    sensors = ['gyro', 'accel']
    sensor_names = ['Gyroscope', 'Accelerometer']
    axes = ['x', 'y', 'z']
    axis_names = ['X', 'Y', 'Z']

    for row, (sensor, sensor_name) in enumerate(zip(sensors, sensor_names)):
        for col, (axis, axis_name) in enumerate(zip(axes, axis_names)):
            ax = axs[row][col]
            for cond_name, data in all_data.items():
                if data is None:
                    continue
                freqs, fft_mag, fs = compute_fft(data, sensor, axis)
                label = LABELS_DISPLAY.get(cond_name, cond_name)
                ax.plot(freqs, fft_mag, label=label,
                        color=COLORS[cond_name], alpha=0.8, linewidth=1.2)

            unit = 'dps' if sensor == 'gyro' else 'g'
            ax.set_title(f'{sensor_name} {axis_name}', fontsize=10)
            ax.set_ylabel(f'Amplitude ({unit})', fontsize=8)
            ax.set_xlabel('Frequency (Hz)', fontsize=8)
            ax.grid(True, linestyle='--', alpha=0.4)
            ax.legend(fontsize=7)
            ax.set_xlim(0, None)  # 从 0Hz 开始

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"  📊 频谱分析图已保存: {save_path}")


def plot_stats_bar(all_stats, save_path):
    """绘制 RMS 和峰峰值的柱状对比图"""
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('IMU Vibration: Statistical Comparison', fontsize=16, fontweight='bold')

    cond_names = list(all_stats.keys())
    display_names = [LABELS_DISPLAY.get(c, c) for c in cond_names]
    x = np.arange(3)  # 3 axes
    width = 0.25

    for row, (sensor, sensor_name, unit) in enumerate([
        ('gyro', 'Gyroscope', 'dps'),
        ('accel', 'Accelerometer', 'g')
    ]):
        for col, (metric, metric_name) in enumerate([('rms', 'RMS'), ('peak_to_peak', 'Peak-to-Peak')]):
            ax = axs[row][col]
            for i, cond_name in enumerate(cond_names):
                values = [all_stats[cond_name][f'{sensor}_{axis}'][metric] for axis in ['x', 'y', 'z']]
                bars = ax.bar(x + i * width, values, width, label=display_names[i],
                              color=COLORS[cond_name], alpha=0.85, edgecolor='white')
                # 在柱子顶部标数值
                for bar, val in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                            f'{val:.3f}', ha='center', va='bottom', fontsize=7)

            ax.set_ylabel(f'{metric_name} ({unit})', fontsize=9)
            ax.set_title(f'{sensor_name} — {metric_name}', fontsize=11)
            ax.set_xticks(x + width)
            ax.set_xticklabels(['X', 'Y', 'Z'])
            ax.legend(fontsize=8)
            ax.grid(True, axis='y', linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"  📊 统计柱状图已保存: {save_path}")


def save_stats_csv(all_stats, save_path):
    """导出统计数据到 CSV"""
    rows = []
    header = "条件,传感器,轴,均值,标准差,RMS,峰峰值,最大绝对值,单位"
    rows.append(header)
    for cond_name, stats in all_stats.items():
        display = LABELS_DISPLAY.get(cond_name, cond_name)
        for sensor in ['gyro', 'accel']:
            for axis in ['x', 'y', 'z']:
                key = f'{sensor}_{axis}'
                s = stats[key]
                sensor_cn = '陀螺仪' if sensor == 'gyro' else '加速度计'
                rows.append(f"{display},{sensor_cn},{axis.upper()},{s['mean']:.6f},{s['std']:.6f},"
                            f"{s['rms']:.6f},{s['peak_to_peak']:.6f},{s['max_abs']:.6f},{s['unit']}")
    with open(save_path, 'w', encoding='utf-8-sig') as f:
        f.write('\n'.join(rows))
    print(f"  📄 统计数据 CSV 已保存: {save_path}")


def main():
    all_data = {}
    all_stats = {}

    # 1. 读取数据
    print("=" * 60)
    print("  IMU 振动对比分析工具 (多段支持)")
    print("=" * 60)
    for condition_name, cfg in CONFIGS.items():
        bag_path = cfg["path"]
        start_times = cfg["starts"]
        print(f"\n正在处理: {LABELS_DISPLAY.get(condition_name, condition_name)} ({len(start_times)} 段) ...")
        data = extract_imu_data(bag_path, start_times, DURATION)
        all_data[condition_name] = data
        if data is not None:
            n_total = len(data['time'])
            n_seg = data['n_segments']
            dt = np.mean(np.diff(data['time'][data['time'] < DURATION + 0.1])) if n_total > 1 else 0.01
            print(f"  ✅ 共 {n_seg} 段, {n_total} 条数据 (采样率≈{1.0/dt:.0f}Hz)")
            all_stats[condition_name] = compute_stats(data)

    if not all_stats:
        print("❌ 没有有效数据，退出")
        return

    # 2. 打印统计表
    print_stats_table(all_stats)

    # 3. 生成图表
    print("正在生成图表...")
    plot_time_domain(all_data, os.path.join(OUTPUT_DIR, 'vibration_time_domain.png'))
    plot_fft(all_data, os.path.join(OUTPUT_DIR, 'vibration_fft.png'))
    plot_stats_bar(all_stats, os.path.join(OUTPUT_DIR, 'vibration_stats_bar.png'))

    # 4. 导出 CSV
    save_stats_csv(all_stats, os.path.join(OUTPUT_DIR, 'vibration_stats.csv'))

    print(f"\n✅ 分析完成！所有输出文件位于: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
