#!/usr/bin/env python3
"""
高级点云处理工具
- 合并多帧点云
- 统计点云的几何特性
- 导出为其他格式
- 简单的体素滤波去噪
"""
import os
import re
import glob
import numpy as np
from pathlib import Path


def read_pcd_binary(pcd_path):
    """Read XYZI from either ASCII or binary PCD, honoring the declared types."""
    from sensor_tools.pcd import xyzi
    return xyzi(pcd_path)


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
    if not np.isfinite(voxel_size) or voxel_size <= 0:
        raise ValueError('voxel_size must be finite and positive')
    points_xyzi = points_xyzi[np.isfinite(points_xyzi[:, :3]).all(axis=1)]
    if not len(points_xyzi):
        return np.empty((0, 4), dtype=np.float32)
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
        raise ValueError("no PCD files found")

    if frame_range:
        start, end = frame_range
        files = [f for f in files if start <= int(Path(f).stem.split('_')[1]) <= end]

    if not files:
        raise ValueError("no files in requested frame range")

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

    if not all_points:
        raise ValueError("no PCD files matched")
    merged = np.vstack(all_points)
    merged = merged[np.isfinite(merged[:, :3]).all(axis=1)]
    if not len(merged):
        raise ValueError("no finite points")
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
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    write_pcd_binary(output_path, merged)
    print(f"\n✓ 已保存: {output_path}")


def export_format(pcd_path, output_format='xyz', output_path=None):
    """Export XYZI; additional source fields (ring/time) are not part of this view."""
    points = read_pcd_binary(pcd_path)
    if not len(points):
        raise ValueError('empty point cloud')
    suffix = '.pcd' if output_format == 'pcd_ascii' else '.' + output_format
    output = Path(output_path) if output_path else Path(pcd_path).with_name(Path(pcd_path).stem + '_export' + suffix)
    if output.resolve() == Path(pcd_path).resolve():
        raise ValueError('output must differ from input')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == 'pcd_ascii':
        write_pcd_ascii(output, points)
    elif output_format == 'xyz':
        write_xyz(output, points[:, :3])
    elif output_format == 'ply':
        with output.open('w') as file:
            file.write(f'ply\nformat ascii 1.0\nelement vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\nproperty float intensity\nend_header\n')
            np.savetxt(file, points, fmt='%.9g')
    elif output_format == 'las':
        import laspy
        points = points[np.isfinite(points).all(axis=1)]
        if not len(points):
            raise ValueError('no finite LAS points')
        header = laspy.LasHeader(point_format=0, version='1.2')
        header.offsets = points[:, :3].min(axis=0)
        header.scales = np.array([0.0001] * 3)
        las = laspy.LasData(header)
        las.x, las.y, las.z = points[:, 0], points[:, 1], points[:, 2]
        las.intensity = np.clip(points[:, 3], 0, 65535).astype(np.uint16)
        las.write(output)
    else:
        raise ValueError(f'unsupported output format: {output_format}')
    print(f'Saved: {output}')
    return output


def main():
    import argparse
    import subprocess
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ['merge', 'merge_downsample']:
        sub = subs.add_parser(name)
        sub.add_argument('--pcd-dir', required=True)
        sub.add_argument('--output', required=True)
        sub.add_argument('--start', type=int)
        sub.add_argument('--end', type=int)
        if name == 'merge_downsample':
            sub.add_argument('--voxel-size', type=float, default=.05)
    sub = subs.add_parser('export')
    sub.add_argument('input')
    sub.add_argument('--format', choices=['pcd_ascii', 'xyz', 'ply', 'las'], default='xyz')
    sub.add_argument('--output')
    sub = subs.add_parser('analyze')
    sub.add_argument('--pcd-dir', required=True)
    args = parser.parse_args()
    try:
        if args.command.startswith('merge'):
            if (args.start is None) != (args.end is None) or (args.start is not None and args.start > args.end):
                parser.error('provide both --start and --end, with start <= end')
            merge_frames(args.pcd_dir, args.output,
                         frame_range=(args.start, args.end) if args.start is not None else None,
                         voxel_downsample_size=getattr(args, 'voxel_size', None))
        elif args.command == 'export':
            export_format(args.input, args.format, args.output)
        else:
            return subprocess.call([sys.executable, str(Path(__file__).with_name('analyze_pcd_quality.py')), args.pcd_dir])
    except (OSError, ValueError, ImportError) as error:
        parser.exit(1, f'error: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
