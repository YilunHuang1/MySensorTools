"""
Online 模式检查项：通过 ROS2 CLI 接口进行，不停止 uwb_node。
"""

import subprocess
import json
import time
import re
import signal
import os
import statistics
from typing import Optional, List
from dataclasses import dataclass

from protocol import MIN_ANCHOR_VERSION, MIN_TAG_VERSION, AnchorVersion, TagVersion
from report import CheckResult, CheckStatus


# Zenoh 连接启动约需 1-2s，所有 ROS2 CLI 命令需要足够的超时
_ZENOH_STARTUP_S = 5


def _run_cmd(cmd: list, timeout: float = 30.0) -> tuple[int, str, str]:
    """运行命令返回 (returncode, stdout, stderr)。stderr 中的 zenoh 日志被过滤。"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def _ros2_service_call(service: str, srv_type: str, args: str = "{}", timeout: float = 30.0) -> tuple[bool, str]:
    """调用 ROS2 service，返回 (success, output)。"""
    cmd = ["ros2", "service", "call", service, srv_type, args]
    rc, stdout, stderr = _run_cmd(cmd, timeout=timeout)
    if rc != 0:
        return False, stderr or stdout
    return True, stdout


def _popen_collect(cmd: list, duration: float) -> str:
    """
    启动进程，采集 duration 秒后强制终止，返回 stdout 内容。
    边读边采集，避免管道缓冲区满导致子进程阻塞死锁。
    """
    import select
    import fcntl

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,  # 新进程组，方便整组 kill
    )

    # 设置 stdout 为非阻塞
    fd = proc.stdout.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    # 边读边采集，持续 duration 秒
    output = b""
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.5)
        if ready:
            try:
                chunk = os.read(fd, 65536)
                if chunk:
                    output += chunk
            except BlockingIOError:
                pass

    # 采集结束，再读一次残留数据
    try:
        chunk = os.read(fd, 65536)
        if chunk:
            output += chunk
    except (BlockingIOError, OSError):
        pass

    # 强制终止进程组
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        pass
    return output.decode("utf-8", errors="replace")


# ── Checks ───────────────────────────────────────────────────────────────────

def check_anchor_version_online() -> tuple[CheckResult, Optional[str]]:
    """检查 2: Anchor 版本 (online)。"""
    name = "Anchor 版本"

    ok, output = _ros2_service_call(
        "/firmware_version/uwb",
        "firmware_version_msgs/srv/GetFirmwareVersion",
        "{target_device_type: 3}",
    )

    if not ok:
        return CheckResult(name=name, status=CheckStatus.FAIL, detail=f"Service 调用失败: {output}"), None

    # 解析版本 - 输出为 Python repr 格式:
    # name='uwb_anchor', ..., sw_version='5.1.35'
    anchor_ver = None
    anchor_match = re.search(r"name='uwb_anchor'.*?sw_version='([^']+)'", output, re.DOTALL)
    if anchor_match:
        anchor_ver = anchor_match.group(1)

    if anchor_ver is None or anchor_ver == "unknown":
        return CheckResult(name=name, status=CheckStatus.FAIL, detail="Anchor 版本未知 (设备可能未连接)"), None

    # 版本比较
    try:
        parts = [int(x) for x in anchor_ver.split(".")]
        if tuple(parts) < MIN_ANCHOR_VERSION:
            min_str = ".".join(str(x) for x in MIN_ANCHOR_VERSION)
            return CheckResult(
                name=name, status=CheckStatus.FAIL,
                detail=f"{anchor_ver} < {min_str}",
            ), anchor_ver
    except ValueError:
        pass

    return CheckResult(
        name=name, status=CheckStatus.PASS,
        detail=f"{anchor_ver}",
        data={"version": anchor_ver},
    ), anchor_ver


def check_tag_version_online() -> tuple[CheckResult, Optional[str]]:
    """检查 5: Tag 版本 (online)。"""
    name = "Tag 版本"

    ok, output = _ros2_service_call(
        "/firmware_version/uwb",
        "firmware_version_msgs/srv/GetFirmwareVersion",
        "{target_device_type: 3}",
    )

    if not ok:
        return CheckResult(name=name, status=CheckStatus.FAIL, detail=f"Service 调用失败: {output}"), None

    tag_match = re.search(r"name='uwb_tag'.*?sw_version='([^']+)'", output, re.DOTALL)
    tag_ver = tag_match.group(1) if tag_match else None

    if tag_ver is None or tag_ver == "unknown":
        return CheckResult(name=name, status=CheckStatus.WARN, detail="Tag 版本未知 (BLE 可能未连接)"), None

    try:
        parts = [int(x) for x in tag_ver.split(".")]
        if tuple(parts) < MIN_TAG_VERSION:
            min_str = ".".join(str(x) for x in MIN_TAG_VERSION)
            return CheckResult(
                name=name, status=CheckStatus.FAIL,
                detail=f"{tag_ver} < {min_str}",
            ), tag_ver
    except ValueError:
        pass

    return CheckResult(
        name=name, status=CheckStatus.PASS,
        detail=f"SW {tag_ver}",
        data={"version": tag_ver},
    ), tag_ver


def check_uwb_status_online() -> CheckResult:
    """检查 9: UWB 状态/电量 (online) — 从 /uwb/state topic 读取。"""
    name = "Tag 状态/电量"

    # 使用 Popen 采集，给 zenoh 足够的连接时间
    collect_s = _ZENOH_STARTUP_S + 3  # zenoh 启动 + 等 1Hz 消息
    stdout = _popen_collect(
        ["ros2", "topic", "echo", "--once", "/uwb/state", "uwb_msgs/msg/Status"],
        duration=collect_s,
    )

    if not stdout.strip():
        return CheckResult(name=name, status=CheckStatus.FAIL, detail=f"无法读取 /uwb/state ({collect_s}s 超时)")

    # 解析关键字段
    battery = None
    state = None
    charging = None

    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("battery_percentage:"):
            try:
                battery = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("state:"):
            try:
                state = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("is_charging:"):
            charging = "true" in line.lower()

    details = []
    warnings = []

    if battery is not None:
        details.append(f"电量 {battery}%")
        if battery < 10:
            warnings.append("电量过低")
    else:
        details.append("电量未知")

    state_names = {0: "IDLE", 1: "CONNECTED", 2: "RANGING"}
    if state is not None:
        details.append(f"状态 {state_names.get(state, str(state))}")

    if charging:
        details.append("充电中")

    status = CheckStatus.WARN if warnings else CheckStatus.PASS
    return CheckResult(
        name=name, status=status,
        detail=", ".join(details),
        data={"battery": battery, "state": state, "is_charging": charging},
    )


def check_ranging_online(duration: float = 10.0) -> tuple[CheckResult, Optional[float]]:
    """检查 6: 测距功能 (online) — 通过 ros2 topic hz 获取帧率。"""
    name = "测距功能"

    # 使用 Popen 采集帧率，duration 要加上 zenoh 启动时间
    total_s = _ZENOH_STARTUP_S + duration
    stdout = _popen_collect(
        ["ros2", "topic", "hz", "/uwb/data"],
        duration=total_s,
    )

    # 解析 "average rate: 20.05"
    hz = None
    for line in stdout.splitlines():
        m = re.search(r'average rate:\s*([\d.]+)', line)
        if m:
            hz = float(m.group(1))

    if hz is None or hz < 1.0:
        return CheckResult(
            name=name, status=CheckStatus.WARN,
            detail=f"帧率: {hz if hz else '无数据'} (可能未在测距中)",
        ), hz

    status = CheckStatus.PASS if hz >= 12.0 else CheckStatus.WARN
    return CheckResult(
        name=name, status=status,
        detail=f"帧率 {hz:.1f}Hz" + (" (< 12Hz)" if hz < 12.0 else ""),
        data={"frame_rate": round(hz, 1)},
    ), hz


def check_data_quality_online(duration: float = 5.0) -> CheckResult:
    """检查 7: 数据质量 (online) — 通过 echo 多条消息。"""
    name = "数据质量"

    total_s = _ZENOH_STARTUP_S + duration
    stdout = _popen_collect(
        ["ros2", "topic", "echo", "/uwb/data", "uwb_location/msg/UWB"],
        duration=total_s,
    )

    # 解析 distance, angle, pos_confidence
    distances = []
    angles = []
    confidences = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("distance_filtered:"):
            try:
                val = float(line.split(":")[1].strip())
                if 0 < val < 100:
                    distances.append(val)
            except ValueError:
                pass
        elif line.startswith("angle_filtered:"):
            try:
                val = float(line.split(":")[1].strip())
                angles.append(val)
            except ValueError:
                pass
        elif line.startswith("pos_confidence:"):
            try:
                val = int(line.split(":")[1].strip())
                confidences.append(val)
            except ValueError:
                pass

    if not distances:
        return CheckResult(name=name, status=CheckStatus.SKIP, detail="无有效数据 (可能未在测距)")

    details = []
    warnings = []

    avg_dist = statistics.mean(distances)
    avg_angle = statistics.mean(angles) if angles else 0
    avg_conf = statistics.mean(confidences) if confidences else 0
    dist_std = statistics.stdev(distances) if len(distances) > 1 else 0

    details.append(f"采集 {len(distances)} 帧")
    details.append(f"距离均值 {avg_dist:.2f}m")
    details.append(f"角度均值 {avg_angle:.1f}°")
    details.append(f"confidence 均值 {avg_conf:.0f}")
    if avg_conf < 50 and confidences:
        warnings.append("置信度偏低")

    details.append(f"距离标准差 {dist_std:.2f}m")
    if dist_std > 0.5:
        warnings.append("距离抖动大")

    status = CheckStatus.WARN if warnings else CheckStatus.PASS
    return CheckResult(
        name=name, status=status,
        detail="; ".join(details),
        data={
            "frame_count": len(distances),
            "avg_distance": round(avg_dist, 3),
            "avg_angle": round(avg_angle, 1),
            "avg_confidence": round(avg_conf, 1),
            "distance_std": round(dist_std, 3),
        },
    )


def check_error_status_online() -> CheckResult:
    """检查 8: 错误状态 (online) — 读取 /uwb/state 确认状态正常。"""
    name = "错误状态"

    stdout = _popen_collect(
        ["ros2", "topic", "echo", "--once", "/uwb/state", "uwb_msgs/msg/Status"],
        duration=_ZENOH_STARTUP_S + 3,
    )

    if not stdout.strip():
        return CheckResult(name=name, status=CheckStatus.WARN, detail="无法读取状态")

    return CheckResult(name=name, status=CheckStatus.PASS, detail="无异常状态上报")
