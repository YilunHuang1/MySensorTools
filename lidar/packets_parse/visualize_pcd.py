#!/usr/bin/env python3
"""可视化 PCD 点云帧 - 支持 Open3D 或 Matplotlib 后端"""
import sys
import os
import glob
import argparse
import numpy as np


def visualize_with_open3d(pcd_path, frame_idx, points):
    """使用 Open3D 可视化（推荐）"""
    try:
        import open3d as o3d
    except ImportError:
        return False

    print(f"使用 Open3D 后端...")
    pcd = o3d.io.read_point_cloud(pcd_path)

    # 按高度着色
    z_min, z_max = points[:, 2].min(), points[:, 2].max()
    if z_max > z_min:
        z_norm = (points[:, 2] - z_min) / (z_max - z_min)
    else:
        z_norm = np.zeros(len(points))

    colors = np.zeros((len(points), 3))
    colors[:, 0] = z_norm  # R
    colors[:, 1] = 1.0 - z_norm  # G
    colors[:, 2] = 0.5  # B
    pcd.colors = o3d.utility.Vector3dVector(colors)

    print("按 Q 退出可视化窗口")
    o3d.visualization.draw_geometries(
        [pcd],
        window_name=f"Vanjee 722Z - Frame {frame_idx} ({len(points)} pts)",
        width=1280,
        height=720,
        point_show_normal=False,
    )
    return True


def visualize_with_matplotlib(pcd_path, frame_idx, points):
    """使用 Matplotlib 可视化（备用）"""
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
    except ImportError:
        return False

    print(f"使用 Matplotlib 后端...")

    # 按高度着色
    z_min, z_max = points[:, 2].min(), points[:, 2].max()
    if z_max > z_min:
        z_norm = (points[:, 2] - z_min) / (z_max - z_min)
    else:
        z_norm = np.zeros(len(points))

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")

    scatter = ax.scatter(
        points[:, 0],
        points[:, 1],
        points[:, 2],
        c=z_norm,
        cmap="coolwarm",
        s=1,
        alpha=0.6,
    )
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title(f"Vanjee 722Z - Frame {frame_idx} ({len(points)} pts)")
    plt.colorbar(scatter, ax=ax, label="Height (normalized)")
    plt.tight_layout()
    plt.show()
    return True


def read_pcd_binary(pcd_path):
    """读取 PCD binary 文件"""
    with open(pcd_path, 'rb') as f:
        header_lines = []
        while True:
            line = f.readline().decode('ascii').strip()
            header_lines.append(line)
            if line.startswith('DATA'):
                break

        # 解析 header
        n_points = None
        for line in header_lines:
            if line.startswith('POINTS'):
                n_points = int(line.split()[1])
                break

        if n_points is None:
            raise ValueError("无法从 PCD 文件中获取点数")

        # 读取二进制数据 (4个 float32: x, y, z, intensity)
        data = np.frombuffer(f.read(n_points * 16), dtype=np.float32)
        points = data.reshape(n_points, 4)
        return points


def main():
    parser = argparse.ArgumentParser(description="Visualize one PCD frame")
    parser.add_argument("frame_idx", nargs="?", type=int, default=10, help="Frame index")
    parser.add_argument("--pcd-dir", default="pcd_output", help="Directory containing frame_XXXX.pcd")
    args = parser.parse_args()
    pcd_dir = args.pcd_dir

    # 选择要可视化的帧
    frame_idx = args.frame_idx
    pcd_path = os.path.join(pcd_dir, f'frame_{frame_idx:04d}.pcd')

    if not os.path.exists(pcd_path):
        print(f"❌ 文件不存在: {pcd_path}")
        files = sorted(glob.glob(os.path.join(pcd_dir, '*.pcd')))
        print(f"✓ 可用帧: {len(files)} 个")
        if files:
            print(f"  第一帧: {os.path.basename(files[0])}")
            print(f"  最后帧: {os.path.basename(files[-1])}")
        return

    print(f"📂 加载: {pcd_path}")
    points = read_pcd_binary(pcd_path)

    print(f"✓ 点数: {len(points)}")
    print(f"  X 范围: [{points[:,0].min():.3f}, {points[:,0].max():.3f}] m")
    print(f"  Y 范围: [{points[:,1].min():.3f}, {points[:,1].max():.3f}] m")
    print(f"  Z 范围: [{points[:,2].min():.3f}, {points[:,2].max():.3f}] m")
    print(f"  强度范围: [{points[:,3].min():.1f}, {points[:,3].max():.1f}]")

    # 尝试使用 Open3D，失败则使用 Matplotlib
    print("\n🎨 启动可视化...")
    if visualize_with_open3d(pcd_path, frame_idx, points):
        return
    elif visualize_with_matplotlib(pcd_path, frame_idx, points):
        return
    else:
        print("❌ 错误: 未找到可视化库 (需要 open3d 或 matplotlib)")
        print("   请运行以下命令安装:")
        print("   conda install open3d")
        print("   或")
        print("   pip install matplotlib")


if __name__ == '__main__':
    main()
