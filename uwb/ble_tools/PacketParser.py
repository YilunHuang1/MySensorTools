import struct

class PacketParser:

    @staticmethod
    def parse(data_bytes):
        if data_bytes[5] == 0xC5:
            return PacketParser.parseRangingPacket(data_bytes)
        else:
            return None
    
    @staticmethod
    def parseRangingPacket(data_bytes):
        offset = 7  # 从数据帧头跳过固定的头部字段
        result = {}

        result['sync_cnt'], result['mac_id'], result['fob_id'] = \
            struct.unpack_from('<III', data_bytes, offset)
        offset += 12

        result['fob_type'] = struct.unpack_from('<H', data_bytes, offset)[0]
        offset += 2

        result['distance'], result['angle'], result['pitch'] = \
            struct.unpack_from('<fff', data_bytes, offset)
        offset += 12

        result['rssi_len'] = struct.unpack_from('<B', data_bytes, offset)[0]
        offset += 1

        result['rssi_values'] = struct.unpack_from(f'{result["rssi_len"]}b', data_bytes, offset)
        offset += result['rssi_len']

        return result