"""UWB serial framing and C5 ranging payload decoding, independent of ROS."""
import binascii
import struct


def tlvs(payload):
    offset = 0
    while offset < len(payload):
        if len(payload) - offset < 2:
            raise ValueError('truncated TLV header')
        kind, length = payload[offset:offset + 2]
        offset += 2
        if kind == 0xc5 and length == 0x22 and len(payload) - offset >= 0x26:
            # Supported firmware underreports 38-byte C5 values as 34 bytes.
            # Expand only when the RSSI count requires the extra footer bytes;
            # an ordinary 34-byte C5 followed by another TLV must stay intact.
            footer_end = 27 + payload[offset + 26] + 5
            if length < footer_end <= 0x26:
                length = 0x26
        if offset + length > len(payload):
            raise ValueError('TLV length exceeds packet')
        yield kind, bytes(payload[offset:offset + length])
        offset += length


def packet_tlvs(packet):
    if len(packet) < 7 or packet[:2] != b'\x55\xaa':
        raise ValueError('invalid serial header')
    length = struct.unpack_from('<H', packet, 3)[0]
    if length + 7 != len(packet):
        raise ValueError('serial length mismatch')
    payload = packet[5:-2]
    if binascii.crc_hqx(payload, 0) != struct.unpack_from('>H', packet, len(packet) - 2)[0]:
        raise ValueError('serial CRC mismatch')
    return list(tlvs(payload))


def ranging(value):
    if len(value) < 26:
        raise ValueError('truncated C5 fixed fields')
    sync, mac, fob, fob_type, distance, angle, pitch = struct.unpack_from('<IIIHfff', value)
    result = dict(sync_cnt=sync, mac_id=mac, fob_id=fob, fob_type=fob_type, distance=distance,
                  angle=angle, pitch=pitch, rssi_len=0, rssi_values=(), rssi_rxp=None,
                  rssi_fpp=None, rssi_np=None, rssi_ble=None, pos_confidence=None)
    if len(value) == 26:
        return result  # Older firmware omitted the entire optional block.
    count = value[26]
    end = 27 + count
    if end > len(value):
        raise ValueError('truncated C5 RSSI vector')
    result.update(rssi_len=count, rssi_values=struct.unpack_from(f'<{count}b', value, 27))
    tail = value[end:]
    if tail and len(tail) < 4:
        raise ValueError('truncated C5 RSSI extension')
    if len(tail) >= 4:
        result.update(zip(['rssi_rxp', 'rssi_fpp', 'rssi_np', 'rssi_ble'], struct.unpack_from('<bbbb', tail)))
    if len(tail) >= 5:
        result['pos_confidence'] = tail[4]
    result['extension_bytes'] = bytes(tail[5:])
    return result


class Framer:
    """Incremental receiver; invalid frames are resynchronized, never parsed as C5."""
    def __init__(self):
        self.buffer = bytearray()
        self.invalid_frames = 0

    def feed(self, data):
        self.buffer.extend(data)
        packets = []
        while len(self.buffer) >= 7:
            if self.buffer[:2] != b'\x55\xaa':
                del self.buffer[0]
                continue
            length = struct.unpack_from('<H', self.buffer, 3)[0] + 7
            if len(self.buffer) < length:
                break
            packet = bytes(self.buffer[:length])
            try:
                packet_tlvs(packet)
            except ValueError:
                self.invalid_frames += 1
                del self.buffer[0]
            else:
                packets.append(packet)
                del self.buffer[:length]
        return packets
