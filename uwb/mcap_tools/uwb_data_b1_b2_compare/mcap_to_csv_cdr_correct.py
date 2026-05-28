#!/usr/bin/env python3
"""
严格按CDR规则解析 UWB 消息：
std_msgs/Header header
uint8 rssi_len
float32 pitch
float32 angle
float32 distance
int8[] rssi
float32 angle_filtered
float32 distance_filtered
uint8 pos_confidence
bool has_living_body
bool has_head_touch

并根据文件名自动处理角度范围：
- 007 版本：angle 0..360（顺时针）
- 062 版本：angle 0..180，然后 -180..0（顺时针）；输出统一规范为 0..360
"""

import argparse
import struct
from pathlib import Path
import pandas as pd
import numpy as np
from mcap.reader import make_reader

# ------------- CDR 解析辅助函数 -------------

def align(offset: int, align_bytes: int) -> int:
    return offset + ((align_bytes - (offset % align_bytes)) % align_bytes)


def read_uint8(buf: bytes, offset: int):
    return struct.unpack_from('<B', buf, offset)[0], offset + 1


def read_bool(buf: bytes, offset: int):
    val = struct.unpack_from('<B', buf, offset)[0]
    return bool(val), offset + 1


def read_int32(buf: bytes, offset: int):
    offset = align(offset, 4)
    return struct.unpack_from('<i', buf, offset)[0], offset + 4


def read_uint32(buf: bytes, offset: int):
    offset = align(offset, 4)
    return struct.unpack_from('<I', buf, offset)[0], offset + 4


def read_float32(buf: bytes, offset: int):
    offset = align(offset, 4)
    return struct.unpack_from('<f', buf, offset)[0], offset + 4


def read_string(buf: bytes, offset: int):
    length, offset = read_uint32(buf, offset)
    s = buf[offset:offset+length].decode('utf-8', errors='ignore')
    return s, offset + length

# ------------- 解析 header -------------

def parse_header(buf: bytes, offset: int):
    # builtin_interfaces/Time: int32 sec, uint32 nanosec
    sec, offset = read_int32(buf, offset)
    nsec, offset = read_uint32(buf, offset)
    # std_msgs/Header: string frame_id
    frame_id, offset = read_string(buf, offset)
    return {
        'stamp_sec': int(sec),
        'stamp_nsec': int(nsec),
        'frame_id': frame_id,
        'timestamp_sec': float(sec) + float(nsec) / 1e9,
    }, offset

# ------------- 主解析函数 -------------

def parse_uwb_message_cdr(data: bytes):
    try:
        if len(data) < 4:
            return None
        # 跳过 CDR 封装头 4 字节
        offset = 4

        # 1) header
        header, offset = parse_header(data, offset)

        # 2) rssi_len (uint8)
        rssi_len, offset = read_uint8(data, offset)
        
        # 3) 对齐并读取 float32 字段
        pitch, offset = read_float32(data, offset)
        angle, offset = read_float32(data, offset)
        distance, offset = read_float32(data, offset)

        # 4) rssi: sequence<int8>
        # CDR: 先对齐到4字节，读取 uint32 长度，再读取对应字节数
        rssi_seq_len, offset = read_uint32(data, offset)
        rssi_bytes = data[offset:offset + rssi_seq_len]
        rssi = list(struct.unpack('<' + 'b' * rssi_seq_len, rssi_bytes)) if rssi_seq_len > 0 else []
        offset += rssi_seq_len

        # 5) angle_filtered, distance_filtered
        angle_filtered, offset = read_float32(data, offset)
        distance_filtered, offset = read_float32(data, offset)

        # 6) pos_confidence (uint8), has_living_body (bool), has_head_touch (bool)
        pos_confidence, offset = read_uint8(data, offset)
        has_living_body, offset = read_bool(data, offset)
        has_head_touch, offset = read_bool(data, offset)

        result = {
            **header,
            'rssi_len': int(rssi_len),
            'pitch': float(pitch),
            'angle': float(angle),
            'distance': float(distance),
            'rssi': rssi,
            'angle_filtered': float(angle_filtered),
            'distance_filtered': float(distance_filtered),
            'pos_confidence': int(pos_confidence),
            'has_living_body': bool(has_living_body),
            'has_head_touch': bool(has_head_touch),
        }

        return result
    except Exception as e:
        # 返回 None 让上层跳过异常消息，但打印一次错误便于调试
        print(f"解析错误: {e}")
        return None

# ------------- 角度规范化 -------------

def normalize_angle_for_version(angle_deg: float, version: str) -> float:
    """将角度统一到 0..360 顺时针表示：
    - 007: 原始即 0..360
    - 062: 输入 0..180 与 -180..0，转换到 0..360（负数加360）
    """
    if version == '062':
        if angle_deg < 0:
            angle_deg = 360.0 + angle_deg
    # 归一化到 0..360
    angle_deg = angle_deg % 360.0
    return angle_deg


def detect_version_from_path(path: Path) -> str:
    s = str(path).lower()
    if 'close_62' in s or '062' in s:
        return '062'
    return '007'

# ------------- MCAP 转 DataFrame -------------

def mcap_to_dataframe(mcap_file: Path, topic_name: str = '/uwb/data'):
    data_list = []
    message_count = 0
    version = detect_version_from_path(mcap_file)

    print(f"正在处理MCAP文件: {mcap_file} (版本: {version})")

    with open(mcap_file, 'rb') as f:
        reader = make_reader(f)
        try:
            iter_msgs = reader.iter_messages(topics=[topic_name])
        except Exception:
            # 如果指定topic失败，遍历全部
            iter_msgs = reader.iter_messages()

        for schema, channel, message in iter_msgs:
            message_count += 1
            parsed = parse_uwb_message_cdr(message.data)
            if not parsed:
                continue

            # 角度统一
            parsed['angle'] = normalize_angle_for_version(parsed['angle'], version)
            parsed['angle_filtered'] = normalize_angle_for_version(parsed['angle_filtered'], version)

            # 计算坐标（基于统一角度与距离）
            ang_rad = np.radians(parsed['angle'])
            parsed['raw_x_m'] = parsed['distance'] * np.cos(ang_rad)
            parsed['raw_y_m'] = parsed['distance'] * np.sin(ang_rad)

            ang_f_rad = np.radians(parsed['angle_filtered'])
            parsed['filtered_x_m'] = parsed['distance_filtered'] * np.cos(ang_f_rad)
            parsed['filtered_y_m'] = parsed['distance_filtered'] * np.sin(ang_f_rad)

            # 额外元数据
            parsed['message_count'] = message_count
            parsed['channel_topic'] = channel.topic if channel else ''

            data_list.append(parsed)

            if message_count % 1000 == 0:
                print(f"已处理 {message_count} 条消息...")

    print(f"总共处理了 {message_count} 条消息")

    if not data_list:
        print("警告: 没有解析到有效数据")
        return pd.DataFrame()

    df = pd.DataFrame(data_list)

    # 数据质量报告
    print("\n数据质量报告:")
    print(f"距离范围: {df['distance'].min():.3f} - {df['distance'].max():.3f} m")
    print(f"角度范围(统一后): {df['angle'].min():.3f} - {df['angle'].max():.3f} °")
    if 'angle_filtered' in df.columns:
        print(f"滤波角度范围(统一后): {df['angle_filtered'].min():.3f} - {df['angle_filtered'].max():.3f} °")
        diff = np.abs(df['angle'] - df['angle_filtered'])
        diff = np.minimum(diff, 360.0 - diff)  # 处理环绕
        print(f"角度差(原 vs 滤波): 均值 {diff.mean():.2f}°, 标准差 {diff.std():.2f}°")

    return df

# ------------- 主程序 -------------

def main():
    parser = argparse.ArgumentParser(description='按CDR严格解析UWB MCAP并导出CSV')
    parser.add_argument('mcap_file', help='输入MCAP文件路径')
    parser.add_argument('-o', '--output', help='输出CSV文件路径')
    parser.add_argument('-t', '--topic', default='/uwb/data', help='要解析的topic名称')

    args = parser.parse_args()
    mcap_path = Path(args.mcap_file)
    if not mcap_path.exists():
        print(f"错误: MCAP文件不存在: {mcap_path}")
        return

    df = mcap_to_dataframe(mcap_path, args.topic)
    if df.empty:
        print("错误: 未解析到有效数据")
        return

    # 输出路径
    if args.output:
        out = Path(args.output)
    else:
        out = mcap_path.with_suffix('.csv')

    df.to_csv(out, index=False)
    print(f"\n✓ CSV文件已保存: {out}")
    print(f"数据形状: {df.shape}")

if __name__ == '__main__':
    main()