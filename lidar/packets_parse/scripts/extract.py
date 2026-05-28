#!/usr/bin/env python3
"""
万集 WLR-722Z 激光雷达点云提取工具

从 MCAP 文件中提取 /lidar_packets 并转换为 PCD 点云文件
"""

import argparse
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.calibration import CalibrationManager
from src.core.decoder import VanjeeDecoder
from src.core.extractor import FrameExtractor


def main():
    parser = argparse.ArgumentParser(
        description='从 MCAP 文件中提取万集雷达点云',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 基本用法 (使用默认配置)
  python scripts/extract.py --mcap /path/to/file.mcap

  # 指定 MCAP 文件
  python scripts/extract.py --mcap /path/to/file.mcap

  # 指定输出目录
  python scripts/extract.py --output /path/to/output

  # 只提取前 100 帧
  python scripts/extract.py --max-frames 100

  # 使用不同型号的校准文件
  python scripts/extract.py --model 722
        '''
    )
    
    parser.add_argument(
        '--mcap',
        type=str,
        required=True,
        help='MCAP 文件路径'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='pcd_output',
        help='输出目录 (默认: pcd_output)'
    )
    parser.add_argument(
        '--calibration',
        type=str,
        default=None,
        help='校准文件路径 (默认: 自动查找)'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='722z',
        choices=['722z', '722', '720_16', '722f', '722h'],
        help='雷达型号 (默认: 722z)'
    )
    parser.add_argument(
        '--max-frames',
        type=int,
        default=None,
        help='最多提取多少帧 (默认: 全部)'
    )
    parser.add_argument(
        '--topic',
        type=str,
        default='/lidar_packets',
        help='消息主题 (默认: /lidar_packets)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出'
    )
    
    args = parser.parse_args()
    
    # 检查 MCAP 文件
    if not Path(args.mcap).exists():
        print(f"❌ 错误: MCAP 文件不存在: {args.mcap}")
        sys.exit(1)
    
    # 加载校准参数
    print("📋 加载校准参数...")
    calib = CalibrationManager()
    
    if args.calibration:
        calib.load(args.calibration)
    else:
        calib.load_default(args.model)
    
    is_valid, msg = calib.validate()
    if not is_valid:
        print(f"❌ 错误: {msg}")
        sys.exit(1)
    
    vert_angles, horiz_angles = calib.get_all_angles()
    print(f"✓ 加载了 {calib.num_channels} 通道的校准参数")
    
    if args.verbose:
        print(f"  校准文件: {calib.csv_path}")
        for i in range(min(5, calib.num_channels)):
            vert = vert_angles[i] / 1000
            horiz = horiz_angles[i] / 1000
            print(f"    CH{i}: vert={vert:.2f}° horiz={horiz:.3f}°")
        if calib.num_channels > 5:
            print(f"    ... ({calib.num_channels - 5} more channels)")
    
    # 初始化提取器
    print(f"\n🔧 初始化提取器...")
    extractor = FrameExtractor(vert_angles, horiz_angles, args.output)
    print(f"✓ 输出目录: {args.output}")
    
    # 打开 MCAP 文件并提取
    print(f"\n📂 读取 MCAP 文件: {args.mcap}")
    print(f"📡 主题: {args.topic}\n")
    
    try:
        from mcap.reader import make_reader
    except ImportError:
        print("❌ 错误: 请安装 mcap 库")
        print("   pip install mcap")
        sys.exit(1)
    
    # 统计信息
    frame_count = 0
    total_packets = 0
    valid_pc_packets = 0
    crc_fail_count = 0
    prev_azimuth = -1
    frame_start_timestamp_ns = None
    frame_points = []
    
    t_start = time.time()
    
    with open(args.mcap, 'rb') as f:
        reader = make_reader(f)
        
        for schema, channel, message in reader.iter_messages(topics=[args.topic]):
            # 处理消息
            timestamp_ns = message.publish_time
            
            if frame_start_timestamp_ns is None:
                frame_start_timestamp_ns = timestamp_ns
            
            results = extractor.process_message(message)
            total_packets += 1
            
            for azimuth, points, _ in results:
                valid_pc_packets += 1
                
                # 检测帧边界
                if prev_azimuth >= 0:
                    if extractor.detect_frame_boundary(prev_azimuth, azimuth):
                        # 保存上一帧
                        if len(frame_points) > 0:
                            frame_count += 1
                            filepath = extractor.save_frame(
                                frame_count, frame_points, frame_start_timestamp_ns
                            )
                            print(f"  帧 {frame_count:4d}: {len(frame_points):6d} 个点 -> {Path(filepath).name}")
                            
                            frame_points = []
                            frame_start_timestamp_ns = timestamp_ns
                            
                            if args.max_frames and frame_count >= args.max_frames:
                                print(f"\n已达到最大帧数限制 ({args.max_frames})")
                                break
                
                prev_azimuth = azimuth
                frame_points.extend(points)
            
            if args.max_frames and frame_count >= args.max_frames:
                break
            
            if total_packets % 10000 == 0 and total_packets > 0:
                print(f"  已处理 {total_packets} 个消息...")
    
    # 保存最后一帧
    if len(frame_points) > 0 and (args.max_frames is None or frame_count < args.max_frames):
        frame_count += 1
        filepath = extractor.save_frame(frame_count, frame_points, frame_start_timestamp_ns)
        print(f"  帧 {frame_count:4d}: {len(frame_points):6d} 个点 -> {Path(filepath).name}")
    
    t_elapsed = time.time() - t_start
    
    # 打印统计
    print(f"\n{'='*60}")
    print(f"✅ 提取完成!")
    print(f"{'='*60}")
    print(f"  总消息数:       {total_packets}")
    print(f"  有效点云包数:   {valid_pc_packets}")
    print(f"  CRC 校验失败:   {crc_fail_count}")
    print(f"  导出帧数:       {frame_count}")
    print(f"  输出目录:       {args.output}")
    print(f"  耗时:           {t_elapsed:.1f} 秒")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
