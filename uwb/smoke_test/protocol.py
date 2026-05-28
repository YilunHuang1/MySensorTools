"""
UWB 协议常量与命令构造。

基于 SPEC_PROTOCOL.md 中的 TLV 定义。
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
import struct

from serial_comm import TLV

# ── Serial TLV Types ─────────────────────────────────────────────────────────

TLV_RESPONSE = 0x00           # 设备响应
TLV_REBOOT = 0x05             # 重启
TLV_DISTANCE_OFFSET = 0x0B    # 距离偏移配置
TLV_FIRA_CONFIG = 0x24        # FIRA 配置
TLV_SENTRY_CONTROL = 0x4A     # 哨兵模式控制
TLV_VERSION = 0x53            # 版本号
TLV_SENTRY_STATUS = 0x54      # 哨兵状态上报
TLV_RADAR_CONFIG = 0x55       # 雷达参数配置
TLV_HEARTBEAT = 0x59          # 会话心跳
TLV_RANGING_CONTROL = 0x60    # 启动/停止测距
TLV_SN_CONFIG = 0x08          # SN 码配置
TLV_AOA_DATA = 0xC5           # 距离/角度/俯仰角
TLV_ERROR_STATUS = 0xC7       # 错误状态反馈

# ── BLE Message IDs ──────────────────────────────────────────────────────────

BLE_MSG_INIT_REQ = 0x0A       # dog -> tag: 初始化请求
BLE_MSG_TAG_CONFIG = 0x01     # tag -> dog: tag 配置数据
BLE_MSG_START_RANGING = 0x0B  # dog -> tag: 开始测距
BLE_MSG_RANGING_STARTED = 0x02  # tag -> dog: 确认开启
BLE_MSG_STOP_RANGING = 0x0C   # dog -> tag: 停止测距
BLE_MSG_RANGING_STOPPED = 0x03  # tag -> dog: 确认关闭
BLE_MSG_INTERACTION = 0x11    # tag <-> dog: 交互

# BLE Interaction payload_headers
BLE_PAYLOAD_TAG_EVENT = 0x01
BLE_PAYLOAD_VOICE_RESP = 0x02
BLE_PAYLOAD_DOG_RESP = 0x03
BLE_PAYLOAD_TAG_RESP = 0x04
BLE_PAYLOAD_DOG_REQ = 0x05
BLE_PAYLOAD_VERSION_REQ = 0x06
BLE_PAYLOAD_VERSION_RESP = 0x07
BLE_PAYLOAD_STATUS = 0x08
BLE_PAYLOAD_PRODUCTION = 0x09

# ── Response Status Codes ────────────────────────────────────────────────────

RESP_STATUS = {
    0x00: "OK",
    0x01: "FORMAT_ERROR",
    0x02: "UNSUPPORTED_CMD",
    0x03: "DATA_TOO_LONG",
    0x04: "AUTH_ERROR",
    0x05: "UNDER_VOLTAGE",
    0x06: "CRC_ERROR",
    0x07: "DEVICE_REBOOT",
    0x08: "BASEBAND_ERROR",
}

# ── Error Status Codes (0xC7) ────────────────────────────────────────────────

ERROR_STATUS = {
    0x00: "STATUS_OK",
    0x01: "STATUS_REJECTED",
    0x20: "RANGING_TX_FAILED",
    0x21: "RANGING_RX_TIMEOUT",
    0x22: "RANGING_RX_PHY_DEC_FAILED",
    0x23: "RANGING_RX_PHY_TOA_FAILED",
    0x24: "RANGING_RX_PHY_STS_FAILED",
    0x25: "RANGING_RX_MAC_DEC_FAILED",
    0x26: "RANGING_RX_MAC_IE_DEC_FAILED",
    0x27: "RANGING_RX_MAC_IE_MISSING",
    0xE4: "RANGING_BASEBAND_ERROR",
    0xE8: "RANGE_DISTANCE_FAIL",
    0xE9: "RANGE_ANGLE_FAIL",
}

# Critical errors that indicate hardware/firmware issues
CRITICAL_ERROR_CODES = {0xE4}  # baseband error

# ── Minimum Compatible Versions ─────────────────────────────────────────────

MIN_ANCHOR_VERSION = (5, 0, 24)
MIN_TAG_VERSION = (0, 1, 15)

# ── Tag Error Flags (from BLE 0x11 0x08 0x01) ───────────────────────────────

TAG_ERROR_FLAGS = {
    0x01: "D5_INIT_FAILED",
    0x02: "D5_SESSION_FAILED",
    0x04: "D5_RANGE_ABNORMAL",
    0x08: "D5_DISCONNECTED",
    0x10: "IMU_INIT_FAILED",
    0x20: "LOW_BATTERY",
}


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class AnchorVersion:
    major: int
    minor: int
    patch: int

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tuple(self):
        return (self.major, self.minor, self.patch)


@dataclass
class TagVersion:
    sw_major: int
    sw_minor: int
    sw_patch: int
    hw_major: int
    hw_minor: int
    hw_patch: int

    @property
    def sw_str(self):
        return f"{self.sw_major}.{self.sw_minor}.{self.sw_patch}"

    @property
    def hw_str(self):
        return f"{self.hw_major}.{self.hw_minor}.{self.hw_patch}"

    def __str__(self):
        return f"SW {self.sw_str} / HW {self.hw_str}"

    @property
    def sw_tuple(self):
        return (self.sw_major, self.sw_minor, self.sw_patch)


@dataclass
class AoaFrame:
    """解析后的单帧 AoA 数据。"""
    sync_cnt: int = 0
    distance: float = 0.0
    angle: float = 0.0
    pitch: float = 0.0
    rssi: List[int] = None
    rssi_rxp: int = 0
    rssi_fpp: int = 0
    rssi_np: int = 0
    rssi_ble: int = 0
    pos_confidence: int = 0
    timestamp: float = 0.0  # 本地接收时间


@dataclass
class HeartbeatFrame:
    heart_cnt: int = 0
    range_status: int = 0
    radar_status: int = 0


# ── Command Builders ─────────────────────────────────────────────────────────

def cmd_reboot() -> List[TLV]:
    """0x05: 重启 Anchor。"""
    return [TLV(type=TLV_REBOOT, value=bytes([0x01]))]


def cmd_get_version_raw() -> List[TLV]:
    """发送版本查询（直接复用固件发的固定帧）。
    实际上 Anchor 重启后会自动上报版本，这里提供一个主动触发。
    """
    # 发送 0x05 0x01 重启来获取版本，或者等待心跳。
    # 简单方案：发送一个 0x00 响应探测，设备会回复。
    return [TLV(type=TLV_RESPONSE, value=bytes([0xFF, 0x00]))]


def cmd_fira_config(
    session_id: int = 0x1111,
    precode: int = 12,
    tag_addr: int = 0x0000,
    anchor_addr: int = 0x0100,
) -> List[TLV]:
    """0x24: 配置 FIRA 参数。"""
    value = bytearray()
    value += struct.pack("<HH", 0x0001, 0x0000)       # major_ver, minor_ver
    value += bytes([0x17])                               # len
    value += bytes([0x43, 0x4E])                         # country_code "CN"
    value += struct.pack("<I", session_id)               # session_id
    value += bytes([precode & 0xFF])                     # preamble_id
    value += bytes([0x09])                               # chan_num
    value += bytes([0x08])                               # slot_ix
    value += bytes([0x00])                               # res0
    value += struct.pack("<H", 0x0960)                   # slot_rstu
    value += struct.pack("<H", 0x0030)                   # range_period 48ms
    value += bytes([0x03])                               # ranging_round_control
    value += bytes([0x01, 0x01, 0x01, 0x01, 0x01, 0x01])  # vupper_48
    value += struct.pack("<H", tag_addr)                 # tag_addr
    value += struct.pack("<H", anchor_addr)              # anchor_addr
    value += bytes([0x02])                               # num_of_anchors
    value += bytes([0x01])                               # multi_mode
    value += bytes([0x01, 0x01])                         # vendor_id
    return [TLV(type=TLV_FIRA_CONFIG, value=bytes(value))]


def cmd_start_ranging(session_id: int = 0x1111) -> List[TLV]:
    """0x60: 启动测距。"""
    value = bytearray([0x01])
    value += struct.pack("<I", session_id)
    return [TLV(type=TLV_RANGING_CONTROL, value=bytes(value))]


def cmd_stop_ranging(session_id: int = 0x1111) -> List[TLV]:
    """0x60: 停止测距。"""
    value = bytearray([0x02])
    value += struct.pack("<I", session_id)
    return [TLV(type=TLV_RANGING_CONTROL, value=bytes(value))]


def cmd_sentry_enable() -> List[TLV]:
    """0x4A: 开启哨兵。"""
    return [TLV(type=TLV_SENTRY_CONTROL, value=bytes([0x04]))]


def cmd_sentry_disable() -> List[TLV]:
    """0x4A: 关闭哨兵。"""
    return [TLV(type=TLV_SENTRY_CONTROL, value=bytes([0x05]))]


# ── Parsers ──────────────────────────────────────────────────────────────────

def parse_response_tlv(tlv: TLV) -> Optional[Tuple[int, int]]:
    """解析 0x00 响应 TLV，返回 (type_resp, status)。"""
    if tlv.type != TLV_RESPONSE or len(tlv.value) < 2:
        return None
    return (tlv.value[0], tlv.value[1])


def parse_anchor_version(tlv: TLV) -> Optional[AnchorVersion]:
    """解析 0x53 版本 TLV。"""
    if tlv.type != TLV_VERSION or len(tlv.value) < 16:
        return None
    # 跳过 4 字节固定头 (60 0A 00 10)
    data = tlv.value[4:]
    if len(data) < 12:
        return None
    major = struct.unpack_from("<I", data, 0)[0]
    minor = struct.unpack_from("<I", data, 4)[0]
    patch = struct.unpack_from("<I", data, 8)[0]
    return AnchorVersion(major=major, minor=minor, patch=patch)


def parse_aoa_data(tlv: TLV, recv_time: float = 0.0) -> Optional[AoaFrame]:
    """解析 0xC5 AoA TLV。"""
    if tlv.type != TLV_AOA_DATA:
        return None
    data = tlv.value
    if len(data) < 26:
        return None

    frame = AoaFrame(timestamp=recv_time)
    frame.sync_cnt = struct.unpack_from("<I", data, 0)[0]
    # skip mac_id(4), fob_id(4), fob_type(2) = 10 bytes
    offset = 14
    frame.distance = struct.unpack_from("<f", data, offset)[0]; offset += 4
    frame.angle = struct.unpack_from("<f", data, offset)[0]; offset += 4
    frame.pitch = struct.unpack_from("<f", data, offset)[0]; offset += 4

    if offset < len(data):
        rssi_len = data[offset]; offset += 1
        if offset + rssi_len <= len(data):
            frame.rssi = [struct.unpack_from("<b", data, offset + i)[0] for i in range(rssi_len)]
            offset += rssi_len

    # rssi_rxp, rssi_fpp, rssi_np, rssi_ble (optional)
    for attr in ['rssi_rxp', 'rssi_fpp', 'rssi_np', 'rssi_ble']:
        if offset < len(data):
            setattr(frame, attr, struct.unpack_from("<b", data, offset)[0])
            offset += 1

    # pos_confidence
    if offset < len(data):
        frame.pos_confidence = data[offset]

    return frame


def parse_heartbeat(tlv: TLV) -> Optional[HeartbeatFrame]:
    """解析 0x59 心跳 TLV。"""
    if tlv.type != TLV_HEARTBEAT or len(tlv.value) < 3:
        return None
    return HeartbeatFrame(
        heart_cnt=tlv.value[0],
        range_status=tlv.value[1],
        radar_status=tlv.value[2],
    )


def parse_error_status(tlv: TLV) -> Optional[int]:
    """解析 0xC7 错误状态，返回 status_code。"""
    if tlv.type != TLV_ERROR_STATUS or len(tlv.value) < 1:
        return None
    return tlv.value[0]
