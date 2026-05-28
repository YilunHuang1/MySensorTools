import cv2
import numpy as np
import matplotlib.pyplot as plt

def visualize_distortion_ring(cam_name, width, height, fx, fy, cx, cy, k_coeffs, p_coeffs):
    """
    可视化畸变环（有效视场边界）
    """
    # 1. 构建相机内参矩阵 K
    K = np.array([[fx, 0, cx],
                  [0, fy, cy],
                  [0, 0, 1]], dtype=np.float64)

    # 2. 构建畸变系数向量 D
    # OpenCV Rational Model (8参数) 顺序: k1, k2, p1, p2, k3, k4, k5, k6
    # 你的文件顺序: k1, k2, p1, p2, k3, k4, k5, k6 (完全一致)
    k1, k2, k3, k4, k5, k6 = k_coeffs
    p1, p2 = p_coeffs
    dist_coeffs = np.array([k1, k2, p1, p2, k3, k4, k5, k6], dtype=np.float64)

    print(f"--- Processing {cam_name} ---")
    print(f"K:\n{K}")
    print(f"Dist:\n{dist_coeffs}")

    # 3. 创建一张纯白色的图像，代表Sensor的所有像素都是有效的
    src_img = np.full((height, width), 255, dtype=np.uint8)

    # 4. 计算新的相机矩阵
    # alpha=1 表示保留所有原始图像像素，这会导致图像四周出现黑边（这正是我们要看的畸变形状）
    # alpha=0 表示裁剪掉黑边，只保留有效区域
    new_K, roi = cv2.getOptimalNewCameraMatrix(K, dist_coeffs, (width, height), alpha=1, newImgSize=(width, height))
    
    # 5. 计算映射表 (undistort map)
    map1, map2 = cv2.initUndistortRectifyMap(K, dist_coeffs, None, new_K, (width, height), cv2.CV_16SC2)

    # 6. 重映射 (Remap)，得到矫正后的图像
    dst_img = cv2.remap(src_img, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    # 7. 绘制网格线以便更清晰地观察畸变流向（可选）
    # 在原图画网格再矫正，效果会更直观
    grid_img = np.full((height, width, 3), 255, dtype=np.uint8)
    # 画水平线和垂直线
    step = 100
    for y in range(0, height, step):
        cv2.line(grid_img, (0, y), (width, y), (0, 0, 0), 2)
    for x in range(0, width, step):
        cv2.line(grid_img, (x, 0), (x, height), (0, 0, 0), 2)
    
    distorted_grid_view = cv2.remap(grid_img, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    return dst_img, distorted_grid_view

# ================= 配置参数 (来自你的 H150TA-H08220011.txt) =================

# 图像分辨率
W = 1920
H = 1080

# --- CAM0 参数 ---
CAM0_fx = 792.7126564834
CAM0_fy = 793.4440460521
CAM0_cx = 961.3506236272
CAM0_cy = 537.5909910405

# 畸变参数 (注意：p1, p2 是切向畸变，k是径向畸变)
CAM0_k = [0.3504645695, -0.0148283222, -0.0004982023, 0.7163776233, 0.0274484744, -0.0042843837] # k1, k2, k3, k4, k5, k6
CAM0_p = [0.0000017778, 0.0000423982] # p1, p2

# --- CAM1 参数 ---
CAM1_fx = 794.2034951154
CAM1_fy = 794.9710914973
CAM1_cx = 961.7600045114
CAM1_cy = 536.8664538234

CAM1_k = [0.2508015858, -0.0551241988, -0.0014610888, 0.6172811089, -0.0496510314, -0.0114472033]
CAM1_p = [-0.0000185161, 0.0001535738]


# # --- CAM0 参数 (左相机L) ---
# CAM0_fx = 802.47080843
# CAM0_fy = 802.59297056
# CAM0_cx = 950.15893498
# CAM0_cy = 525.80168387

# # 畸变参数 (注意：p1, p2 是切向畸变，k是径向畸变)
# CAM0_k = [0.97171448, 0.13484287, -0.00044831, 1.35036323, 0.38916477, 0.01047079] # k1, k2, k3, k4, k5, k6
# CAM0_p = [0.00012320, 0.00004062] # p1, p2

# # --- CAM1 参数 (右相机R) ---
# CAM1_fx = 797.73450917
# CAM1_fy = 797.63702216
# CAM1_cx = 968.73714300
# CAM1_cy = 531.17948965

# CAM1_k = [0.77476825, 0.09613920, 0.00084810, 1.15047172, 0.28145796, 0.01047079]
# CAM1_p = [0.00003301, -0.00000390]

# ================= 执行可视化 =================

# 生成 CAM0
mask0, grid0 = visualize_distortion_ring("CAM0", W, H, CAM0_fx, CAM0_fy, CAM0_cx, CAM0_cy, CAM0_k, CAM0_p)
# 生成 CAM1
mask1, grid1 = visualize_distortion_ring("CAM1", W, H, CAM1_fx, CAM1_fy, CAM1_cx, CAM1_cy, CAM1_k, CAM1_p)

# 显示结果
plt.figure(figsize=(12, 8))

plt.subplot(2, 2, 1)
plt.title("CAM0 Distortion Shape (Mask)")
plt.imshow(mask0, cmap='gray')
plt.axis('off')

plt.subplot(2, 2, 2)
plt.title("CAM0 Undistorted Grid")
plt.imshow(grid0)
plt.axis('off')

plt.subplot(2, 2, 3)
plt.title("CAM1 Distortion Shape (Mask)")
plt.imshow(mask1, cmap='gray')
plt.axis('off')

plt.subplot(2, 2, 4)
plt.title("CAM1 Undistorted Grid")
plt.imshow(grid1)
plt.axis('off')

plt.tight_layout()
plt.show()

# 如果需要保存图片给厂商看
cv2.imwrite('CAM0_Distortion_Ring.png', mask0)
cv2.imwrite('CAM0_Grid_Check.png', grid0)
print("图片已保存至当前目录。")