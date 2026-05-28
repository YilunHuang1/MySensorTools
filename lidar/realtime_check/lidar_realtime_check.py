#!/usr/bin/env python3
"""
万集 WLR-722Z LiDAR 实时点云诊断工具

直接在 S100 上运行，订阅 ROS2 Topic 抓取点云数据并输出每帧统计信息。
用于快速判断 LiDAR 硬件是否正常工作。

使用方法 (在 S100 上运行):
  # 检查 /lidar_points (PointCloud2，驱动已解码的点云)
  python3 lidar_realtime_check.py

  # 检查 /lidar_packets (原始数据包)
  python3 lidar_realtime_check.py --topic /lidar_packets --mode raw

  # 指定帧数
  python3 lidar_realtime_check.py --max-frames 20

  # 同时检查两个 topic
  python3 lidar_realtime_check.py --mode both

依赖: rclpy, sensor_msgs (ROS2 环境自带)
"""

import argparse
import sys
import struct
import math
import time
import signal
from collections import defaultdict

# ============================================================
# 全局控制
# ============================================================
_running = True

def signal_handler(sig, frame):
    global _running
    _running = False
    print("\n\n⚠️  收到中断信号，正在退出...")

signal.signal(signal.SIGINT, signal_handler)

# ============================================================
# 万集 722Z 原始包解码器 (轻量版, 不依赖 numpy)
# ============================================================
DISTANCE_RES = 0.002  # 米/LSB
DISTANCE_MIN = 0.0    # 诊断模式: 不过滤, 展示所有原始值
DISTANCE_MAX = 200.0

def crc32_mpeg2(data, length):
    crc = 0xFFFFFFFF
    for i in range(length):
        crc ^= (data[i] << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def parse_raw_packet_data(raw_data):
    """
    兼容两种调用场景:
      1. rclpy 已反序列化的消息对象 (msg.data) → 直接返回 bytes, 无需 CDR 解析
      2. 手动传入原始 CDR 字节流 (离线 MCAP 解析用) → 走 CDR offset 解析
    本函数只处理场景2; 场景1 在 callback 中直接 bytes(msg.data) 即可.
    """
    if len(raw_data) < 20:
        return None
    try:
        offset = 4  # CDR header
        offset += 4  # stamp.sec
        offset += 4  # stamp.nanosec
        if offset + 4 > len(raw_data):
            return None
        str_len = struct.unpack_from('<I', raw_data, offset)[0]
        if str_len > 256 or offset + 4 + str_len > len(raw_data):
            # 不像合法的 CDR, 直接把整段当作 data 返回 (场景1降级)
            return raw_data
        offset += 4 + str_len
        offset = (offset + 3) & ~3  # align
        if offset + 4 > len(raw_data):
            return None
        data_len = struct.unpack_from('<I', raw_data, offset)[0]
        offset += 4
        if offset + data_len > len(raw_data):
            return None
        return raw_data[offset:offset + data_len]
    except struct.error:
        return None


def extract_sub_packets(data_bytes):
    """提取子数据包, 返回类型和数据"""
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
                if len(data_bytes) - i < 80:
                    break
                packets.append(('pointcloud', data_bytes[i:i+80]))
                i += 80
            elif data_type == 0x01:
                if len(data_bytes) - i < 34:
                    break
                packets.append(('imu', data_bytes[i:i+34]))
                i += 34
            else:
                packets.append(('unknown', data_bytes[i:i+6]))
                i += 1
        elif data_bytes[i + 1] == 0xDD:
            if len(data_bytes) - i < 41:
                break
            packets.append(('fault', data_bytes[i:i+41]))
            i += 41
        else:
            i += 1
    return packets


def decode_pointcloud_packet_diag(pkt):
    """
    诊断模式解码: 返回原始距离值, 不过滤, 用于诊断
    返回: dict 或 None
    """
    if len(pkt) != 80:
        return None
    if pkt[0] != 0xEE or pkt[1] != 0xFF:
        return None
    if pkt[5] != 0x00:
        return None

    # CRC
    crc_check = crc32_mpeg2(pkt, 76)
    crc_pkg = pkt[76] | (pkt[77] << 8) | (pkt[78] << 16) | (pkt[79] << 24)
    crc_ok = (crc_check == crc_pkg)

    azimuth = struct.unpack_from('<H', pkt, 16)[0] % 36000

    channels = []
    for ch in range(16):
        ch_offset = 18 + ch * 3
        dist_raw = struct.unpack_from('<H', pkt, ch_offset)[0]
        reflectivity = pkt[ch_offset + 2]
        distance_m = dist_raw * DISTANCE_RES
        channels.append({
            'channel': ch,
            'dist_raw': dist_raw,
            'distance_m': distance_m,
            'reflectivity': reflectivity,
        })

    return {
        'azimuth': azimuth,
        'azimuth_deg': azimuth / 100.0,
        'crc_ok': crc_ok,
        'channels': channels,
    }


# ============================================================
# PointCloud2 解析 (sensor_msgs/msg/PointCloud2)
# ============================================================
def parse_pointcloud2(msg):
    """解析 PointCloud2 消息, 提取点数和距离统计"""
    width = msg.width
    height = msg.height
    point_step = msg.point_step
    row_step = msg.row_step
    is_dense = msg.is_dense
    total_points = width * height
    data = bytes(msg.data)

    # 找到 x, y, z 字段偏移
    field_map = {}
    for f in msg.fields:
        field_map[f.name] = (f.offset, f.datatype, f.count)

    has_xyz = 'x' in field_map and 'y' in field_map and 'z' in field_map
    has_intensity = 'intensity' in field_map or 'i' in field_map

    stats = {
        'total_points': total_points,
        'width': width,
        'height': height,
        'point_step': point_step,
        'is_dense': is_dense,
        'data_length': len(data),
        'fields': [f.name for f in msg.fields],
        'has_xyz': has_xyz,
    }

    if total_points == 0 or not has_xyz:
        stats['valid_points'] = 0
        stats['nan_points'] = 0
        stats['zero_points'] = 0
        stats['min_distance'] = 0
        stats['max_distance'] = 0
        stats['mean_distance'] = 0
        return stats

    x_off = field_map['x'][0]
    y_off = field_map['y'][0]
    z_off = field_map['z'][0]

    valid_count = 0
    nan_count = 0
    zero_count = 0
    min_dist = float('inf')
    max_dist = 0.0
    sum_dist = 0.0
    intensity_sum = 0.0
    min_intensity = float('inf')
    max_intensity = 0.0

    int_key = 'intensity' if 'intensity' in field_map else ('i' if 'i' in field_map else None)
    int_off = field_map[int_key][0] if int_key else None

    # 采样解析 (全量太慢时可改为抽样)
    sample_step = max(1, total_points // 10000)  # 最多采样 10000 个点

    for idx in range(0, total_points, sample_step):
        offset = idx * point_step
        if offset + point_step > len(data):
            break
        x = struct.unpack_from('<f', data, offset + x_off)[0]
        y = struct.unpack_from('<f', data, offset + y_off)[0]
        z = struct.unpack_from('<f', data, offset + z_off)[0]

        if math.isnan(x) or math.isnan(y) or math.isnan(z):
            nan_count += 1
            continue

        dist = math.sqrt(x*x + y*y + z*z)
        if dist < 1e-6:
            zero_count += 1
            continue

        valid_count += 1
        if dist < min_dist:
            min_dist = dist
        if dist > max_dist:
            max_dist = dist
        sum_dist += dist

        if int_off is not None:
            try:
                iv = struct.unpack_from('<f', data, offset + int_off)[0]
                intensity_sum += iv
                if iv < min_intensity:
                    min_intensity = iv
                if iv > max_intensity:
                    max_intensity = iv
            except Exception:
                pass

    scale_factor = sample_step  # 估算全量
    stats['valid_points'] = valid_count * scale_factor
    stats['nan_points'] = nan_count * scale_factor
    stats['zero_points'] = zero_count * scale_factor
    stats['min_distance'] = min_dist if valid_count > 0 else 0
    stats['max_distance'] = max_dist if valid_count > 0 else 0
    stats['mean_distance'] = (sum_dist / valid_count) if valid_count > 0 else 0
    stats['sample_step'] = sample_step
    stats['sampled_valid'] = valid_count
    if int_off is not None and valid_count > 0:
        stats['min_intensity'] = min_intensity
        stats['max_intensity'] = max_intensity
        stats['mean_intensity'] = intensity_sum / valid_count

    return stats


# ============================================================
# ROS2 订阅检查
# ============================================================
def check_pointcloud2_topic(topic, max_frames, timeout):
    """订阅 PointCloud2 topic 并统计"""
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import PointCloud2

    rclpy.init()
    node = Node('lidar_pc2_checker')

    frame_count = [0]
    t_start = time.time()
    t_first = [None]

    print(f"\n{'='*70}")
    print(f"📡 订阅 PointCloud2: {topic}")
    print(f"{'='*70}")
    print(f"{'帧#':>5} | {'总点数':>8} | {'有效点':>8} | {'NaN':>6} | {'零值':>6} | "
          f"{'最小距离':>8} | {'最大距离':>8} | {'平均距离':>8} | {'延迟ms':>7}")
    print('-' * 100)

    def callback(msg):
        if not _running:
            return
        if t_first[0] is None:
            t_first[0] = time.time()

        frame_count[0] += 1
        stats = parse_pointcloud2(msg)

        now_ns = node.get_clock().now().nanoseconds
        msg_stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        latency_ms = (now_ns - msg_stamp_ns) / 1e6 if msg_stamp_ns > 0 else -1

        print(f"{frame_count[0]:5d} | {stats['total_points']:8d} | {stats.get('valid_points',0):8d} | "
              f"{stats.get('nan_points',0):6d} | {stats.get('zero_points',0):6d} | "
              f"{stats['min_distance']:8.3f} | {stats['max_distance']:8.3f} | "
              f"{stats['mean_distance']:8.3f} | {latency_ms:7.1f}")

        if stats['total_points'] > 0 and stats.get('valid_points', 0) == 0:
            print(f"  ⚠️  所有点无效! fields={stats['fields']}, "
                  f"point_step={stats['point_step']}, data_len={stats['data_length']}")

    node.create_subscription(PointCloud2, topic, callback, 10)

    def _done():
        if t_first[0] is None and (time.time() - t_start) > timeout:
            return True
        return bool(max_frames and frame_count[0] >= max_frames)

    _spin_with_timeout(node, _done, timeout + 5)

    if t_first[0] is None:
        print(f"\n❌ 超时 {timeout}s，未收到任何消息！检查 topic 是否存在。")

    elapsed = time.time() - t_start
    avg_hz = frame_count[0] / elapsed if elapsed > 0 else 0
    print(f"\n{'='*70}")
    print(f"📊 PointCloud2 汇总: 共 {frame_count[0]} 帧, {elapsed:.1f}s, 平均 {avg_hz:.1f} Hz")
    print(f"{'='*70}\n")

    node.destroy_node()
    rclpy.shutdown()


def _new_frame_state():
    """创建一帧的统计状态 dict（混合类型，不用 defaultdict(int)）"""
    return {
        'sub_packets': 0,
        'pc_packets': 0,
        'crc_fail': 0,
        'decode_fail': 0,
        'valid_dist': 0,
        'zero_dist': 0,
        'near_zero': 0,
        'total_channels': 0,
        'empty_msgs': 0,
        'min_dist': float('inf'),
        'max_dist': 0.0,
        'max_ref': 0,
        'sample_raw': [],   # list[dict]
    }


def _spin_with_timeout(node, stop_fn, timeout):
    """
    使用 MultiThreadedExecutor spin，规避 zenoh rmw 在 spin_once 中的 core dump。
    stop_fn() 返回 True 时退出。
    """
    import rclpy
    from rclpy.executors import MultiThreadedExecutor

    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    t_start = time.time()
    while _running and not stop_fn():
        executor.spin_once(timeout_sec=0.5)
        if time.time() - t_start > timeout:
            break
    try:
        executor.shutdown()
    except Exception:
        pass


def check_raw_packets_topic(topic, max_frames, timeout):
    """订阅原始 packets topic 并逐帧解码诊断"""
    import rclpy
    from rclpy.node import Node

    try:
        from vanjee_lidar_msg.msg import VanjeelidarPacket
        msg_type = VanjeelidarPacket
        msg_type_name = "VanjeelidarPacket"
    except ImportError:
        print("⚠️  无法导入 VanjeelidarPacket, 尝试使用通用消息类型...")
        try:
            from std_msgs.msg import UInt8MultiArray
            msg_type = UInt8MultiArray
            msg_type_name = "UInt8MultiArray"
        except ImportError:
            print("❌ 无法导入消息类型，请确保在 ROS2 环境中运行")
            return

    rclpy.init()
    node = Node('lidar_raw_checker')

    msg_count = [0]
    frame_count = [0]
    prev_azimuth = [-1]
    cur_frame = [_new_frame_state()]
    t_start = time.time()
    first_msg_time = [None]

    print(f"\n{'='*70}")
    print(f"📡 订阅原始数据包: {topic}  (msg_type={msg_type_name})")
    print(f"{'='*70}")
    print(f"{'帧#':>5} | {'子包数':>7} | {'点云包':>7} | {'CRC失败':>7} | {'有效距离':>8} | "
          f"{'零距离':>7} | {'最小距离m':>9} | {'最大距离m':>9} | {'最大反射':>8}")
    print('-' * 105)

    def flush_frame():
        s = cur_frame[0]
        if s['pc_packets'] == 0:
            return
        frame_count[0] += 1
        min_d = s['min_dist'] if s['min_dist'] != float('inf') else 0.0
        max_d = s['max_dist']
        print(f"{frame_count[0]:5d} | {s['sub_packets']:7d} | {s['pc_packets']:7d} | "
              f"{s['crc_fail']:7d} | {s['valid_dist']:8d} | {s['zero_dist']:7d} | "
              f"{min_d:9.3f} | {max_d:9.3f} | {s['max_ref']:8d}")
        if s['valid_dist'] == 0 and s['pc_packets'] > 0:
            print(f"  ⚠️  帧内所有距离为0! 共 {s['pc_packets']} 个点云包, "
                  f"{s['total_channels']} 个通道")
            if s['sample_raw']:
                print(f"  📝 采样原始数据 (前3个包的前4通道):")
                for smp in s['sample_raw'][:3]:
                    print(f"      azimuth={smp['azimuth']:.1f}°, "
                          f"dist_raw & reflectivity: {smp['channels']}")
        cur_frame[0] = _new_frame_state()

    def callback(msg):
        if not _running:
            return
        msg_count[0] += 1
        if first_msg_time[0] is None:
            first_msg_time[0] = time.time()

        # rclpy 已反序列化 —— msg.data 就是 uint8[] 原始载荷，直接转 bytes
        raw_data = bytes(msg.data)

        if len(raw_data) == 0:
            cur_frame[0]['empty_msgs'] += 1
            if msg_count[0] <= 3:
                print(f"  ⚠️  消息{msg_count[0]}: data 字段为空!")
            return

        sub_packets = extract_sub_packets(raw_data)
        cur_frame[0]['sub_packets'] += len(sub_packets)

        for pkt_type, pkt_data in sub_packets:
            if pkt_type != 'pointcloud':
                continue
            result = decode_pointcloud_packet_diag(pkt_data)
            if result is None:
                cur_frame[0]['decode_fail'] += 1
                continue
            if not result['crc_ok']:
                cur_frame[0]['crc_fail'] += 1
                continue

            cur_frame[0]['pc_packets'] += 1
            azimuth = result['azimuth']

            # 帧边界检测
            if prev_azimuth[0] >= 0:
                curr_trans = (azimuth + 60) % 36000
                prev_trans = (prev_azimuth[0] + 60) % 36000
                if curr_trans < prev_trans:
                    flush_frame()
                    if max_frames and frame_count[0] >= max_frames:
                        return
            prev_azimuth[0] = azimuth

            # 通道距离统计
            for ch_info in result['channels']:
                cur_frame[0]['total_channels'] += 1
                dist_m = ch_info['distance_m']
                dist_raw = ch_info['dist_raw']
                if dist_raw == 0:
                    cur_frame[0]['zero_dist'] += 1
                elif dist_m >= 0.01:
                    cur_frame[0]['valid_dist'] += 1
                    if dist_m < cur_frame[0]['min_dist']:
                        cur_frame[0]['min_dist'] = dist_m
                    if dist_m > cur_frame[0]['max_dist']:
                        cur_frame[0]['max_dist'] = dist_m
                else:
                    cur_frame[0]['near_zero'] += 1
                ref = ch_info['reflectivity']
                if ref > cur_frame[0]['max_ref']:
                    cur_frame[0]['max_ref'] = ref

            # 保存原始采样（每帧前3个包）
            if cur_frame[0]['pc_packets'] <= 3:
                cur_frame[0]['sample_raw'].append({
                    'azimuth': result['azimuth_deg'],
                    'channels': [(c['dist_raw'], c['reflectivity'])
                                 for c in result['channels'][:4]]
                })

    node.create_subscription(msg_type, topic, callback, 10)

    def _done():
        if first_msg_time[0] is None and (time.time() - t_start) > timeout:
            return True
        return bool(max_frames and frame_count[0] >= max_frames)

    _spin_with_timeout(node, _done, timeout + 5)

    if first_msg_time[0] is None:
        print(f"\n❌ 超时 {timeout}s，未收到任何消息！")
    else:
        # 输出最后一帧
        if cur_frame[0]['pc_packets'] > 0:
            flush_frame()

    elapsed = time.time() - t_start
    avg_hz = frame_count[0] / elapsed if elapsed > 0 else 0
    print(f"\n{'='*70}")
    print(f"📊 原始包汇总: 共 {msg_count[0]} 条消息, {frame_count[0]} 帧, "
          f"{elapsed:.1f}s, 平均 {avg_hz:.1f} Hz")
    print(f"{'='*70}\n")

    node.destroy_node()
    rclpy.shutdown()


def check_both_topics(points_topic, packets_topic, max_frames, timeout):
    """同时订阅两个 topic 进行交叉诊断"""
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import PointCloud2

    try:
        from vanjee_lidar_msg.msg import VanjeelidarPacket
        packet_msg_type = VanjeelidarPacket
    except ImportError:
        from std_msgs.msg import UInt8MultiArray
        packet_msg_type = UInt8MultiArray

    rclpy.init()
    node = Node('lidar_both_checker')

    pc2_info = {'count': 0, 'total_pts': 0, 'valid_pts': 0, 'nan_pts': 0}
    raw_info = {'count': 0, 'pc_packets': 0, 'valid_dist': 0, 'zero_dist': 0,
                'crc_fail': 0, 'empty_data': 0, 'data_len_samples': []}
    t_start = time.time()

    print(f"\n{'='*70}")
    print(f"🔍 双 Topic 交叉诊断")
    print(f"   PointCloud2:  {points_topic}")
    print(f"   Raw Packets:  {packets_topic}")
    print(f"{'='*70}\n")

    def pc2_callback(msg):
        pc2_info['count'] += 1
        stats = parse_pointcloud2(msg)
        pc2_info['total_pts'] += stats['total_points']
        pc2_info['valid_pts'] += stats.get('valid_points', 0)
        pc2_info['nan_pts'] += stats.get('nan_points', 0)
        if pc2_info['count'] <= 5:
            print(f"  [PointCloud2] 帧{pc2_info['count']}: total={stats['total_points']}, "
                  f"valid={stats.get('valid_points', 0)}, nan={stats.get('nan_points', 0)}, "
                  f"fields={stats['fields']}, point_step={stats['point_step']}, "
                  f"data_len={stats['data_length']}")

    def raw_callback(msg):
        raw_info['count'] += 1
        # rclpy 已反序列化，msg.data 就是 uint8[] 原始载荷
        raw_data = bytes(msg.data)

        if len(raw_data) == 0:
            raw_info['empty_data'] += 1
            if raw_info['count'] <= 5:
                print(f"  [RawPacket] 消息{raw_info['count']}: data 字段为空!")
            return

        if len(raw_info['data_len_samples']) < 10:
            raw_info['data_len_samples'].append(len(raw_data))

        sub_pkts = extract_sub_packets(raw_data)
        for pkt_type, pkt_data in sub_pkts:
            if pkt_type == 'pointcloud':
                result = decode_pointcloud_packet_diag(pkt_data)
                if result is None:
                    continue
                if not result['crc_ok']:
                    raw_info['crc_fail'] += 1
                    continue
                raw_info['pc_packets'] += 1
                for ch in result['channels']:
                    if ch['dist_raw'] == 0:
                        raw_info['zero_dist'] += 1
                    elif ch['distance_m'] >= 0.01:
                        raw_info['valid_dist'] += 1

        if raw_info['count'] <= 3:
            print(f"  [RawPacket] 消息{raw_info['count']}: data_len={len(raw_data)}, "
                  f"sub_packets={len(sub_pkts)}, types={[t for t, _ in sub_pkts]}")
            for pkt_type, pkt_data in sub_pkts[:2]:
                if pkt_type == 'pointcloud':
                    r = decode_pointcloud_packet_diag(pkt_data)
                    if r and r['crc_ok']:
                        dists = [c['dist_raw'] for c in r['channels']]
                        refs = [c['reflectivity'] for c in r['channels']]
                        print(f"    azimuth={r['azimuth_deg']:.2f}°  "
                              f"dist_raw={dists}  ref={refs}")

    node.create_subscription(PointCloud2, points_topic, pc2_callback, 10)
    try:
        node.create_subscription(packet_msg_type, packets_topic, raw_callback, 10)
    except Exception as e:
        print(f"⚠️  无法订阅 {packets_topic}: {e}")

    sample_target = (max_frames or 10) * 5

    def _done():
        total = pc2_info['count'] + raw_info['count']
        if total >= sample_target:
            return True
        if total == 0 and (time.time() - t_start) > timeout:
            return True
        return False

    _spin_with_timeout(node, _done, timeout + 5)

    elapsed = time.time() - t_start
    if pc2_info['count'] == 0 and raw_info['count'] == 0:
        print(f"\n❌ 超时 {timeout}s，两个 topic 都未收到消息！")

    # 汇总
    print(f"\n{'='*70}")
    print(f"📊 交叉诊断汇总 (耗时 {elapsed:.1f}s)")
    print(f"{'='*70}")
    print(f"\n🔵 PointCloud2 ({points_topic}):")
    print(f"   收到帧数:     {pc2_info['count']}")
    print(f"   总点数:       {pc2_info['total_pts']}")
    print(f"   有效点数:     {pc2_info['valid_pts']}")
    print(f"   NaN 点数:     {pc2_info['nan_pts']}")
    if pc2_info['count'] > 0:
        print(f"   平均每帧点数: {pc2_info['total_pts'] / pc2_info['count']:.0f} "
              f"(有效: {pc2_info['valid_pts'] / pc2_info['count']:.0f})")

    print(f"\n🟠 Raw Packets ({packets_topic}):")
    print(f"   收到消息数:   {raw_info['count']}")
    print(f"   空数据消息:   {raw_info['empty_data']}")
    print(f"   点云子包数:   {raw_info['pc_packets']}")
    print(f"   CRC 失败:     {raw_info['crc_fail']}")
    print(f"   有效距离通道: {raw_info['valid_dist']}")
    print(f"   零距离通道:   {raw_info['zero_dist']}")
    if raw_info['data_len_samples']:
        print(f"   数据长度采样: {raw_info['data_len_samples']}")

    # 诊断建议
    print(f"\n{'='*70}")
    print(f"🔍 诊断分析")
    print(f"{'='*70}")

    if pc2_info['count'] == 0 and raw_info['count'] == 0:
        print("❌ 两个 topic 都没有数据 → LiDAR 驱动可能未运行")
        print("   检查: ros2 topic list | grep lidar")
    elif raw_info['count'] > 0 and raw_info['empty_data'] == raw_info['count']:
        print("❌ 原始包全是空数据 → LiDAR 硬件未连接或串口异常")
        print("   检查: ls -la /dev/ttyS1")
        print("   检查: LiDAR 供电和线缆连接")
    elif raw_info['pc_packets'] > 0 and raw_info['valid_dist'] == 0:
        print("⚠️  原始包 CRC 通过但所有距离为 0 → LiDAR 激光/马达异常")
        print("   可能原因:")
        print("   1. LiDAR 电机未旋转 (听声音/观察转动)")
        print("   2. LiDAR 激光发射器故障")
        print("   3. 光路被遮挡物封闭")
        print("   4. LiDAR 处于待机模式，需要发送启动指令")
    elif pc2_info['count'] > 0 and pc2_info['valid_pts'] == 0 and pc2_info['total_pts'] > 0:
        print("⚠️  PointCloud2 有点但全是 NaN/零值 → 驱动解码异常")
        print("   检查: wait_for_difop=true 但角度表可能未下发")
        print("   检查: /app/lidar/param/Vanjee_722z_VA.csv 是否存在")
    elif pc2_info['count'] > 0 and pc2_info['valid_pts'] > 0:
        avg_valid = pc2_info['valid_pts'] / pc2_info['count']
        print(f"✅ LiDAR 数据正常! 平均每帧 {avg_valid:.0f} 个有效点")
        if avg_valid < 1000:
            print(f"   ⚠️  每帧有效点数偏少，请检查周围环境或遮挡情况")
    else:
        print("ℹ️  样本数不足，请增加 --max-frames 或延长等待时间")

    print()
    node.destroy_node()
    rclpy.shutdown()


# ============================================================
# 简易网络检查 (不依赖 ROS, 直接 UDP 抓包)
# ============================================================
def check_udp_raw(host='0.0.0.0', port=3001, duration=5):
    """直接 UDP 监听 LiDAR 数据 (绕过 ROS, 适用于串口模式时跳过)"""
    import socket

    print(f"\n{'='*70}")
    print(f"🔌 UDP 直接监听: {host}:{port} (持续 {duration}s)")
    print(f"{'='*70}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(1.0)

    try:
        sock.bind((host, port))
    except Exception as e:
        print(f"❌ 绑定 {host}:{port} 失败: {e}")
        return

    pkt_count = 0
    total_bytes = 0
    t_start = time.time()

    while _running and (time.time() - t_start) < duration:
        try:
            data, addr = sock.recvfrom(65536)
            pkt_count += 1
            total_bytes += len(data)
            if pkt_count <= 3:
                print(f"  包{pkt_count}: {len(data)} bytes from {addr}, hex[:32]={data[:32].hex()}")
        except socket.timeout:
            continue

    sock.close()
    elapsed = time.time() - t_start
    print(f"\n📊 UDP 汇总: {pkt_count} 包, {total_bytes} 字节, {elapsed:.1f}s")
    if pkt_count == 0:
        print("❌ 未收到任何 UDP 数据 → LiDAR 未通过 UDP 发送数据")
        print("   注意: 你的配置使用 connect_type=3 (串口模式), UDP 无数据是正常的")
    print()


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description='LiDAR 实时点云诊断工具 (在 S100 上运行)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 检查 PointCloud2 (默认)
  python3 lidar_realtime_check.py

  # 检查原始数据包
  python3 lidar_realtime_check.py --mode raw

  # 双 topic 交叉诊断 (推荐)
  python3 lidar_realtime_check.py --mode both

  # 指定 topic
  python3 lidar_realtime_check.py --topic /vanjee_722z --mode pc2

  # UDP 直接抓包 (不依赖 ROS)
  python3 lidar_realtime_check.py --mode udp
        ''')

    parser.add_argument('--mode', choices=['pc2', 'raw', 'both', 'udp'],
                        default='both',
                        help='检查模式: pc2=PointCloud2, raw=原始包, both=双topic, udp=UDP直接抓包')
    parser.add_argument('--topic', type=str, default=None,
                        help='自定义 topic (默认: pc2=/lidar_points, raw=/lidar_packets)')
    parser.add_argument('--points-topic', type=str, default='/lidar_points',
                        help='PointCloud2 topic (默认: /lidar_points)')
    parser.add_argument('--packets-topic', type=str, default='/lidar_packets',
                        help='原始包 topic (默认: /lidar_packets)')
    parser.add_argument('--max-frames', type=int, default=10,
                        help='最多检查帧数 (默认: 10)')
    parser.add_argument('--timeout', type=int, default=15,
                        help='超时时间秒 (默认: 15)')
    parser.add_argument('--udp-port', type=int, default=3001,
                        help='UDP 监听端口 (默认: 3001)')

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════╗
║  万集 WLR-722Z LiDAR 实时诊断工具                    ║
║  模式: {args.mode:<46s} ║
╚══════════════════════════════════════════════════════╝
""")

    if args.mode == 'pc2':
        topic = args.topic or args.points_topic
        check_pointcloud2_topic(topic, args.max_frames, args.timeout)

    elif args.mode == 'raw':
        topic = args.topic or args.packets_topic
        check_raw_packets_topic(topic, args.max_frames, args.timeout)

    elif args.mode == 'both':
        check_both_topics(args.points_topic, args.packets_topic,
                          args.max_frames, args.timeout)

    elif args.mode == 'udp':
        check_udp_raw(port=args.udp_port, duration=args.timeout)


if __name__ == '__main__':
    main()
