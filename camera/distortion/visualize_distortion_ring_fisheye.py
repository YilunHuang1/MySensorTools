import cv2
import numpy as np
import os
import re
import argparse
from pathlib import Path
from sensor_tools.images import save_image
from sensor_tools.calibration import cameras, load

def parse_calibration_file(file_path):
    if Path(file_path).suffix.lower() in ('.yaml', '.yml'):
        parsed = cameras(load(file_path))
        result = {'common': {}, 'cams': {}}
        for label, camera in parsed.items():
            if camera['model'] != 'equidistant':
                raise ValueError(f"{label}: expected {'equidistant'}, got {camera['model']}")
            K, D = camera['K'], camera['D']
            names = ['k1', 'k2', 'k3', 'k4']
            values = dict(zip(names, D))
            values.update(fx=K[0,0], fy=K[1,1], cx=K[0,2], cy=K[1,2], imageWidth=camera['width'], imageHeight=camera['height'])
            result['cams'][label] = values
        return result
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到文件: {file_path}")

    params = {'common': {}, 'cams': {}}
    num_pattern = re.compile(r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)')

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, val_str = line.split('=', 1)
            key = key.strip()
            val_str = val_str.strip()
            match = num_pattern.search(val_str)
            if not match:
                continue
            value = float(match.group(1))
            if key.startswith('CAM'):
                cam_name = key.split('_')[0]
                param_name = key.split('_')[1]
                if cam_name not in params['cams']:
                    params['cams'][cam_name] = {}
                params['cams'][cam_name][param_name] = value
            else:
                params['common'][key] = value

    return params

def visualize_distortion_fisheye(cam_name, cam_params, common_params, output_dir="."):
    W = int(cam_params.get('imageWidth', common_params.get('imageWidth', 0)))
    H = int(cam_params.get('imageHeight', common_params.get('imageHeight', 0)))
    if W <= 0 or H <= 0:
        raise ValueError('calibration must contain explicit image dimensions')

    try:
        fx = cam_params['fx']
        fy = cam_params['fy']
        cx = cam_params['cx']
        cy = cam_params['cy']
        K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
    except KeyError as e:
        raise ValueError(f"{cam_name}: missing intrinsic {e}") from e

    k1 = cam_params.get('k1', 0.0)
    k2 = cam_params.get('k2', 0.0)
    k3 = cam_params.get('k3', 0.0)
    k4 = cam_params.get('k4', 0.0)
    D = np.array([k1, k2, k3, k4], dtype=np.float64).reshape(1, 4)

    print(f"正在处理: {cam_name}")
    print(f"  - K Matrix: fx={fx:.2f}, fy={fy:.2f}, cx={cx:.2f}, cy={cy:.2f}")
    print(f"  - Fisheye Distortion: {D.flatten()}")

    src_img = np.full((H, W), 255, dtype=np.uint8)

    R = np.eye(3, dtype=np.float64)
    Knew = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D, (W, H), R, balance=1.0, new_size=(W, H))
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(K, D, R, Knew, (W, H), cv2.CV_16SC2)
    dst_img = cv2.remap(src_img, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    save_path = os.path.join(output_dir, f"{cam_name}_Fisheye_Distortion_Ring.png")
    save_image(save_path, dst_img)
    print(f"  -> 结果已保存: {save_path}\n")

def main():
    parser = argparse.ArgumentParser(description="Visualize fisheye camera distortion rings")
    parser.add_argument("input_file", help="Calibration text file")
    parser.add_argument("-o", "--output-dir", default=".", help="Output directory")
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        parser.exit(1, f"File not found: {args.input_file}\n")
    os.makedirs(args.output_dir, exist_ok=True)

    try:
        data = parse_calibration_file(args.input_file)
        if not data['cams']:
            raise ValueError("no camera parameters found")
        for cam_name, cam_params in data['cams'].items():
            visualize_distortion_fisheye(cam_name, cam_params, data['common'], args.output_dir)
        print("所有处理完成。")
    except Exception as e:
        parser.exit(1, f"error: {e}\n")

if __name__ == "__main__":
    main()
