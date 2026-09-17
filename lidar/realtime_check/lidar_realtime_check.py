#!/usr/bin/env python3
"""Bounded passive LiDAR diagnosis from live Aorta or ROS/Aorta MCAP.

Reports data evidence, not a blanket hardware-health verdict. UDP mode binds an
unused port exclusively and must never compete with the production receiver.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time

from sensor_tools import aorta
from sensor_tools.lidar import PacketStream
from sensor_tools.mcap import iter_records, source_time_ns
from sensor_tools.pointcloud import statistics as cloud_statistics

DISTANCE_RES = 0.002

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



def inspect(path, points_topic, packets_topic, mode, max_frames):
    topics = ([points_topic] if mode == 'pc2' else [packets_topic] if mode == 'raw' else [points_topic, packets_topic])
    summary = dict(mode=mode, pointcloud_frames=0, raw_messages=0, raw_point_packets=0,
                   crc_failures=0, empty_raw_messages=0, raw_valid_channels=0, raw_zero_channels=0,
                   pointcloud_valid_points=0, sequence_duplicates=0, sequence_discontinuities=0,
                   cross_frame_time_regressions=0, within_frame_time_regressions=0)
    previous_last = previous_seq = None
    stream = PacketStream()
    frames = []
    for record in iter_records(path, topics):
        data = record.data
        if 'point_stride' in data or 'point_step' in data:
            if summary['pointcloud_frames'] >= max_frames:
                continue
            stats = cloud_statistics(data)
            stats.update(source_time_ns=source_time_ns(data, record.publish_time_ns), topic=record.topic)
            first, last = stats.get('first_point_timestamp'), stats.get('last_point_timestamp')
            if first is not None and previous_last is not None and first < previous_last:
                summary['cross_frame_time_regressions'] += 1
            previous_last = last
            summary['within_frame_time_regressions'] += stats.get('within_frame_time_regressions', 0)
            summary['pointcloud_frames'] += 1
            summary['pointcloud_valid_points'] += stats['valid_points']
            frames.append(stats)
        else:
            summary['raw_messages'] += 1
            payload = bytes(data.get('data', []))
            packets = stream.feed(payload)
            if not payload:
                summary['empty_raw_messages'] += 1
            for kind, packet in packets:
                if kind != 'pointcloud':
                    continue
                diagnostic = decode_pointcloud_packet_diag(packet)
                if not diagnostic['crc_ok']:
                    summary['crc_failures'] += 1
                    continue
                summary['raw_point_packets'] += 1
                sequence = struct.unpack_from('<H', packet, 74)[0]
                if previous_seq is not None:
                    delta = (sequence - previous_seq) & 0xffff
                    summary['sequence_duplicates'] += delta == 0
                    summary['sequence_discontinuities'] += delta not in (0, 1)
                previous_seq = sequence
                for channel in diagnostic['channels']:
                    summary['raw_zero_channels' if channel['dist_raw'] == 0 else 'raw_valid_channels'] += 1
    summary['frames'] = frames
    summary['trailing_partial_packet_bytes'] = len(stream.pending)
    summary['unframed_bytes'] = stream.discarded_bytes
    missing = ((mode in ('pc2', 'both') and summary['pointcloud_frames'] == 0) or
               (mode in ('raw', 'both') and summary['raw_point_packets'] == 0))
    bad = (summary['crc_failures'] or summary['cross_frame_time_regressions'] or
           summary['within_frame_time_regressions'] or
           (summary['pointcloud_frames'] and not summary['pointcloud_valid_points']))
    summary['status'] = 'FAIL' if bad else 'INCOMPLETE' if missing else 'PASS'
    summary['scope'] = 'sample decoding and data presence; sequence gaps do not prove UDP loss'
    return summary


def check_udp_raw(host='0.0.0.0', port=3001, duration=5):
    count = total = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        # No SO_REUSEADDR: fail if a production receiver owns this port.
        connection.bind((host, port))
        connection.settimeout(min(1.0, duration))
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            try:
                payload, _ = connection.recvfrom(65536)
                count += 1
                total += len(payload)
            except socket.timeout:
                pass
    return {'packets': count, 'bytes': total, 'status': 'PASS' if count else 'INCOMPLETE',
            'scope': 'UDP reception only; no traffic does not prove hardware failure'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['pc2', 'raw', 'both', 'udp'], default='both')
    parser.add_argument('--mcap', type=Path, help='offline input; omit for bounded Aorta capture')
    parser.add_argument('--topic', help='override topic for pc2/raw mode')
    parser.add_argument('--points-topic', default='/lidar_points')
    parser.add_argument('--packets-topic', default='/lidar_packets')
    parser.add_argument('--max-frames', type=int, default=10, help='maximum decoded pointcloud frames; all raw packets are checked')
    parser.add_argument('--timeout', type=int, default=15, help='live capture duration in seconds')
    parser.add_argument('--udp-port', type=int, default=3001)
    parser.add_argument('--output', type=Path, help='JSON report')
    args = parser.parse_args()
    if args.max_frames <= 0 or args.timeout <= 0:
        parser.error('max-frames and timeout must be positive')
    if args.topic:
        if args.mode == 'pc2':
            args.points_topic = args.topic
        elif args.mode == 'raw':
            args.packets_topic = args.topic
        else:
            parser.error('--topic requires pc2 or raw mode')
    try:
        if args.mode == 'udp':
            if args.mcap:
                parser.error('--mcap cannot be combined with UDP mode')
            result = check_udp_raw(port=args.udp_port, duration=args.timeout)
        else:
            with tempfile.TemporaryDirectory(prefix='lidar-check-') as directory:
                path = args.mcap or Path(directory) / 'lidar.mcap'
                if not args.mcap:
                    topics = [args.points_topic] if args.mode == 'pc2' else [args.packets_topic] if args.mode == 'raw' else [args.points_topic, args.packets_topic]
                    aorta.capture(path, topics, args.timeout)
                result = inspect(path, args.points_topic, args.packets_topic, args.mode, args.max_frames)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + '\n')
        return {'PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2}[result['status']]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f'error: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
