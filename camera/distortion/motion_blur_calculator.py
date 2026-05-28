import math

def calculate_pixel_density(resolution_h, hfov_degrees):
    """
    计算水平方向上每度视角包含多少像素。
    
    参数:
    resolution_h (int): 相机的水平分辨率 (例如 1920)
    hfov_degrees (float): 相机的水平视场角 (单位: 度)
    
    返回:
    float: 像素/度
    """
    if hfov_degrees <= 0:
        raise ValueError("水平视场角 (HFOV) 必须大于0")
    return resolution_h / hfov_degrees

def calculate_motion_blur(
    resolution_h,
    hfov_degrees,
    object_distance_m,
    relative_speed_mps,
    exposure_time_s,
    is_rotational=False,
    angular_velocity_dps=0
):
    """
    计算在给定条件下产生的运动模糊像素数。
    
    参数:
    resolution_h (int): 相机水平分辨率。
    hfov_degrees (float): 相机水平视场角（度）。
    object_distance_m (float): 物体到相机的垂直距离（米）。仅在线性运动时使用。
    relative_speed_mps (float): 物体相对于相机的横向速度（米/秒）。仅在线性运动时使用。
    exposure_time_s (float): 曝光时间（秒）。
    is_rotational (bool): 是否为旋转运动。如果是，则使用 angular_velocity_dps。
    angular_velocity_dps (float): 相机的角速度（度/秒）。仅在旋转运动时使用。
    
    返回:
    float: 产生的模糊像素数。
    """
    pixel_density = calculate_pixel_density(resolution_h, hfov_degrees)
    
    if is_rotational:
        # 旋转运动
        if angular_velocity_dps <= 0:
            raise ValueError("旋转运动时，角速度必须大于0")
        angular_velocity = angular_velocity_dps
    else:
        # 线性运动
        if object_distance_m <= 0:
            raise ValueError("线性运动时，物体距离必须大于0")
        # 计算角速度 (rad/s) = v / r
        angular_velocity_rad_per_sec = relative_speed_mps / object_distance_m
        # 转换为度/秒
        angular_velocity = math.degrees(angular_velocity_rad_per_sec)

    # 图像上的移动速度 (像素/秒)
    image_speed_pps = angular_velocity * pixel_density
    
    # 计算模糊像素数
    blur_pixels = image_speed_pps * exposure_time_s
    
    return blur_pixels

def calculate_max_exposure_time(
    resolution_h,
    hfov_degrees,
    object_distance_m,
    relative_speed_mps,
    max_blur_pixels,
    is_rotational=False,
    angular_velocity_dps=0
):
    """
    根据最大可容忍的模糊像素数，反推最大曝光时间。
    
    参数:
    resolution_h (int): 相机水平分辨率。
    hfov_degrees (float): 相机水平视场角（度）。
    object_distance_m (float): 物体到相机的垂直距离（米）。仅在线性运动时使用。
    relative_speed_mps (float): 物体相对于相机的横向速度（米/秒）。仅在线性运动时使用。
    max_blur_pixels (float): 算法能容忍的最大模糊像素数。
    is_rotational (bool): 是否为旋转运动。如果是，则使用 angular_velocity_dps。
    angular_velocity_dps (float): 相机的角速度（度/秒）。仅在旋转运动时使用。

    返回:
    float: 最大允许的曝光时间（秒）。
    """
    pixel_density = calculate_pixel_density(resolution_h, hfov_degrees)

    if is_rotational:
        # 旋转运动
        if angular_velocity_dps <= 0:
            raise ValueError("旋转运动时，角速度必须大于0")
        angular_velocity = angular_velocity_dps
    else:
        # 线性运动
        if object_distance_m <= 0:
            raise ValueError("线性运动时，物体距离必须大于0")
        # 计算角速度 (rad/s) = v / r
        angular_velocity_rad_per_sec = relative_speed_mps / object_distance_m
        # 转换为度/秒
        angular_velocity = math.degrees(angular_velocity_rad_per_sec)
        
    # 图像上的移动速度 (像素/秒)
    image_speed_pps = angular_velocity * pixel_density
    
    if image_speed_pps == 0:
        return float('inf') # 如果没有移动，曝光时间可以是无限长

    # 计算最大曝光时间
    max_exposure_time = max_blur_pixels / image_speed_pps
    
    return max_exposure_time


if __name__ == "__main__":
    # --- 1. 定义相机和场景参数 ---
    # 相机参数 (根据您的补充信息)
    RESOLUTION_H = 1920  # 水平分辨率 (像素)
    HFOV = 96.8         # 水平视场角 (度)

    print("--- 场景参数 ---")
    print(f"相机水平分辨率: {RESOLUTION_H} px")
    print(f"相机水平视场角: {HFOV}°\n")
    
    # --- 2. 计算示例 ---

    # === 示例 A: 计算最大允许曝光时间 (给供应商提需求) ===
    print("="*10 + " 示例 A: 计算最大允许曝光时间 " + "="*10)
    
    # 场景: 机器狗转头 (旋转运动)
    print("\n[场景 A1: 机器狗转头]")
    rotational_speed_dps = 229.18  # 假设转身速度为 20 度/秒，最大是4π/s
    tolerable_blur_pixels_rot = 10  # 算法能容忍10个像素的模糊
    
    max_exp_time_rot = calculate_max_exposure_time(
        resolution_h=RESOLUTION_H,
        hfov_degrees=HFOV,
        object_distance_m=0, # 旋转运动不需要距离
        relative_speed_mps=0, # 旋转运动不需要线性速度
        max_blur_pixels=tolerable_blur_pixels_rot,
        is_rotational=True,
        angular_velocity_dps=rotational_speed_dps
    )
    print(f"最大转身速度: {rotational_speed_dps}°/s")
    print(f"可容忍的模糊: {tolerable_blur_pixels_rot} 像素")
    print(f"  -> 最大允许曝光时间: {max_exp_time_rot * 1000:.2f} ms (或 1/{1/max_exp_time_rot:.0f} 秒)")

    # 场景: 机器狗直线前进，观察侧方物体 (线性运动)
    print("\n[场景 A2: 机器狗直线前进，观察近处物体2m]")
    linear_speed_mps = 1.0  # 狗子速度 1 m/s
    object_dist_m = 2.0     # 物体距离 2 米
    tolerable_blur_pixels_lin = 10 # 算法能容忍5个像素的模糊
    
    max_exp_time_lin = calculate_max_exposure_time(
        resolution_h=RESOLUTION_H,
        hfov_degrees=HFOV,
        object_distance_m=object_dist_m,
        relative_speed_mps=linear_speed_mps,
        max_blur_pixels=tolerable_blur_pixels_lin
    )
    print(f"机器人速度: {linear_speed_mps} m/s")
    print(f"物体距离: {object_dist_m} m")
    print(f"可容忍的模糊: {tolerable_blur_pixels_lin} 像素")
    print(f"  -> 最大允许曝光时间: {max_exp_time_lin * 1000:.2f} ms (或 1/{1/max_exp_time_lin:.0f} 秒)")
    
    print("\n" + "="*40 + "\n")

    # === 示例 B: 已知曝光时间，计算会产生多少模糊 (分析当前问题) ===
    print("="*10 + " 示例 B: 计算产生的模糊像素数 " + "="*10)
    
    # 场景: 机器狗转头，使用当前ISP配置的最大曝光时间
    print("\n[场景 B1: 机器狗转头，使用当前ISP配置]")
    current_max_exposure_s = 0.030 # 当前配置的最大曝光时间 30ms
    
    blur_pixels_result_rot = calculate_motion_blur(
        resolution_h=RESOLUTION_H,
        hfov_degrees=HFOV,
        object_distance_m=0,
        relative_speed_mps=0,
        exposure_time_s=current_max_exposure_s,
        is_rotational=True,
        angular_velocity_dps=rotational_speed_dps
    )
    print(f"最大转身速度: {rotational_speed_dps}°/s")
    print(f"当前最大曝光时间: {current_max_exposure_s * 1000:.1f} ms")
    print(f"  -> 产生的运动模糊: {blur_pixels_result_rot:.1f} 像素")

    # 场景: 机器狗直线前进，观察不同距离的物体，使用当前ISP配置
    print("\n[场景 B2: 机器狗直线前进，观察不同距离的物体]")
    distances_to_test = [1.0, 3.0, 5.0]
    print(f"机器人速度: {linear_speed_mps} m/s")
    print(f"当前最大曝光时间: {current_max_exposure_s * 1000:.1f} ms")
    for dist in distances_to_test:
        blur_pixels_result_lin = calculate_motion_blur(
            resolution_h=RESOLUTION_H,
            hfov_degrees=HFOV,
            object_distance_m=dist,
            relative_speed_mps=linear_speed_mps,
            exposure_time_s=current_max_exposure_s
        )
        print(f"  - 物体距离 {dist:.1f} m 时，产生的运动模糊: {blur_pixels_result_lin:.1f} 像素")









        