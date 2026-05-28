"""
BLE 通信封装：基于 bleak 库，用于 standalone 模式的 Tag 交互。
"""

import asyncio
import struct
import time
from typing import Optional, List
from dataclasses import dataclass

try:
    from bleak import BleakScanner, BleakClient
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False

from protocol import (
    BLE_MSG_INIT_REQ, BLE_MSG_TAG_CONFIG, BLE_MSG_INTERACTION,
    BLE_PAYLOAD_VERSION_REQ, BLE_PAYLOAD_VERSION_RESP, BLE_PAYLOAD_STATUS,
    TagVersion, MIN_TAG_VERSION, TAG_ERROR_FLAGS,
)
from report import CheckResult, CheckStatus


# ── GATT UUIDs (来自 ble_runtime.cpp) ────────────────────────────────────────

NI_TX_CHAR_UUID = "2E93998A-6A61-11ED-A1EB-0242AC120002"   # dog -> tag (write)
NI_RX_CHAR_UUID = "2E939AF2-6A61-11ED-A1EB-0242AC120002"   # tag -> dog (notify)


# ── Parsers ──────────────────────────────────────────────────────────────────

@dataclass
class BleTagInfo:
    tag_addr: int = 0
    major_version: int = 0
    minor_version: int = 0


def parse_tag_config(data: bytes) -> Optional[BleTagInfo]:
    """解析 0x01 tag 配置响应，提取 tag_addr。"""
    if len(data) < 35:
        return None
    info = BleTagInfo()
    info.major_version = struct.unpack_from(">H", data, 0)[0]
    info.minor_version = struct.unpack_from(">H", data, 2)[0]
    # tag_addr: uwb_config_data 偏移 15-16 (payload[17+15])
    uwb_offset = 17
    if uwb_offset + 17 <= len(data):
        info.tag_addr = struct.unpack_from("<H", data, uwb_offset + 15)[0]
    return info


def parse_tag_version_resp(data: bytes) -> Optional[TagVersion]:
    """解析 0x11 payload 中的版本响应 (payload_header=0x07)。"""
    if len(data) < 3:
        return None
    if data[0] != BLE_PAYLOAD_VERSION_RESP:
        return None
    length = struct.unpack_from(">H", data, 1)[0]
    if len(data) < 3 + length or length < 7:
        return None
    d = data[3:]
    return TagVersion(
        sw_major=d[1], sw_minor=d[2], sw_patch=d[3],
        hw_major=d[4], hw_minor=d[5], hw_patch=d[6],
    )


def parse_tag_status(data: bytes) -> Optional[dict]:
    """解析 0x11 payload 中的状态上报 (payload_header=0x08, cmd=0x01)。"""
    if len(data) < 3 or data[0] != BLE_PAYLOAD_STATUS:
        return None
    length = struct.unpack_from(">H", data, 1)[0]
    if len(data) < 3 + length or length < 2:
        return None
    d = data[3:]
    if d[0] != 0x01:
        return None
    if len(d) < 6:
        return None
    error_flags = struct.unpack_from("<I", d, 1)[0]
    battery_raw = d[5]
    is_charging = battery_raw == 0xFF
    return {
        "error_flags": error_flags,
        "battery_percentage": 100 if is_charging else battery_raw,
        "is_charging": is_charging,
    }


# ── BLE Comm Class ───────────────────────────────────────────────────────────

class BleComm:
    def __init__(self, tag_name: str):
        self.tag_name = tag_name
        self._client: Optional['BleakClient'] = None
        self._address: Optional[str] = None
        self._rx_buffer: List[bytes] = []

    async def scan_and_connect(self, scan_timeout: float = 10.0) -> bool:
        if not HAS_BLEAK:
            return False
        devices = await BleakScanner.discover(timeout=scan_timeout)
        for d in devices:
            if d.name and self.tag_name in d.name:
                self._address = d.address
                break
        if not self._address:
            return False
        self._client = BleakClient(self._address)
        try:
            await self._client.connect(timeout=10.0)
        except Exception:
            return False
        if not self._client.is_connected:
            return False
        try:
            await self._client.start_notify(NI_RX_CHAR_UUID, self._on_notify)
        except Exception:
            pass
        return True

    async def disconnect(self):
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    async def write(self, data: bytes):
        if self._client and self._client.is_connected:
            await self._client.write_gatt_char(NI_TX_CHAR_UUID, data, response=False)

    async def wait_response(self, timeout: float = 5.0) -> Optional[bytes]:
        self._rx_buffer.clear()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._rx_buffer:
                return self._rx_buffer.pop(0)
            await asyncio.sleep(0.05)
        return None

    def _on_notify(self, sender, data: bytearray):
        self._rx_buffer.append(bytes(data))

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected


# ── Helper ───────────────────────────────────────────────────────────────────

def _get_loop():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


# ── BLE Checks ───────────────────────────────────────────────────────────────

def check_ble_connect(tag_name: str, verbose: bool = False):
    """检查 4: BLE Tag 连接。返回 (result, BleComm or None, tag_addr)。"""
    name = "BLE Tag 连接"

    if not HAS_BLEAK:
        return CheckResult(name=name, status=CheckStatus.SKIP, detail="bleak 未安装"), None, 0

    ble = BleComm(tag_name)
    loop = _get_loop()

    async def _do():
        ok = await ble.scan_and_connect(scan_timeout=10.0)
        if not ok:
            # 列出扫描到的设备帮助排查
            try:
                from bleak import BleakScanner
                devs = await BleakScanner.discover(timeout=5)
                vbots = [f"{d.name}({d.address})" for d in devs
                         if d.name and ("Vbot" in d.name or "vbot" in d.name)]
                if vbots:
                    hint = f"附近 Vbot 设备: {', '.join(vbots)}"
                else:
                    hint = "附近未发现任何 Vbot 设备"
            except Exception:
                hint = "无法扫描附近设备"
            return CheckResult(name=name, status=CheckStatus.FAIL,
                               detail=f"未找到 {tag_name} ({hint})"), 0

        # 发 0x0A 获取 tag 配置
        await ble.write(bytes([BLE_MSG_INIT_REQ]))
        resp = await ble.wait_response(timeout=5.0)
        if resp is None or len(resp) < 2:
            return CheckResult(name=name, status=CheckStatus.FAIL, detail="0x0A 无响应"), 0
        if resp[0] != BLE_MSG_TAG_CONFIG:
            return CheckResult(name=name, status=CheckStatus.FAIL,
                               detail=f"期望 0x01, 收到 0x{resp[0]:02X}"), 0

        tag_info = parse_tag_config(resp[1:])
        addr = tag_info.tag_addr if tag_info else 0
        return CheckResult(name=name, status=CheckStatus.PASS,
                           detail=f"{tag_name}, tag_addr=0x{addr:04X}",
                           data={"tag_name": tag_name, "tag_addr": addr}), addr

    try:
        result, addr = loop.run_until_complete(_do())
    except Exception as e:
        return CheckResult(name=name, status=CheckStatus.FAIL, detail=f"BLE 异常: {e}"), None, 0

    if result.status != CheckStatus.PASS:
        return result, None, 0
    return result, ble, addr


def check_tag_version(ble: Optional['BleComm'], verbose: bool = False):
    """检查 5: Tag 版本。返回 (result, TagVersion or None)。"""
    name = "Tag 版本"
    if ble is None or not ble.is_connected:
        return CheckResult(name=name, status=CheckStatus.SKIP, detail="BLE 未连接"), None

    loop = _get_loop()

    async def _do():
        req = bytes([BLE_MSG_INTERACTION, BLE_PAYLOAD_VERSION_REQ, 0x00, 0x01, 0x01])
        await ble.write(req)
        resp = await ble.wait_response(timeout=5.0)
        if resp is None or len(resp) < 2:
            return CheckResult(name=name, status=CheckStatus.FAIL, detail="版本查询无响应"), None
        if resp[0] != BLE_MSG_INTERACTION:
            return CheckResult(name=name, status=CheckStatus.FAIL,
                               detail=f"意外响应 0x{resp[0]:02X}"), None
        ver = parse_tag_version_resp(resp[1:])
        if ver is None:
            return CheckResult(name=name, status=CheckStatus.FAIL, detail="版本解析失败"), None
        min_str = ".".join(str(x) for x in MIN_TAG_VERSION)
        if ver.sw_tuple < MIN_TAG_VERSION:
            return CheckResult(name=name, status=CheckStatus.FAIL,
                               detail=f"{ver} < {min_str}"), ver
        return CheckResult(name=name, status=CheckStatus.PASS, detail=str(ver),
                           data={"sw_version": ver.sw_str, "hw_version": ver.hw_str}), ver

    try:
        result, ver = loop.run_until_complete(_do())
    except Exception as e:
        return CheckResult(name=name, status=CheckStatus.FAIL, detail=f"异常: {e}"), None
    return result, ver


def check_tag_status(ble: Optional['BleComm'], verbose: bool = False) -> CheckResult:
    """检查 9: Tag 状态/电量 (standalone BLE)。"""
    name = "Tag 状态/电量"
    if ble is None or not ble.is_connected:
        return CheckResult(name=name, status=CheckStatus.SKIP, detail="BLE 未连接")

    loop = _get_loop()

    async def _do():
        # 等待被动上报 0x11 0x08 最多 10s
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            resp = await ble.wait_response(timeout=2.0)
            if resp is None:
                continue
            if resp[0] == BLE_MSG_INTERACTION and len(resp) > 1:
                info = parse_tag_status(resp[1:])
                if info:
                    parts = [f"电量 {info['battery_percentage']}%"]
                    warns = []
                    if info['is_charging']:
                        parts.append("充电中")
                    if info['battery_percentage'] < 10:
                        warns.append("电量过低")
                    ef = info['error_flags']
                    if ef:
                        flags = [n for b, n in TAG_ERROR_FLAGS.items() if ef & b]
                        if flags:
                            warns.append(f"错误: {', '.join(flags)}")
                    st = CheckStatus.WARN if warns else CheckStatus.PASS
                    return CheckResult(name=name, status=st,
                                       detail=", ".join(parts + warns), data=info)
        return CheckResult(name=name, status=CheckStatus.WARN, detail="10s 内未收到状态上报")

    try:
        return loop.run_until_complete(_do())
    except Exception as e:
        return CheckResult(name=name, status=CheckStatus.WARN, detail=f"异常: {e}")
