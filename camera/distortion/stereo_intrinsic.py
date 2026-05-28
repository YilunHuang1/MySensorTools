import numpy as np
import os
import glob
import yaml
import cv2
import csv
import argparse
import matplotlib.pyplot as plt
import matplotlib
from datetime import datetime

# 设置matplotlib为非交互模式
matplotlib.use('Agg')  # 这行必须在导入pyplot之后

def load_calibration_yaml(calib_path):
    """处理OpenCV风格的YAML文件（带%YAML标头）"""
    with open(calib_path, 'r') as f:
        # 跳过YAML版本声明行
        if f.readline().startswith('%YAML'):
            return yaml.safe_load(f)
        else:
            f.seek(0)
            return yaml.safe_load(f)

def check_distortion_curve(x, y):
    """
    检查畸变曲线异常
    参数:
        x: 横轴数组 (到主点的像素距离)
        y: 纵轴数组 (去畸变后的归一化距离)
    返回:
        dict {
            'is_valid': bool,       # 整体是否有效
            'is_monotonic': bool,   # 是否单调递增
            'has_missing': bool,    # 是否有数据缺失
            'has_spike': bool       # 是否有尖峰
        }
    """
    # 初始化标志位
    flags = {
        'is_monotonic': True,
        'has_missing': False,
        'has_spike': False
    }
    
    # ------------------------
    # 1. 基础数据检查
    # ------------------------
    n = len(x)
    if n != len(y) or n < 3:
        flags['has_missing'] = True
        flags['is_valid'] = False
        return flags
    
    # 检查NaN值
    if np.isnan(x).any() or np.isnan(y).any():
        flags['has_missing'] = True
    
    # ------------------------
    # 2. 单调性和连续性检查
    # ------------------------
    for i in range(1, n):
        # 检查x递增
        if x[i] <= x[i-1]:
            flags['has_missing'] = True
        
        # 检查y递增
        if y[i] <= y[i-1]:
            flags['is_monotonic'] = False
    
    # ------------------------
    # 3. 尖峰检测（需n≥3）
    # ------------------------
    if n >= 3:
        dy = np.diff(y)       # 一阶差分
        d2y = np.abs(np.diff(dy))  # 二阶差分
        
        # 计算动态阈值
        mean_dy = np.mean(dy)
        std_dy = np.std(dy)
        threshold = mean_dy + 3 * std_dy
        
        # 检测超出阈值的尖峰
        if np.any(d2y > threshold):
            flags['has_spike'] = True
    
    # ------------------------
    # 综合有效性判断
    # ------------------------
    flags['is_valid'] = all([
        flags['is_monotonic'],
        not flags['has_missing'],
        not flags['has_spike']
    ])
    
    return flags

def analyze_distortion_curve(K_l, dist_l, K_r, dist_r, img_size, output_path, file_name):
    """
    绘制左右相机畸变曲线并保存图像
    """
    # 配置样式
    plt.figure(figsize=(10, 6))
    plt.title(f"Distortion Curves Comparison ({file_name})", fontsize=14)
    plt.xlabel("Distance from Principal Point (pixels)")
    plt.ylabel("Normalized Distortion Radius")
    plt.grid(True, alpha=0.3)
    
    # 绘制左相机曲线
    _, curve_left = compute_distortion_curve(K_l, dist_l, img_size)
    result_left = check_distortion_curve(curve_left[0], curve_left[1])
    plt.plot(curve_left[0], curve_left[1], 'b-', linewidth=2, label='Left Camera')
    
    # 绘制右相机曲线
    _, curve_right = compute_distortion_curve(K_r, dist_r, img_size)
    result_right = check_distortion_curve(curve_right[0], curve_right[1])
    plt.plot(curve_right[0], curve_right[1], 'r-', linewidth=2, label='Right Camera')
    
    # 添加参考线
    plt.axhline(1.0, color='gray', linestyle='--', alpha=0.7)
    
    # 添加图例
    plt.legend(loc='best')
    
    # 保存结果到指定路径
    plt.tight_layout()
    output_file = os.path.join(output_path, f"distortion_curve_{file_name}.png")
    plt.savefig(output_file, dpi=150)
    plt.close()  # 关闭图形以释放内存
    
    # 返回畸变检查结果
    return output_file, result_left, result_right

def compute_distortion_curve(K, dist, img_size):
    """计算畸变曲线"""
    # 提取主点坐标
    cx, cy = K[0, 2], K[1, 2]
    
    # 计算最大距离
    corners = np.array([
        [0, 0], [img_size[0]-1, 0], 
        [0, img_size[1]-1], [img_size[0]-1, img_size[1]-1]
    ])
    distances = np.sqrt((corners[:, 0] - cx)**2 + (corners[:, 1] - cy)**2)
    max_distance = np.max(distances)
    
    # 沿0度方向采样
    dist_samples = np.linspace(1, max_distance, 200)  # 使用200个采样点
    points = np.zeros((len(dist_samples), 2))
    points[:, 0] = cx + dist_samples
    points[:, 1] = cy
    
    # 畸变矫正
    undist_points = cv2.undistortPoints(
        points.reshape(1, -1, 2), K, np.array(dist).flatten(), None, K
    ).reshape(-1, 2)
    
    # 计算归一化半径
    norm_x = (undist_points[:, 0] - cx) / K[0, 0]
    norm_y = (undist_points[:, 1] - cy) / K[1, 1]
    norm_r = np.sqrt(norm_x**2 + norm_y**2)
    
    return max_distance, (dist_samples, norm_r)

def analyze_stereo_calibration(yaml_dir):
    yaml_files = glob.glob(os.path.join(yaml_dir, "*.yaml"))
    if not yaml_files:
        print("未找到YAML文件！")
        return
    
    # 创建输出目录
    output_dir = os.path.join(yaml_dir, f"distortion_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化数据结构
    results = []  # 存储所有结果
    csv_header = [
        '文件名', '左目fx', '左目fy', '左目cx', '左目cy', '左目主点偏差(px)', 
        '右目fx', '右目fy', '右目cx', '右目cy', '右目主点偏差(px)',
        '理论cx', '理论cy', '畸变曲线文件', '左畸变异常', '右畸变异常'
    ]
    
    # 临时存储用于计算统计的数据
    left_deviations = []  # 左目主点偏差
    right_deviations = []  # 右目主点偏差
    left_fx_list, left_fy_list, left_cx_list, left_cy_list = [], [], [], []
    right_fx_list, right_fy_list, right_cx_list, right_cy_list = [], [], [], []
    
    # 存储焦距偏差数据
    left_focal_diff = []  # 左目|fx - fy|
    right_focal_diff = []  # 右目|fx - fy|
    
    # 存储畸变异常文件
    left_dist_abnormal_files = []
    right_dist_abnormal_files = []
    
    # 遍历所有YAML文件
    for yaml_file in yaml_files:
        try:
            file_name = os.path.splitext(os.path.basename(yaml_file))[0]
            calib = load_calibration_yaml(yaml_file)

            # 获取图像尺寸
            img_w = calib.get('image_width', 1920)
            img_h = calib.get('image_height', 1080)
            theory_cx = img_w / 2.0
            theory_cy = img_h / 2.0
            
            # 解析左相机参数
            K_l = np.array(calib['left_camera_matrix']['data']).reshape(3,3)
            dist_l = np.array(calib['left_distortion_coefficients']['data']).reshape(1,8)
            fx_l, fy_l, cx_l, cy_l = K_l[0,0], K_l[1,1], K_l[0,2], K_l[1,2]
            left_dev = np.sqrt((cx_l - theory_cx)**2 + (cy_l - theory_cy)**2)
            
            # 解析右相机参数
            K_r = np.array(calib['right_camera_matrix']['data']).reshape(3,3)
            dist_r = np.array(calib['right_distortion_coefficients']['data']).reshape(1,8)
            fx_r, fy_r, cx_r, cy_r = K_r[0,0], K_r[1,1], K_r[0,2], K_r[1,2]
            right_dev = np.sqrt((cx_r - theory_cx)**2 + (cy_r - theory_cy)**2)
            
            # 生成畸变曲线图并获取路径
            curve_path, result_left, result_right = analyze_distortion_curve(
                K_l, dist_l, K_r, dist_r, 
                [img_w, img_h], output_dir, file_name
            )
            curve_rel_path = os.path.relpath(curve_path, yaml_dir)
            
            # 记录畸变异常
            left_dist_abnormal = not result_left['is_valid']
            right_dist_abnormal = not result_right['is_valid']
            
            # 添加到异常文件列表
            if left_dist_abnormal:
                left_dist_abnormal_files.append(file_name)
            if right_dist_abnormal:
                right_dist_abnormal_files.append(file_name)
            
            # 存储用于统计的数据
            left_fx_list.append(fx_l)
            left_fy_list.append(fy_l)
            left_cx_list.append(cx_l)
            left_cy_list.append(cy_l)
            left_deviations.append(left_dev)
            
            right_fx_list.append(fx_r)
            right_fy_list.append(fy_r)
            right_cx_list.append(cx_r)
            right_cy_list.append(cy_r)
            right_deviations.append(right_dev)
            
            # 存储焦距偏差数据
            left_focal_diff.append(abs(fx_l - fy_l))
            right_focal_diff.append(abs(fx_r - fy_r))
            
            # 添加到结果列表
            results.append([
                os.path.basename(yaml_file),
                f"{fx_l:.6f}", f"{fy_l:.6f}", f"{cx_l:.2f}", f"{cy_l:.2f}", f"{left_dev:.2f}",
                f"{fx_r:.6f}", f"{fy_r:.6f}", f"{cx_r:.2f}", f"{cy_r:.2f}", f"{right_dev:.2f}",
                f"{theory_cx:.2f}", f"{theory_cy:.2f}",
                curve_rel_path,
                str(left_dist_abnormal),  # 转为字符串便于CSV处理
                str(right_dist_abnormal)  # 转为字符串便于CSV处理
            ])
            
        except Exception as e:
            print(f"处理文件 {yaml_file} 时出错: {str(e)}")
            results.append([
                os.path.basename(yaml_file),
                "Error", "Error", "Error", "Error", "Error",
                "Error", "Error", "Error", "Error", "Error",
                "Error", "Error", "Error", "Error", "Error"
            ])
    
    # 计算统计结果
    def calculate_stats(values):
        if values:
            mean = np.mean(values)
            std = np.std(values)
            max_val = np.max(values)
            min_val = np.min(values)
            return mean, std, max_val, min_val
        return 0, 0, 0, 0
    
    # 左目统计
    left_dev_mean, left_dev_std, left_dev_max, left_dev_min = calculate_stats(left_deviations)
    left_fx_mean, left_fx_std, _, _ = calculate_stats(left_fx_list)
    left_fy_mean, left_fy_std, _, _ = calculate_stats(left_fy_list)
    left_cx_mean, left_cx_std, _, _ = calculate_stats(left_cx_list)
    left_cy_mean, left_cy_std, _, _ = calculate_stats(left_cy_list)
    
    # 右目统计
    right_dev_mean, right_dev_std, right_dev_max, right_dev_min = calculate_stats(right_deviations)
    right_fx_mean, right_fx_std, _, _ = calculate_stats(right_fx_list)
    right_fy_mean, right_fy_std, _, _ = calculate_stats(right_fy_list)
    right_cx_mean, right_cx_std, _, _ = calculate_stats(right_cx_list)
    right_cy_mean, right_cy_std, _, _ = calculate_stats(right_cy_list)
    
    # 找到主点偏差最大的文件索引
    left_worst_idx = np.argmax(left_deviations) if left_deviations else None
    right_worst_idx = np.argmax(right_deviations) if right_deviations else None
    
    # 找到焦距偏差最大的文件索引
    left_focal_worst_idx = np.argmax(left_focal_diff) if left_focal_diff else None
    right_focal_worst_idx = np.argmax(right_focal_diff) if right_focal_diff else None
    
    # 准备CSV文件内容
    csv_rows = [csv_header] + results
    
    # 创建统计行
    stats_rows = [
        [],
        ["统计结果"],
        ["", "左目", "右目"],
        ["主点偏差均值(px)", f"{left_dev_mean:.4f}", f"{right_dev_mean:.4f}"],
        ["主点偏差标准差(px)", f"{left_dev_std:.4f}", f"{right_dev_std:.4f}"],
        ["最大主点偏差(px)", f"{left_dev_max:.4f}", f"{right_dev_max:.4f}"],
        ["最小主点偏差(px)", f"{left_dev_min:.4f}", f"{right_dev_min:.4f}"],
        [],
        ["内参统计"],
        ["", "左目", "右目"],
        ["fx均值", f"{left_fx_mean:.6f}", f"{right_fx_mean:.6f}"],
        ["fx标准差", f"{left_fx_std:.6f}", f"{right_fx_std:.6f}"],
        ["fy均值", f"{left_fy_mean:.6f}", f"{right_fy_mean:.6f}"],
        ["fy标准差", f"{left_fy_std:.6f}", f"{right_fy_std:.6f}"],
        ["cx均值", f"{left_cx_mean:.6f}", f"{right_cx_mean:.6f}"],
        ["cx标准差", f"{left_cx_std:.6f}", f"{right_cx_std:.6f}"],
        ["cy均值", f"{left_cy_mean:.6f}", f"{right_cy_mean:.6f}"],
        ["cy标准差", f"{left_cy_std:.6f}", f"{right_cy_std:.6f}"],
        [],
    ]
    
    # 添加最差文件信息
    if left_worst_idx is not None:
        left_worst_file = results[left_worst_idx][0]
        left_worst_dev = results[left_worst_idx][5]
        stats_rows.append([f"左目主点偏差最大文件: {left_worst_file}", f"偏差值: {left_worst_dev}px"])
    
    if right_worst_idx is not None:
        right_worst_file = results[right_worst_idx][0]
        right_worst_dev = results[right_worst_idx][10]
        stats_rows.append([f"右目主点偏差最大文件: {right_worst_file}", f"偏差值: {right_worst_dev}px"])
    
    # 添加焦距偏差最大的文件
    if left_focal_worst_idx is not None:
        left_focal_file = results[left_focal_worst_idx][0]
        left_focal_value = left_focal_diff[left_focal_worst_idx]
        stats_rows.append([f"左目焦距偏差最大文件: {left_focal_file}", f"|fx-fy|: {left_focal_value:.6f}"])
    
    if right_focal_worst_idx is not None:
        right_focal_file = results[right_focal_worst_idx][0]
        right_focal_value = right_focal_diff[right_focal_worst_idx]
        stats_rows.append([f"右目焦距偏差最大文件: {right_focal_file}", f"|fx-fy|: {right_focal_value:.6f}"])
    
    # 添加畸变异常文件（合并为一行）
    stats_rows.append([])
    
    if left_dist_abnormal_files:
        left_abnormal_str = ", ".join(left_dist_abnormal_files)
        stats_rows.append([f"左目畸变异常: {left_abnormal_str}"])
    else:
        stats_rows.append(["左目畸变正常"])
    
    if right_dist_abnormal_files:
        right_abnormal_str = ", ".join(right_dist_abnormal_files)
        stats_rows.append([f"右目畸变异常: {right_abnormal_str}"])
    else:
        stats_rows.append(["右目畸变正常"])

    # 合并所有行
    full_csv = csv_rows + stats_rows
    
    # 写入CSV文件
    csv_filename = os.path.join(output_dir, "calibration_analysis.csv")
    with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(full_csv)
    
    return {
        'csv_file': csv_filename,
        'output_dir': output_dir,
        'left_worst_file': results[left_worst_idx][0] if left_worst_idx is not None else None,
        'right_worst_file': results[right_worst_idx][0] if right_worst_idx is not None else None,
        'left_focal_worst_file': results[left_focal_worst_idx][0] if left_focal_worst_idx is not None else None,
        'right_focal_worst_file': results[right_focal_worst_idx][0] if right_focal_worst_idx is not None else None,
        'left_focal_max_dev': left_focal_diff[left_focal_worst_idx] if left_focal_worst_idx is not None else 0,
        'right_focal_max_dev': right_focal_diff[right_focal_worst_idx] if right_focal_worst_idx is not None else 0,
        'num_files': len(results),
        'left_dist_abnormal': left_dist_abnormal_files,
        'right_dist_abnormal': right_dist_abnormal_files
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='相机内参校验程序')
    parser.add_argument('--input', required=True, help='输入内参文件路径')
    
    args = parser.parse_args()

    result = analyze_stereo_calibration(args.input)
    
    if result:
        print(f"分析完成！处理了 {result['num_files']} 个文件")
        print(f"CSV报告保存至: {result['csv_file']}")
        print(f"所有畸变曲线保存至: {result['output_dir']}")
        
        if result['left_worst_file']:
            print(f"左目主点偏差最严重的文件: {result['left_worst_file']}")
        if result['right_worst_file']:
            print(f"右目主点偏差最严重的文件: {result['right_worst_file']}")
        
        if result['left_focal_worst_file']:
            print(f"左目焦距偏差最大文件: {result['left_focal_worst_file']} (|fx-fy| = {result['left_focal_max_dev']:.6f})")
        if result['right_focal_worst_file']:
            print(f"右目焦距偏差最大文件: {result['right_focal_worst_file']} (|fx-fy| = {result['right_focal_max_dev']:.6f})")
        
        if result['left_dist_abnormal']:
            print(f"左目畸变异常文件: {', '.join(result['left_dist_abnormal'])}")
        
        if result['right_dist_abnormal']:
            print(f"右目畸变异常文件: {', '.join(result['right_dist_abnormal'])}")