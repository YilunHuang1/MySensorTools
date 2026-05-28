"""
UWB Serial Protocol: 帧构造、CRC 校验、收发。

基于 SPEC_PROTOCOL.md 中定义的串口协议实现。
数据格式: [0x55][0xAA][seq][tlv_total_len:u16le][tlv_data][crc16:u16be]
CRC: CRC-16-XMODEM, 仅校验 tlv_data 部分, 大端写入。
TLV: Type(u8) + Length(u8) + Value(u8[Length]), Value 小端。
"""

import struct
import time
import threading
from typing import Optional, List, Tuple, Callable
from dataclasses import dataclass, field

import serial

# ── Constants ────────────────────────────────────────────────────────────────

HEADER_MAGIC = bytes([0x55, 0xAA])
HEADER_LEN = 5  # 0x55 + 0xAA + seq(1) + tlv_total_len(2)
CRC_LEN = 2
MIN_PACKET_LEN = HEADER_LEN + CRC_LEN
MAX_PACKET_LEN = 1024

# CRC-16-XMODEM lookup table (matches C++ implementation)
_CRC16_XMODEM_TABLE = [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
    0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
    0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
    0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
    0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
    0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
    0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12,
    0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
    0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
    0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
    0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
    0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
    0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
    0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
    0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
    0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
    0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
    0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A,
    0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
    0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DE8, 0x8DC9,
    0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
    0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
    0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0,
]


def crc16_xmodem(data: bytes, crc: int = 0x0000) -> int:
    """CRC-16-XMODEM, 与 C++ Crc16Xmodem 一致。"""
    for byte in data:
        tmp = ((crc >> 8) ^ byte) & 0xFF
        crc = ((crc << 8) ^ _CRC16_XMODEM_TABLE[tmp]) & 0xFFFF
    return crc


# ── TLV ──────────────────────────────────────────────────────────────────────

@dataclass
class TLV:
    type: int
    value: bytes

    @property
    def length(self) -> int:
        return len(self.value)

    def to_bytes(self) -> bytes:
        return bytes([self.type, self.length]) + self.value


def parse_tlvs(data: bytes) -> List[TLV]:
    """解析 TLV 列表，兼容 0xC5 固件 quirk（len 0x22 实际 0x26）。"""
    result = []
    offset = 0
    while offset + 2 <= len(data):
        tlv_type = data[offset]
        tlv_len = data[offset + 1]
        # 固件 quirk: AOA 0xC5 报 len=0x22 实际有效 0x26
        if tlv_type == 0xC5 and tlv_len == 0x22 and (offset + 2 + 0x26) <= len(data):
            tlv_len = 0x26
        if offset + 2 + tlv_len > len(data):
            break
        result.append(TLV(type=tlv_type, value=data[offset + 2: offset + 2 + tlv_len]))
        offset += 2 + tlv_len
    return result


# ── Packet ───────────────────────────────────────────────────────────────────

@dataclass
class SerialPacket:
    sequence: int
    tlvs: List[TLV]
    crc_ok: bool = True

    @property
    def raw_tlv_data(self) -> bytes:
        return b"".join(t.to_bytes() for t in self.tlvs)


# 序列号自增
_seq_counter = 0
_seq_lock = threading.Lock()


def _next_seq() -> int:
    global _seq_counter
    with _seq_lock:
        seq = _seq_counter & 0xFF
        _seq_counter += 1
        return seq


def build_packet(tlvs: List[TLV], seq: Optional[int] = None) -> bytes:
    """构建串口数据包。"""
    if seq is None:
        seq = _next_seq()
    tlv_data = b"".join(t.to_bytes() for t in tlvs)
    tlv_len = len(tlv_data)
    # header: 0x55 0xAA seq tlv_total_len(u16le)
    header = struct.pack("<BBB H", 0x55, 0xAA, seq & 0xFF, tlv_len)
    # CRC over tlv_data, big-endian
    crc = crc16_xmodem(tlv_data)
    crc_bytes = struct.pack(">H", crc)
    return header + tlv_data + crc_bytes


# ── Serial Communication ────────────────────────────────────────────────────

class SerialComm:
    """串口通信封装：收发数据包，帧解析。"""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._buffer = bytearray()
        # 统计
        self.total_packets_received = 0
        self.crc_errors = 0

    def open(self) -> bool:
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            self._buffer.clear()
            return True
        except serial.SerialException:
            return False

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def send(self, tlvs: List[TLV]) -> bytes:
        """发送 TLV 数据包，返回发送的原始字节。"""
        pkt = build_packet(tlvs)
        if self._ser:
            self._ser.write(pkt)
            self._ser.flush()
        return pkt

    def receive(self, timeout: Optional[float] = None) -> Optional[SerialPacket]:
        """
        从串口读取并解析一个完整数据包。
        返回 None 表示超时未收到。
        """
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        while time.monotonic() < deadline:
            self._read_available()
            pkt = self._try_parse()
            if pkt is not None:
                return pkt
            time.sleep(0.005)
        return None

    def receive_many(self, duration: float) -> List[SerialPacket]:
        """持续接收指定时长的所有数据包。"""
        packets = []
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self._read_available()
            while True:
                pkt = self._try_parse()
                if pkt is None:
                    break
                packets.append(pkt)
            time.sleep(0.005)
        return packets

    def send_and_receive(self, tlvs: List[TLV], timeout: Optional[float] = None) -> Optional[SerialPacket]:
        """发送后等待一个响应包。"""
        self.send(tlvs)
        return self.receive(timeout)

    def drain(self, duration: float = 0.3):
        """排空缓冲区。"""
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if self._ser and self._ser.in_waiting:
                self._ser.read(self._ser.in_waiting)
            time.sleep(0.01)
        self._buffer.clear()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _read_available(self):
        if not self._ser:
            return
        try:
            n = self._ser.in_waiting
            if n > 0:
                data = self._ser.read(n)
                self._buffer.extend(data)
        except serial.SerialException:
            pass

    def _try_parse(self) -> Optional[SerialPacket]:
        """尝试从 buffer 中解析一个完整包。"""
        while len(self._buffer) >= MIN_PACKET_LEN:
            # 寻找 sync header
            idx = self._buffer.find(HEADER_MAGIC)
            if idx < 0:
                self._buffer.clear()
                return None
            if idx > 0:
                del self._buffer[:idx]

            if len(self._buffer) < HEADER_LEN:
                return None

            seq = self._buffer[2]
            tlv_total_len = struct.unpack_from("<H", self._buffer, 3)[0]
            required = HEADER_LEN + tlv_total_len + CRC_LEN

            if required > MAX_PACKET_LEN:
                # 坏包，跳过这个 sync
                del self._buffer[:2]
                continue

            if len(self._buffer) < required:
                return None  # 等更多数据

            tlv_data = bytes(self._buffer[HEADER_LEN: HEADER_LEN + tlv_total_len])
            crc_received = struct.unpack_from(">H", self._buffer, HEADER_LEN + tlv_total_len)[0]
            crc_calculated = crc16_xmodem(tlv_data)

            crc_ok = (crc_received == crc_calculated)
            self.total_packets_received += 1
            if not crc_ok:
                self.crc_errors += 1

            tlvs = parse_tlvs(tlv_data)
            del self._buffer[:required]
            return SerialPacket(sequence=seq, tlvs=tlvs, crc_ok=crc_ok)

        return None
