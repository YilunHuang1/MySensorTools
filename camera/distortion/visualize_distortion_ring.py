import cv2
import numpy as np
import os
import re
import argparse

def parse_calibration_file(file_path):
    """
    解析标定文件，返回由相机名称索引的参数字典。
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到文件: {file_path}")

    params = {
        'common': {},
        'cams': {}
    }

    # 用于匹配数值的正则表达式 (匹配浮点数或整数)
    num_pattern = re.compile(r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)')

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or '=' not in line:
                continue
            
            # 分割键值对
            key, val_str = line.split('=', 1)
            key = key.strip()
            val_str = val_str.strip()

            # 提取第一个数值
            match = num_pattern.search(val_str)
            if match:
                value = float(match.group(1))
            else:
                continue

            # 分类存储
            if key.startswith('CAM'):
                # 提取相机ID (如 CAM0, CAM1)
                cam_name = key.split('_')[0]
                param_name = key.split('_')[1]
                
                if cam_name not in params['cams']:
                    params['cams'][cam_name] = {}
                
                params['cams'][cam_name][param_name] = value
            else:
                # 公共参数，如 imageWidth
                params['common'][key] = value

    return params

def visualize_distortion(cam_name, cam_params, common_params, output_dir="."):
    """
    根据解析的参数生成畸变可视化图
    """
    # 1. 获取基础分辨率
    try:
        W = int(common_params.get('imageWidth', 1920))
        H = int(common_params.get('imageHeight', 1080))
    except:
        print("警告：未找到分辨率，默认使用 1920x1080")
        W, H = 1920, 1080

    # 2. 构建内参矩阵 K
    try:
        fx = cam_params['fx']
        fy = cam_params['fy']
        cx = cam_params['cx']
        cy = cam_params['cy']
        K = np.array([[fx, 0, cx],
                      [0, fy, cy],
                      [0, 0, 1]], dtype=np.float64)
    except KeyError as e:
        print(f"错误：{cam_name} 缺少必要内参 {e}")
        return

    # 3. 构建畸变系数向量 D (OpenCV 8参数 Rational Model)
    # 顺序: k1, k2, p1, p2, k3, k4, k5, k6
    try:
        k1 = cam_params.get('k1', 0)
        k2 = cam_params.get('k2', 0)
        p1 = cam_params.get('p1', 0)
        p2 = cam_params.get('p2', 0)
        k3 = cam_params.get('k3', 0)
        k4 = cam_params.get('k4', 0)
        k5 = cam_params.get('k5', 0)
        k6 = cam_params.get('k6', 0)
        
        dist_coeffs = np.array([k1, k2, p1, p2, k3, k4, k5, k6], dtype=np.float64)
    except Exception as e:
        print(f"构建畸变系数失败: {e}")
        return

    print(f"正在处理: {cam_name}")
    print(f"  - K Matrix: fx={fx:.2f}, fy={fy:.2f}, cx={cx:.2f}, cy={cy:.2f}")
    print(f"  - Distortion: {dist_coeffs}")

    # 4. 生成白底图像
    src_img = np.full((H, W), 255, dtype=np.uint8)

    # 5. 计算最佳新内参 (alpha=1 保留所有像素，看到黑边)
    new_K, roi = cv2.getOptimalNewCameraMatrix(K, dist_coeffs, (W, H), alpha=1, newImgSize=(W, H))

    # 6. 计算映射表并重映射
    map1, map2 = cv2.initUndistortRectifyMap(K, dist_coeffs, None, new_K, (W, H), cv2.CV_16SC2)
    dst_img = cv2.remap(src_img, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    # 7. 保存结果
    save_path = os.path.join(output_dir, f"{cam_name}_Distortion_Ring.png")
    cv2.imwrite(save_path, dst_img)
    print(f"  -> 结果已保存: {save_path}\n")

def main():
    parser = argparse.ArgumentParser(description="Visualize pinhole camera distortion rings")
    parser.add_argument("input_file", help="Calibration text file")
    parser.add_argument("-o", "--output-dir", default=".", help="Output directory")
    args = parser.parse_args()

    # 简单的文件存在性检查
    if not os.path.exists(args.input_file):
        print(f"Error: 找不到文件 '{args.input_file}'")
        return
    os.makedirs(args.output_dir, exist_ok=True)

    try:
        # 1. 解析参数
        data = parse_calibration_file(args.input_file)
        
        # 2. 遍历所有找到的相机进行可视化
        if not data['cams']:
            print("未在文件中找到以 'CAM' 开头的相机参数。")
            return

        for cam_name, cam_params in data['cams'].items():
            visualize_distortion(cam_name, cam_params, data['common'], args.output_dir)

        print("所有处理完成。")

    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
