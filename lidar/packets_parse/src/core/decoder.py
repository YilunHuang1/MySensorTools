"""
万集 WLR-722Z 数据包解码模块

协议参考: vanjee_driver/decoder/wlr722z
"""

import struct
import math
import numpy as np


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


class VanjeeDecoder:
    """万集雷达解码器"""
    
    # 常量定义
    DISTANCE_RES = 0.002  # 米/LSB
    DISTANCE_MIN = 0.01   # 米
    DISTANCE_MAX = 100.0  # 米
    
    # 光心偏移参数 (来自 C++ 源码)
    OPTCENT_2_LIDAR_ARG = 21570   # 毫度
    OPTCENT_2_LIDAR_L = 2.067e-2  # 米
    OPTCENT_2_LIDAR_Z = 7.95e-3   # 米
    
    # 三角函数查找表 (初始化时计算)
    _cos_table = None
    _sin_table = None
    
    @classmethod
    def init_trig_tables(cls):
        """初始化三角函数查找表"""
        if cls._cos_table is not None:
            return
        angles_rad = np.arange(360000) * math.pi / 180000.0
        cls._cos_table = np.cos(angles_rad).astype(np.float32)
        cls._sin_table = np.sin(angles_rad).astype(np.float32)
    
    @classmethod
    def _cos(cls, angle_millideg):
        """余弦 (输入单位: 毫度)"""
        return cls._cos_table[angle_millideg % 360000]
    
    @classmethod
    def _sin(cls, angle_millideg):
        """正弦 (输入单位: 毫度)"""
        return cls._sin_table[angle_millideg % 360000]
    
    @staticmethod
    def parse_mcap_message(raw_data):
        """
        从 CDR 序列化的 VanjeelidarPacket 消息中提取 data 字段
        
        Args:
            raw_data: 原始消息字节
            
        Returns:
            bytes: 提取的数据字段，若失败返回 None
        """
        if len(raw_data) < 20:
            return None

        offset = 4  # skip CDR header
        
        # stamp.sec
        offset += 4
        # stamp.nanosec
        offset += 4
        # frame_id string
        str_len = struct.unpack_from('<I', raw_data, offset)[0]
        offset += 4
        offset += str_len
        # align to 4 bytes
        offset = (offset + 3) & ~3
        
        # data sequence
        data_len = struct.unpack_from('<I', raw_data, offset)[0]
        offset += 4
        data_bytes = raw_data[offset:offset + data_len]
        
        return data_bytes
    
    @staticmethod
    def extract_sub_packets(data_bytes):
        """
        从原始 data 字节流中提取多个子数据包
        
        Args:
            data_bytes: 原始数据流
            
        Returns:
            list: [(type, data), ...] 其中 type 为 'pointcloud', 'imu' 等
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
    
    def decode_point_cloud_packet(self, pkt, vert_angles, horiz_angles):
        """
        解析单个 80 字节的点云数据包
        
        Args:
            pkt: 80 字节的原始数据包
            vert_angles: 垂直角度表 (毫度)
            horiz_angles: 水平角度偏差表 (毫度)
            
        Returns:
            (azimuth, points) 或 None (如果 CRC 失败)
            azimuth: 方位角 (0-35999, 单位 0.01度)
            points: [(x, y, z, intensity), ...] 列表
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

            distance = dist_raw * self.DISTANCE_RES

            angle_vert = vert_angles[chan]  # 毫度
            angle_horiz_final = (horiz_angles[chan] + azimuth * 10 + 360000) % 360000

            optcent_2_lidar_angle_hor = (azimuth * 10 + self.OPTCENT_2_LIDAR_ARG + 360000) % 360000

            if self.DISTANCE_MIN <= distance <= self.DISTANCE_MAX:
                xy = distance * self._cos(angle_vert)
                x = xy * self._sin(angle_horiz_final) + self.OPTCENT_2_LIDAR_L * self._sin(optcent_2_lidar_angle_hor)
                y = xy * self._cos(angle_horiz_final) + self.OPTCENT_2_LIDAR_L * self._cos(optcent_2_lidar_angle_hor)
                z = distance * self._sin(angle_vert) + self.OPTCENT_2_LIDAR_Z
                points.append((float(x), float(y), float(z), reflectivity))

        return azimuth, points


# 便捷函数 (向后兼容)
def decode_point_cloud_packet(pkt, vert_angles, horiz_angles):
    """便捷函数：使用默认解码器解析点云包"""
    VanjeeDecoder.init_trig_tables()
    decoder = VanjeeDecoder()
    return decoder.decode_point_cloud_packet(pkt, vert_angles, horiz_angles)
