"""
Standalone 模式检查项：直接操作串口和 BLE，需先停止 uwb 服务。

注意：
- 测距功能检查需要 Tag（信令）在线且 BLE 已连接。
  如果使用 --anchor-only 或 BLE 连接失败，测距相关检查会被跳过。
- Anchor 重启后至少需要 2s 才能接收新命令 (SPEC 要求)。
"""

import time
import math
import statistics
from typing import Optional, List

from serial_comm import SerialComm, TLV
from protocol import (
    TLV_RESPONSE, TLV_VERSION, TLV_AOA_DATA, TLV_ERROR_STATUS, TLV_HEARTBEAT,
    cmd_reboot, cmd_fira_config, cmd_start_ranging, cmd_stop_ranging,
    parse_response_tlv, parse_anchor_version, parse_aoa_data,
    parse_heartbeat, parse_error_status,
    AnchorVersion, AoaFrame,
    MIN_ANCHOR_VERSION, CRITICAL_ERROR_CODES, ERROR_STATUS, RESP_STATUS,
)
from report import CheckResult, CheckStatus


def _collect_until_tlv(comm: SerialComm, target_type: int,
                       timeout: float = 8.0) -> tuple[list, Optional[TLV]]:
    """持续接收直到找到指定类型 TLV 或超时。"""
    all_pkts = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pkt = comm.receive(timeout=0.5)
        if pkt is None or not pkt.crc_ok:
            continue
        all_pkts.append(pkt)
        for tlv in pkt.tlvs:
            if tlv.type == target_type:
                return all_pkts, tlv
    return all_pkts, None


# ─────────────────────────────────────────────────────────────────────────────
# 检查 1+2: 串口通信 + Anchor 版本 (合并，共享一次重启)
# ─────────────────────────────────────────────────────────────────────────────

def check_serial_and_version(comm: SerialComm, verbose: bool = False):
    """发送重启 → 等响应(串口OK) → 等版本上报(版本OK)。

    返回: (serial_result, version_result, AnchorVersion or None)
    """
    s_name = "串口通信"
    v_name = "Anchor 版本"

    if not comm.is_open and not comm.open():
        fail = CheckStatus.FAIL
        return (
            CheckResult(name=s_name, status=fail, detail=f"无法打开串口 {comm.port}"),
            CheckResult(name=v_name, status=fail, detail="串口不可用"),
            None,
        )

    comm.drain()

    # 发送重启
    t0 = time.monotonic()
    comm.send(cmd_reboot())

    # 等任意响应 → 串口通信 OK
    first = comm.receive(timeout=3.0)
    if first is None or not first.crc_ok:
        fail = CheckStatus.FAIL
        return (
            CheckResult(name=s_name, status=fail, detail="重启命令无响应 (3s)"),
            CheckResult(name=v_name, status=fail, detail="串口无响应"),
            None,
        )

    latency = (time.monotonic() - t0) * 1000
    serial_r = CheckResult(name=s_name, status=CheckStatus.PASS,
                           detail=f"响应延迟 {latency:.0f}ms",
                           data={"latency_ms": round(latency, 1)})

    # 重启中的首个响应可能就包含版本 TLV
    version = None
    for tlv in first.tlvs:
        if tlv.type == TLV_VERSION:
            version = parse_anchor_version(tlv)

    # 如果首个响应没版本，等设备重启完成后上报 (0x53)
    if version is None:
        time.sleep(2.5)  # 等设备重启
        _, vtlv = _collect_until_tlv(comm, TLV_VERSION, timeout=8.0)
        if vtlv:
            version = parse_anchor_version(vtlv)

    if version is None:
        return serial_r, CheckResult(name=v_name, status=CheckStatus.FAIL,
                                     detail="重启后未收到版本上报 (0x53)"), None

    min_str = ".".join(str(x) for x in MIN_ANCHOR_VERSION)
    if version.tuple < MIN_ANCHOR_VERSION:
        return serial_r, CheckResult(name=v_name, status=CheckStatus.FAIL,
                                     detail=f"{version} < {min_str}",
                                     data={"version": str(version)}), version

    return serial_r, CheckResult(name=v_name, status=CheckStatus.PASS,
                                 detail=f"{version} (≥ {min_str})",
                                 data={"version": str(version)}), version


# ─────────────────────────────────────────────────────────────────────────────
# 检查 3: Anchor 重启恢复
# ─────────────────────────────────────────────────────────────────────────────

def check_anchor_reboot(comm: SerialComm, verbose: bool = False) -> CheckResult:
    name = "Anchor 重启恢复"
    comm.drain()
    comm.send(cmd_reboot())
    time.sleep(2.5)

    t0 = time.monotonic()
    _, vtlv = _collect_until_tlv(comm, TLV_VERSION, timeout=8.0)
    if vtlv is None:
        return CheckResult(name=name, status=CheckStatus.FAIL, detail="重启后未恢复通信 (8s)")

    elapsed = time.monotonic() - t0
    ver = parse_anchor_version(vtlv)
    extra = f", 版本 {ver}" if ver else ""
    return CheckResult(name=name, status=CheckStatus.PASS,
                       detail=f"重启后 {elapsed:.1f}s 恢复{extra}",
                       data={"recovery_time_s": round(elapsed, 1)})


# ─────────────────────────────────────────────────────────────────────────────
# 检查: Anchor 心跳 + 错误状态 (非测距状态下的基础检查)
# ─────────────────────────────────────────────────────────────────────────────

def check_heartbeat_and_errors(comm: SerialComm, duration: float = 5.0,
                               verbose: bool = False) -> tuple[CheckResult, CheckResult]:
    """监听 0x59 心跳和 0xC7 错误状态。"""
    hb_name = "Anchor 心跳"
    err_name = "错误状态"

    comm.drain()
    heartbeats = []
    error_codes = []

    packets = comm.receive_many(duration=duration)
    for pkt in packets:
        if not pkt.crc_ok:
            continue
        for tlv in pkt.tlvs:
            if tlv.type == TLV_HEARTBEAT:
                hb = parse_heartbeat(tlv)
                if hb:
                    heartbeats.append(hb)
            elif tlv.type == TLV_ERROR_STATUS:
                code = parse_error_status(tlv)
                if code is not None:
                    error_codes.append(code)

    # 心跳结果
    if not heartbeats:
        hb_r = CheckResult(name=hb_name, status=CheckStatus.WARN,
                           detail=f"{duration:.0f}s 内未收到心跳 (设备可能未完成初始化)")
    else:
        rate = len(heartbeats) / duration
        hb_r = CheckResult(name=hb_name, status=CheckStatus.PASS,
                           detail=f"{len(heartbeats)} 个心跳 ({rate:.1f}Hz)",
                           data={"count": len(heartbeats), "rate": round(rate, 1)})

    # 错误状态结果
    err_r = _make_error_result(err_name, error_codes)

    return hb_r, err_r


def _make_error_result(name: str, error_codes: list) -> CheckResult:
    if not error_codes:
        return CheckResult(name=name, status=CheckStatus.WARN, detail='未收到有效错误状态，不能确认无错误')
    critical = [c for c in error_codes if c in CRITICAL_ERROR_CODES]
    if critical:
        codes_str = ", ".join(f"0x{c:02X}({ERROR_STATUS.get(c, '?')})" for c in critical)
        return CheckResult(name=name, status=CheckStatus.FAIL,
                           detail=f"严重错误: {codes_str}",
                           data={"critical_errors": [f"0x{c:02X}" for c in critical]})
    non_ok = [c for c in error_codes if c != 0x00]
    if non_ok:
        counter = {}
        for c in non_ok:
            counter[c] = counter.get(c, 0) + 1
        parts = [f"0x{c:02X}({ERROR_STATUS.get(c, '?')})x{n}" for c, n in counter.items()]
        return CheckResult(name=name, status=CheckStatus.WARN,
                           detail=f"非致命错误: {', '.join(parts)}",
                           data={"errors": [f"0x{c:02X}" for c in non_ok]})
    return CheckResult(name=name, status=CheckStatus.PASS, detail="无错误")


# ─────────────────────────────────────────────────────────────────────────────
# 检查 6: 测距功能
# ─────────────────────────────────────────────────────────────────────────────

def check_ranging(comm: SerialComm, tag_addr: int = 0x0000,
                  duration: float = 10.0, verbose: bool = False):
    """配置 FIRA → 开启测距 → 采集 → 停止。

    返回: (result, aoa_frames, error_codes)
    """
    name = "测距功能"
    aoa_frames: List[AoaFrame] = []
    error_codes: list = []

    comm.drain()

    # FIRA 配置
    comm.send(cmd_fira_config(tag_addr=tag_addr))
    config_status = None
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and config_status is None:
        response = comm.receive(timeout=.5)
        if response is None or not response.crc_ok:
            continue
        for tlv in response.tlvs:
            ack = parse_response_tlv(tlv)
            if ack and ack[0] == 0x24:
                config_status = ack[1]
                break
    if config_status is None:
        return CheckResult(name=name, status=CheckStatus.FAIL,
                           detail='FIRA configuration not acknowledged; ranging not started'), [], []
    if config_status != 0:
        return CheckResult(name=name, status=CheckStatus.FAIL,
                           detail=f'FIRA configuration rejected: 0x{config_status:02X}'), [], []

    try:
        time.sleep(.3)
        comm.send(cmd_start_ranging())
        time.sleep(1.)
        packets = comm.receive_many(duration=duration)
        for pkt in packets:
            if not pkt.crc_ok:
                continue
            for tlv in pkt.tlvs:
                if tlv.type == TLV_AOA_DATA:
                    frame = parse_aoa_data(tlv, recv_time=time.monotonic())
                    if frame:
                        aoa_frames.append(frame)
                elif tlv.type == TLV_ERROR_STATUS:
                    code = parse_error_status(tlv)
                    if code is not None:
                        error_codes.append(code)
    finally:
        # A read exception or interruption must still attempt to stop our bench session.
        comm.send(cmd_stop_ranging())
        comm.receive(timeout=1.)

    if not aoa_frames:
        return CheckResult(name=name, status=CheckStatus.FAIL,
                           detail=f"{duration:.0f}s 内无 AoA 数据 (Tag 未连接/未配对?)",
                           data={"frame_count": 0}), aoa_frames, error_codes

    return CheckResult(name=name, status=CheckStatus.PASS,
                       detail=f"{duration:.0f}s 采集 {len(aoa_frames)} 帧",
                       data={"frame_count": len(aoa_frames)}), aoa_frames, error_codes


# ─────────────────────────────────────────────────────────────────────────────
# 检查 7: 数据质量
# ─────────────────────────────────────────────────────────────────────────────

def check_data_quality(aoa_frames: List[AoaFrame], duration: float = 10.0,
                       min_frame_rate: Optional[float] = None) -> CheckResult:
    """Report all samples; acceptance rate must come from the bench configuration."""
    name = '数据质量'
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('duration must be finite and positive')
    if min_frame_rate is not None and (not math.isfinite(min_frame_rate) or min_frame_rate <= 0):
        raise ValueError('min_frame_rate must be finite and positive')
    if len(aoa_frames) < 5:
        return CheckResult(name=name, status=CheckStatus.SKIP, detail='AoA 数据不足')
    invalid = [index for index, frame in enumerate(aoa_frames)
               if not all(math.isfinite(value) for value in (frame.distance, frame.angle, frame.pitch))
               or frame.distance <= 0
               or (frame.pos_confidence is not None and not math.isfinite(frame.pos_confidence))]
    if invalid:
        return CheckResult(name=name, status=CheckStatus.FAIL,
                           detail=f'{len(invalid)}/{len(aoa_frames)} 帧字段无效', data={'invalid_indices': invalid})
    distances = [frame.distance for frame in aoa_frames]
    angles = [math.radians(frame.angle) for frame in aoa_frames]
    confidences = [frame.pos_confidence for frame in aoa_frames if frame.pos_confidence is not None]
    sine, cosine = sum(map(math.sin, angles)), sum(map(math.cos, angles))
    rate = len(aoa_frames) / duration
    data = dict(total_frames=len(aoa_frames), observed_frames_per_requested_second=rate,
                avg_distance=statistics.mean(distances), distance_std=statistics.stdev(distances),
                circular_mean_angle=math.degrees(math.atan2(sine, cosine)) if math.hypot(sine, cosine) > 1e-9 else None,
                avg_confidence=statistics.mean(confidences) if confidences else None,
                missing_confidence_frames=len(aoa_frames)-len(confidences), min_frame_rate=min_frame_rate)
    status = CheckStatus.WARN if min_frame_rate is None or len(confidences) != len(aoa_frames) else CheckStatus.PASS
    if min_frame_rate is not None and rate < min_frame_rate:
        status = CheckStatus.FAIL
    return CheckResult(name=name, status=status,
                       detail=f'{len(aoa_frames)} 帧字段有效；窗口计数 {rate:.2f}/s；未验证定位精度；最低帧率要求={min_frame_rate}',
                       data=data)


# ─────────────────────────────────────────────────────────────────────────────
# 检查 10: CRC 校验完整性
# ─────────────────────────────────────────────────────────────────────────────

def check_crc_integrity(comm: SerialComm) -> CheckResult:
    name = "CRC 校验完整性"
    total = comm.total_packets_received
    errors = comm.crc_errors
    malformed = getattr(comm, 'protocol_errors', 0)
    if malformed:
        return CheckResult(name=name, status=CheckStatus.FAIL,
                           detail=f'{malformed}/{total} TLV frames malformed',
                           data={'total': total, 'errors': errors, 'malformed': malformed})
    if total == 0:
        return CheckResult(name=name, status=CheckStatus.SKIP, detail="无数据包")
    if errors > 0:
        return CheckResult(name=name, status=CheckStatus.FAIL,
                           detail=f"{errors}/{total} CRC 失败 ({errors/total*100:.1f}%)",
                           data={"total": total, "errors": errors})
    return CheckResult(name=name, status=CheckStatus.PASS,
                       detail=f"0/{total} CRC 失败", data={"total": total, "errors": 0})


# ─────────────────────────────────────────────────────────────────────────────
# 检查 11: 测距恢复
# ─────────────────────────────────────────────────────────────────────────────

def check_ranging_recovery(comm: SerialComm, tag_addr: int = 0x0000,
                           verbose: bool = False) -> CheckResult:
    name = "测距恢复"
    comm.drain()
    comm.send(cmd_stop_ranging())
    time.sleep(0.5)
    comm.drain()

    result, frames, _ = check_ranging(comm, tag_addr=tag_addr, duration=5., verbose=verbose)
    if result.status != CheckStatus.PASS:
        return CheckResult(name=name, status=result.status, detail=result.detail, data=result.data)
    if len(frames) < 3:
        return CheckResult(name=name, status=CheckStatus.FAIL, detail=f'二次启动仅 {len(frames)} 帧')
    return CheckResult(name=name, status=CheckStatus.PASS,
                       detail=f'二次启动正常, {len(frames)} 帧', data={'frame_count': len(frames)})
