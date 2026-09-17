#!/usr/bin/env python3
"""从MCAP提取azimuth和sequence_num序列，检测异常"""
from sensor_tools.lidar import iter_packet_messages
import argparse
import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcap.reader import make_reader
from src.core.decoder import VanjeeDecoder, crc32_mpeg2_padded

def extract_packets(mcap_file, topic):
    """提取所有点云包的 azimuth 和 sequence_num"""
    records = []  # (msg_idx, azimuth, sequence_num)
    
    msg_idx = 0
    crc_failures = 0
    for message in iter_packet_messages(mcap_file, topic):
        raw_data = message.data
        data_bytes = raw_data
        if data_bytes is None:
            msg_idx += 1
            continue

        sub_packets = VanjeeDecoder.extract_sub_packets(data_bytes)
        for pkt_type, pkt_data in sub_packets:
            if pkt_type == 'pointcloud' and len(pkt_data) == 80:
                if crc32_mpeg2_padded(pkt_data, 76) != struct.unpack_from('<I', pkt_data, 76)[0]:
                    crc_failures += 1
                    continue  # Corrupted sequence bytes are not evidence of missing packets.
                # azimuth at offset 16 (uint16)
                azimuth = struct.unpack_from('<H', pkt_data, 16)[0] % 36000
                # sequence_num at offset 74 (uint16) based on C++ struct layout:
                # head(2) + protocol(2) + diag(1) + data_type(1) + datetime(6) + timestamp(4) = 16
                # azimuth(2) + channels(16*3=48) + dirty_degree(4) + lidar_state(1) + reserved_id(1) + reserved_info(2) + sequence_num(2) + crc(4) = 80-16=64
                # So sequence_num is at 16 + 2 + 48 + 4 + 1 + 1 + 2 = 74
                sequence_num = struct.unpack_from('<H', pkt_data, 74)[0]
                records.append((msg_idx, azimuth, sequence_num))

        msg_idx += 1
    print(f"CRC-invalid packets excluded: {crc_failures}")
    return records

def analyze(records, resolution=60):
    print(f"总包数: {len(records)}")
    
    # 检查 sequence 不连续
    seq_gaps = []
    azimuth_anomalies = []
    
    for i in range(1, len(records)):
        _, prev_az, prev_seq = records[i-1]
        _, curr_az, curr_seq = records[i]
        
        seq_diff = (curr_seq + 65536 - prev_seq) % 65536
        if seq_diff != 1:
            seq_gaps.append((i, prev_seq, curr_seq, seq_diff, prev_az, curr_az))
        
        # 检测 "1/599" 条件: 连续两包azimuth都在高角度区间(接近360°)
        curr_trans = (curr_az + resolution) % 36000
        prev_trans = (prev_az + resolution) % 36000
        if curr_trans < resolution and prev_trans < resolution:
            azimuth_anomalies.append((i, prev_az, curr_az, prev_seq, curr_seq))
    
    print(f"\n=== Sequence 不连续 (可能丢包、重复、乱序或录制缺失) ===")
    print(f"总数: {len(seq_gaps)}")
    for i, ps, cs, diff, paz, caz in seq_gaps[:20]:
        kind = "duplicate" if diff == 0 else f"forward_missing_estimate={diff-1}" if diff < 32768 else "backward/reset"
        print(f"  包[{i}]: seq {ps}->{cs} ({kind}), azimuth {paz}->{caz}")
    
    print(f"\n=== 连续两包都在360°附近 (1/599条件) ===")
    print(f"总数: {len(azimuth_anomalies)}")
    for i, paz, caz, ps, cs in azimuth_anomalies[:20]:
        print(f"  包[{i}]: azimuth {paz}->{caz}, seq {ps}->{cs}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Check LiDAR azimuth and sequence continuity from MCAP")
    parser.add_argument("mcap", help="Input MCAP file")
    parser.add_argument("--topic", default="/lidar_packets", help="LiDAR packet topic")
    parser.add_argument("--resolution", type=int, choices=[60, 120], default=60, help="Angular increment, hundredths of a degree")
    args = parser.parse_args()

    print("正在解析MCAP...")
    records = extract_packets(args.mcap, args.topic)
    if not records:
        raise SystemExit("error: no point-cloud packets")
    analyze(records, args.resolution)
