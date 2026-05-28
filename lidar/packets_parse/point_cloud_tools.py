#!/usr/bin/env python3
"""
高级点云处理工具
- 合并多帧点云
- 统计点云的几何特性
- 导出为其他格式
- 简单的体素滤波去噪
"""
import os
import glob
import numpy as np
from pathlib import Path


def read_pcd_binary(pcd_path):
    """读取 PCD binary 文件，返回 (n, 4) 数组 [x, y, z, intensity]"""
    with open(pcd_path, 'rb') as f:
        # 读取 header
        n_points = None
        while True:
            line = f.readline().decode('ascii', errors='ignore').strip()
            if line.startswith('POINTS'):
                n_points = int(line.split()[1])
            elif line.startswith('DATA'):
                break

        if n_points is None:
            return None

        # 读取二进制数据
        data = np.frombuffer(f.read(n_points * 16), dtype=np.float32)
        return data.reshape(n_points, 4)


def write_pcd_binary(pcd_path, points_xyzi):
    """写入 PCD binary 文件"""
    n = len(points_xyzi)
    with open(pcd_path, 'wb') as f:
        header = (
            "# .PCD v0.7 - Point Cloud Data file format\n"
            "VERSION 0.7\n"
            "FIELDS x y z intensity\n"
            "SIZE 4 4 4 4\n"
            "TYPE F F F F\n"
            "COUNT 1 1 1 1\n"
            f"WIDTH {n}\n"
            "HEIGHT 1\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            f"POINTS {n}\n"
            "DATA binary\n"
        )
        f.write(header.encode('ascii'))
        f.write(points_xyzi.astype(np.float32).tobytes())


def write_pcd_ascii(pcd_path, points_xyzi):
    """写入 PCD ASCII 文件"""
    n = len(points_xyzi)
    with open(pcd_path, 'w') as f:
        f.write("# .PCD v0.7 - Point Cloud Data file format\n")
        f.write("VERSION 0.7\n")
        f.write("FIELDS x y z intensity\n")
        f.write("SIZE 4 4 4 4\n")
        f.write("TYPE F F F F\n")
        f.write("COUNT 1 1 1 1\n")
        f.write(f"WIDTH {n}\n")
        f.write("HEIGHT 1\n")
        f.write("VIEWPOINT 0 0 0 1 0 0 0\n")
        f.write(f"POINTS {n}\n")
        f.write("DATA ascii\n")
        for i in range(n):
            f.write(f"{points_xyzi[i, 0]:.6f} {points_xyzi[i, 1]:.6f} {points_xyzi[i, 2]:.6f} {points_xyzi[i, 3]:.1f}\n")


def write_xyz(xyz_path, points_xyz):
    """写入简单的 XYZ 文本格式"""
    n = len(points_xyz)
    with open(xyz_path, 'w') as f:
        for i in range(n):
            f.write(f"{points_xyz[i, 0]:.6f} {points_xyz[i, 1]:.6f} {points_xyz[i, 2]:.6f}\n")


def voxel_downsample(points_xyzi, voxel_size=0.05):
    """
    体素下采样（简单版本）
    将点云分成边长为 voxel_size 的体素，每个体素只保留一个点
    """
    xyz = points_xyzi[:, :3]
    intensity = points_xyzi[:, 3]

    # 将坐标量化到体素网格
    voxel_indices = np.floor(xyz / voxel_size).astype(int)

    # 使用字典存储每个体素的第一个点
    voxel_dict = {}
    downsampled = []

    for i in range(len(points_xyzi)):
        idx_tuple = tuple(voxel_indices[i])
        if idx_tuple not in voxel_dict:
            voxel_dict[idx_tuple] = i
            downsampled.append(points_xyzi[i])

    return np.array(downsampled, dtype=np.float32)


def merge_frames(pcd_dir, output_path, frame_range=None, voxel_downsample_size=None):
    """
    合并多帧点云
    
    Args:
        pcd_dir: PCD 文件所在目录
        output_path: 输出文件路径
        frame_range: 帧范围 tuple (start, end)，如 (1, 10) 表示第 1~10 帧
        voxel_downsample_size: 体素下采样大小，None 表示不下采样
    """
    files = sorted(glob.glob(os.path.join(pcd_dir, 'frame_*.pcd')))

    if not files:
        print(f"❌ 没有找到 PCD 文件")
        return

    if frame_range:
        start, end = frame_range
        files = [f for f in files if start <= int(Path(f).stem.split('_')[1]) <= end]

    if not files:
        print(f"❌ 帧范围内没有文件")
        return

    print(f"📂 合并 {len(files)} 帧...")
    all_points = []
    total_points = 0

    for i, pcd_path in enumerate(files):
        frame_idx = Path(pcd_path).stem.split('_')[1]
        points = read_pcd_binary(pcd_path)
        if points is not None:
            all_points.append(points)
            total_points += len(points)
            print(f"  [{'='*(i%10+1):10s}] Frame {frame_idx}: {len(points)} points")

    merged = np.vstack(all_points)
    print(f"\n✓ 合并完成: {total_points} 个点")

    if voxel_downsample_size:
        print(f"🔽 体素下采样 (voxel_size={voxel_downsample_size}m)...")
        merged = voxel_downsample(merged, voxel_downsample_size)
        print(f"✓ 下采样完成: {len(merged)} 个点")

    # 统计
    xyz = merged[:, :3]
    intensity = merged[:, 3]
    print(f"\n📊 统计信息:")
    print(f"  X: [{xyz[:, 0].min():.3f}, {xyz[:, 0].max():.3f}] m")
    print(f"  Y: [{xyz[:, 1].min():.3f}, {xyz[:, 1].max():.3f}] m")
    print(f"  Z: [{xyz[:, 2].min():.3f}, {xyz[:, 2].max():.3f}] m")
    print(f"  强度: [{intensity.min():.1f}, {intensity.max():.1f}]")

    # 保存
    write_pcd_binary(output_path, merged)
    print(f"\n✓ 已保存: {output_path}")


def export_format(pcd_path, output_format='xyz'):
    """
    转换点云格式
    
    支持格式: pcd_ascii, xyz, ply (需 open3d)
    """
    print(f"📂 读取: {pcd_path}")
    points = read_pcd_binary(pcd_path)

    if points is None:
        print("❌ 无法读取 PCD 文件")
        return

    base_path = Path(pcd_path).stem

    if output_format == 'pcd_ascii':
        output = f"{base_path}_ascii.pcd"
        write_pcd_ascii(output, points)
        print(f"✓ 已保存为 PCD ASCII: {output}")

    elif output_format == 'xyz':
        output = f"{base_path}.xyz"
        write_xyz(output, points[:, :3])
        print(f"✓ 已保存为 XYZ: {output}")

    elif output_format == 'ply':
        try:
            import open3d as o3d
            output = f"{base_path}.ply"
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points[:, :3])
            o3d.io.write_point_cloud(output, pcd)
            print(f"✓ 已保存为 PLY: {output}")
        except ImportError:
            print("❌ 需要安装 open3d: pip install open3d")

    elif output_format == 'las':
        try:
            import open3d as o3d
            output = f"{base_path}.las"
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points[:, :3])
            o3d.io.write_point_cloud(output, pcd)
            print(f"✓ 已保存为 LAS: {output}")
        except ImportError:
            print("❌ 需要安装 open3d: pip install open3d")

    else:
        print(f"❌ 不支持的格式: {output_format}")


def main():
    import sys

    if len(sys.argv) < 2:
        print("高级点云处理工具")
        print("\n用法:")
        print("  python point_cloud_tools.py merge [frame_start] [frame_end]")
        print("    合并帧范围内的所有点云 (无下采样)")
        print("    例: python point_cloud_tools.py merge 1 10")
        print()
        print("  python point_cloud_tools.py merge_downsample [frame_start] [frame_end] [voxel_size]")
        print("    合并并体素下采样")
        print("    例: python point_cloud_tools.py merge_downsample 1 50 0.1")
        print()
        print("  python point_cloud_tools.py export [format]")
        print("    转换单帧格式 (format: pcd_ascii, xyz, ply, las)")
        print("    例: python point_cloud_tools.py export xyz")
        print()
        print("  python point_cloud_tools.py analyze")
        print("    分析点云几何特性（同 analyze_pcd_quality.py）")
        return

    pcd_dir = 'pcd_output'

    if sys.argv[1] == 'merge':
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        end = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        output = os.path.join(pcd_dir, f'merged_{start}_{end}.pcd')
        merge_frames(pcd_dir, output, frame_range=(start, end))

    elif sys.argv[1] == 'merge_downsample':
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        end = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        voxel_size = float(sys.argv[4]) if len(sys.argv) > 4 else 0.05
        output = os.path.join(pcd_dir, f'merged_{start}_{end}_downsampled.pcd')
        merge_frames(pcd_dir, output, frame_range=(start, end), voxel_downsample_size=voxel_size)

    elif sys.argv[1] == 'export':
        fmt = sys.argv[2] if len(sys.argv) > 2 else 'xyz'
        pcd_path = os.path.join(pcd_dir, 'frame_0001.pcd')
        export_format(pcd_path, output_format=fmt)

    elif sys.argv[1] == 'analyze':
        # 调用分析脚本
        os.system('python analyze_pcd_quality.py')

    else:
        print(f"❌ 未知命令: {sys.argv[1]}")


if __name__ == '__main__':
    main()
