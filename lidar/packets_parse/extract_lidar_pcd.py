#!/usr/bin/env python3
"""
从 MCAP 文件中提取万集 WLR-722Z 激光雷达 /lidar_packets 并转换为 PCD 点云文件。

数据包协议 (参考 decoder_vanjee_722z.hpp):
  - 点云包: head=0xEE 0xFF, data_type=0x00, 总长 80 字节
  - IMU包:  head=0xEE 0xFF, data_type=0x01, 总长 34 字节
  - 故障码: head=0xEE 0xDD, 总长 41 字节

点云包结构 (Vanjee722zSerialPointCloudMsopPkt, 80 bytes, packed):
  [0:2]   head            (2 bytes) = 0xEE 0xFF
  [2]     protocol_major  (1 byte)
  [3]     protocol_minor  (1 byte)
  [4]     diag_info_ver   (1 byte)
  [5]     data_type       (1 byte) = 0x00 表示点云
  [6:12]  datetime        (6 bytes) year-100, month, day, hour, min, sec
  [12:16] timestamp       (4 bytes) 微秒, little-endian
  --- Vanjee722zSerialPointCloud block ---
  [16:18] azimuth         (2 bytes, uint16, little-endian) 单位: 0.01度, 范围 0~35999
  [18:66] channel[16]     (16 * 3 = 48 bytes)
          每个 channel: distance (uint16, LE, 单位 0.002m) + reflectivity (uint8)
  [66:70] dirty_degree    (4 bytes, uint32, LE)
  [70]    lidar_state     (1 byte)
  [71]    reserved_id     (1 byte)
  [72:74] reserved_info   (2 bytes, uint16, LE)
  [74:76] sequence_num    (2 bytes, uint16, LE)
  [76:80] crc             (4 bytes)

角度校准: Vanjee_722z_VA.csv, 每行 vert_angle, horiz_angle (度)

坐标转换 (来自 C++ 源码):
  distance_res = 0.002  # 米
  angle_vert = chan_angles.vert_angles[chan]   # 单位: 毫度 (0.001°)
  angle_horiz_final = (chan_angles.horiz_angles[chan] + azimuth * 10 + 360000) % 360000  # 毫度
  optcent_2_lidar_arg = 21570  # 毫度
  optcent_2_lidar_l = 2.067e-2  # 米
  optcent_2_lidar_z = 7.95e-3  # 米
  xy = distance * cos(vert)
  x = xy * sin(horiz_final) + L * sin(optcent_2_lidar_angle_hor)
  y = xy * cos(horiz_final) + L * cos(optcent_2_lidar_angle_hor)
  z = distance * sin(vert) + optcent_2_lidar_z
"""

import struct
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

# ============ 配置 ============
MCAP_FILE = 'mcap_data/input.mcap'
TOPIC = '/lidar_packets'
OUTPUT_DIR = 'pcd_output'

# 角度校准文件
ANGLE_CSV = 'config/calibration/Vanjee_722z_VA.csv'

# 最多导出多少帧 (None = 全部)
# 使用 MCAP PTP 时间戳作为 PCD 文件名 (格式: frame_XXXX_TTTTTTTTTT.TTTTTTTTT.pcd，秒级含纳秒小数)
MAX_FRAMES = None

# 距离过滤
DISTANCE_MIN = 0.01   # 米
DISTANCE_MAX = 100.0  # 米
DISTANCE_RES = 0.002  # 米/LSB

# 光心偏移参数 (来自 C++ 源码)
OPTCENT_2_LIDAR_ARG = 21570   # 毫度
OPTCENT_2_LIDAR_L = 2.067e-2  # 米
OPTCENT_2_LIDAR_Z = 7.95e-3   # 米


def load_angle_calibration(csv_path):
    """加载角度校准表，返回 vert_angles 和 horiz_angles (毫度, int)"""
    vert_angles = []
    horiz_angles = []
    with open(csv_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            vert_angles.append(int(float(parts[0]) * 1000))
            horiz_angles.append(int(float(parts[1]) * 1000))
    return vert_angles, horiz_angles


# 预计算三角函数查找表 (0~360000 毫度)
_cos_table = None
_sin_table = None

def init_trig_tables():
    global _cos_table, _sin_table
    # 用于常规角度范围
    angles_rad = np.arange(360000) * math.pi / 180000.0
    _cos_table = np.cos(angles_rad).astype(np.float32)
    _sin_table = np.sin(angles_rad).astype(np.float32)

def COS(angle_millideg):
    return _cos_table[angle_millideg % 360000]

def SIN(angle_millideg):
    return _sin_table[angle_millideg % 360000]


def crc32_mpeg2_padded(data, length):
    """CRC32/MPEG-2 校验"""
    crc = 0xFFFFFFFF
    for i in range(length):
        crc ^= (data[i] << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def parse_vanjee_packet_cdr(raw_data):
    """
    从 CDR 序列化的 VanjeelidarPacket 消息中提取 data 字段。
    VanjeelidarPacket.msg:
        std_msgs/Header header
        uint8[] data

    CDR 布局 (ROS2 CDR serialization):
        [0:4]   CDR header (4 bytes: encapsulation)
        [4:8]   stamp.sec (int32)
        [8:12]  stamp.nanosec (uint32)
        [12:16] frame_id string length (uint32)
        [16:16+N] frame_id string (N bytes, padded to 4-byte align)
        [...]   data sequence length (uint32)
        [...]   data bytes
    
    注意: 时间戳由 MCAP message.publish_time 提供，此处不使用消息头时间戳
    
    返回: data_bytes
    """
    if len(raw_data) < 20:
        return None

    offset = 4  # skip CDR header

    # stamp.sec
    sec = struct.unpack_from('<i', raw_data, offset)[0]
    offset += 4

    # stamp.nanosec
    nsec = struct.unpack_from('<I', raw_data, offset)[0]
    offset += 4

    # frame_id string
    str_len = struct.unpack_from('<I', raw_data, offset)[0]
    offset += 4
    offset += str_len  # skip string bytes
    # align to 4 bytes
    offset = (offset + 3) & ~3

    # data sequence
    data_len = struct.unpack_from('<I', raw_data, offset)[0]
    offset += 4
    data_bytes = raw_data[offset:offset + data_len]

    return data_bytes


def decode_point_cloud_packet(pkt, vert_angles, horiz_angles):
    """
    解析单个 80 字节的点云数据包，返回方位角和 16 个点的列表。
    每个点: (x, y, z, intensity)
    
    注意: 时间戳现在由 MCAP message.publish_time 提供，不再从数据包提取
    
    返回: (azimuth, points)
    """
    if len(pkt) != 80:
        return None

    # 校验 head
    if pkt[0] != 0xEE or pkt[1] != 0xFF:
        return None

    # data_type 应为 0 (点云)
    if pkt[5] != 0x00:
        return None

    # CRC 校验
    crc_check = crc32_mpeg2_padded(pkt, 76)
    crc_pkg = pkt[76] | (pkt[77] << 8) | (pkt[78] << 16) | (pkt[79] << 24)
    if crc_check != crc_pkg:
        return None

    # azimuth (0.01度)
    azimuth = struct.unpack_from('<H', pkt, 16)[0]  # uint16
    azimuth = azimuth % 36000

    points = []
    for chan in range(16):
        ch_offset = 18 + chan * 3
        dist_raw = struct.unpack_from('<H', pkt, ch_offset)[0]
        reflectivity = pkt[ch_offset + 2]

        distance = dist_raw * DISTANCE_RES

        angle_vert = vert_angles[chan]  # 毫度
        angle_horiz_final = (horiz_angles[chan] + azimuth * 10 + 360000) % 360000

        optcent_2_lidar_angle_hor = (azimuth * 10 + OPTCENT_2_LIDAR_ARG + 360000) % 360000

        if DISTANCE_MIN <= distance <= DISTANCE_MAX:
            xy = distance * COS(angle_vert)
            x = xy * SIN(angle_horiz_final) + OPTCENT_2_LIDAR_L * SIN(optcent_2_lidar_angle_hor)
            y = xy * COS(angle_horiz_final) + OPTCENT_2_LIDAR_L * COS(optcent_2_lidar_angle_hor)
            z = distance * SIN(angle_vert) + OPTCENT_2_LIDAR_Z
            points.append((float(x), float(y), float(z), reflectivity))
        # else: 跳过无效距离点

    return azimuth, points


def extract_sub_packets(data_bytes):
    """
    从原始 data 字节流中提取多个子数据包。
    数据流中可能包含点云包(80B)、IMU包(34B)、故障码包(41B)，连续排列。
    """
    packets = []
    i = 0
    while i < len(data_bytes):
        if len(data_bytes) - i < 2:
            break

        if data_bytes[i] != 0xEE:
            i += 1
            continue

        if data_bytes[i + 1] == 0xFF:
            if len(data_bytes) - i < 6:
                break
            data_type = data_bytes[i + 5]
            if data_type == 0x00:
                # 点云包 80 字节
                if len(data_bytes) - i < 80:
                    break
                packets.append(('pointcloud', data_bytes[i:i+80]))
                i += 80
            elif data_type == 0x01:
                # IMU 包 34 字节
                if len(data_bytes) - i < 34:
                    break
                i += 34
            else:
                i += 1
        elif data_bytes[i + 1] == 0xDD:
            # 故障码包 41 字节
            if len(data_bytes) - i < 41:
                break
            i += 41
        else:
            i += 1

    return packets


def save_pcd(filepath, points_xyz, intensities):
    """保存为 PCD ASCII 格式"""
    n = len(points_xyz)
    with open(filepath, 'w') as f:
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
            f.write(f"{points_xyz[i][0]:.6f} {points_xyz[i][1]:.6f} {points_xyz[i][2]:.6f} {intensities[i]:.0f}\n")


def save_pcd_binary(filepath, points_xyz, intensities):
    """保存为 PCD Binary 格式 (更快)"""
    n = len(points_xyz)
    arr = np.zeros((n, 4), dtype=np.float32)
    arr[:, :3] = points_xyz
    arr[:, 3] = intensities

    with open(filepath, 'wb') as f:
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
        f.write(arr.tobytes())


def main():
    print("=" * 60)
    print("万集 WLR-722Z 激光雷达点云提取工具")
    print("=" * 60)

    # 检查文件
    if not Path(MCAP_FILE).exists():
        print(f"错误: MCAP 文件不存在: {MCAP_FILE}")
        sys.exit(1)

    if not Path(ANGLE_CSV).exists():
        print(f"错误: 角度校准文件不存在: {ANGLE_CSV}")
        sys.exit(1)

    # 加载角度校准
    print(f"加载角度校准: {ANGLE_CSV}")
    vert_angles, horiz_angles = load_angle_calibration(ANGLE_CSV)
    print(f"  通道数: {len(vert_angles)}")
    for i, (v, h) in enumerate(zip(vert_angles, horiz_angles)):
        print(f"    CH{i:2d}: vert={v/1000:.3f}° horiz={h/1000:.3f}°")

    # 初始化三角函数表
    print("初始化三角函数查找表...")
    init_trig_tables()

    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 读取 MCAP
    print(f"\n读取 MCAP: {MCAP_FILE}")
    print(f"提取 Topic: {TOPIC}")

    try:
        from mcap.reader import make_reader
    except ImportError:
        print("错误: 请安装 mcap 库: pip install mcap")
        sys.exit(1)

    # 帧拆分逻辑: 当 azimuth 回到 0 附近时，视为新一帧
    frame_points = []          # 当前帧的点集: list of (x, y, z, intensity)
    frame_count = 0
    total_packets = 0
    valid_pc_packets = 0
    crc_fail_count = 0
    prev_azimuth = -1
    prev_azimuth_trans = -1    # 上一个子包的 azimuth_trans，用于帧切割
    frame_start_timestamp_ns = None  # 每帧的起始时间戳 (纳秒)

    t_start = time.time()

    with open(MCAP_FILE, 'rb') as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages(topics=[TOPIC]):
            # 获取 MCAP 消息的 PTP 时间戳 (纳秒)
            mcap_timestamp_ns = message.publish_time
            
            # 解析 CDR 消息，提取 data 字段
            data_bytes = parse_vanjee_packet_cdr(message.data)
            if data_bytes is None or len(data_bytes) == 0:
                continue

            total_packets += 1

            # 从数据流中提取子数据包
            sub_packets = extract_sub_packets(data_bytes)

            for pkt_type, pkt_data in sub_packets:
                if pkt_type != 'pointcloud':
                    continue

                result = decode_point_cloud_packet(pkt_data, vert_angles, horiz_angles)
                if result is None:
                    crc_fail_count += 1
                    continue

                azimuth, points = result
                valid_pc_packets += 1

                # 记录帧的起始时间戳
                if frame_start_timestamp_ns is None:
                    frame_start_timestamp_ns = mcap_timestamp_ns

                # 帧切割: azimuth 从大回小 (过零点)
                # 修复：对齐驱动 SplitStrategyByAngle 的逻辑:
                #   azimuth_trans = (azimuth + resolution) % 36000
                #   触发条件: azimuth_trans < prev_azimuth_trans (纯回落检测)
                # 原条件 "azimuth_trans < 60 and prev_azimuth > 100" 在 azimuth 跳过 0°
                # 落在 [0.6°, 1.8°] 时 azimuth_trans 不满足 < 60，导致漏切。
                if prev_azimuth >= 0:
                    azimuth_trans = (azimuth + 60) % 36000
                    if azimuth_trans < prev_azimuth_trans:
                        # 保存当前帧
                        if len(frame_points) > 0:
                            frame_count += 1
                            xyz = np.array([(p[0], p[1], p[2]) for p in frame_points], dtype=np.float32)
                            intensity = np.array([p[3] for p in frame_points], dtype=np.float32)

                            # 使用 MCAP PTP 时间戳作为文件名 (秒级，含纳秒小数)
                            timestamp_sec = frame_start_timestamp_ns / 1e9
                            pcd_path = os.path.join(OUTPUT_DIR, f"frame_{frame_count:04d}_{timestamp_sec:.9f}.pcd")
                            save_pcd(pcd_path, xyz, intensity)
                            print(f"  帧 {frame_count:4d}: {len(frame_points):6d} 个点, 时间戳: {timestamp_sec:.9f} -> {os.path.basename(pcd_path)}")

                            frame_points = []
                            frame_start_timestamp_ns = None

                            if MAX_FRAMES and frame_count >= MAX_FRAMES:
                                print(f"\n已达到最大帧数限制 ({MAX_FRAMES})，停止提取")
                                break

                prev_azimuth = azimuth
                prev_azimuth_trans = (azimuth + 60) % 36000
                frame_points.extend(points)

            if MAX_FRAMES and frame_count >= MAX_FRAMES:
                break

            if total_packets % 10000 == 0:
                print(f"  已处理 {total_packets} 个消息, 有效点云包 {valid_pc_packets}, 帧 {frame_count}")

    # 保存最后一帧
    if len(frame_points) > 0 and (MAX_FRAMES is None or frame_count < MAX_FRAMES):
        frame_count += 1
        xyz = np.array([(p[0], p[1], p[2]) for p in frame_points], dtype=np.float32)
        intensity = np.array([p[3] for p in frame_points], dtype=np.float32)
        # 使用 MCAP PTP 时间戳作为文件名 (秒级，含纳秒小数)
        ts = frame_start_timestamp_ns if frame_start_timestamp_ns is not None else 0
        timestamp_sec = ts / 1e9
        pcd_path = os.path.join(OUTPUT_DIR, f"frame_{frame_count:04d}_{timestamp_sec:.9f}.pcd")
        save_pcd(pcd_path, xyz, intensity)
        print(f"  帧 {frame_count:4d}: {len(frame_points):6d} 个点, 时间戳: {timestamp_sec:.9f} -> {os.path.basename(pcd_path)}")

    t_elapsed = time.time() - t_start

    print(f"\n{'=' * 60}")
    print(f"提取完成!")
    print(f"  总消息数:       {total_packets}")
    print(f"  有效点云包数:   {valid_pc_packets}")
    print(f"  CRC 校验失败:   {crc_fail_count}")
    print(f"  导出帧数:       {frame_count}")
    print(f"  输出目录:       {OUTPUT_DIR}")
    print(f"  耗时:           {t_elapsed:.1f} 秒")
    print(f"{'=' * 60}")

    if frame_count > 0:
        print(f"\n可使用以下方式可视化:")
        print(f"  1. CloudCompare: 直接打开 .pcd 文件")
        print(f"  2. Open3D (Python):")
        print(f"     import open3d as o3d")
        print(f"     pcd = o3d.io.read_point_cloud('{OUTPUT_DIR}/frame_0001.pcd')")
        print(f"     o3d.visualization.draw_geometries([pcd])")
    else:
        print("\n警告: 未提取到任何帧，请检查数据包格式")


if __name__ == '__main__':
    main()
