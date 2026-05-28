#!/usr/bin/env python3
"""
UWB 固件冒烟测试工具

两种模式:
  standalone - 停止 uwb 服务，直接操作串口验证 Anchor (D6) 固件
  online     - 通过 ROS2 接口在线检查 Anchor + Tag + 测距

用法:
  python3 uwb_smoke_test.py --mode standalone --serial-port /dev/ttyS7
  python3 uwb_smoke_test.py --mode online
"""

import argparse
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report import SmokeTestReport, CheckResult, CheckStatus


def _print_result(result: CheckResult):
    icons = {
        CheckStatus.PASS: "✅",
        CheckStatus.FAIL: "❌",
        CheckStatus.WARN: "⚠️ ",
        CheckStatus.SKIP: "⏭️ ",
    }
    print(f"  {icons.get(result.status, '?')} {result.detail}")
    print()


def run_standalone(args):
    """Standalone 模式：停服务，直接串口验证 Anchor 固件。"""
    from serial_comm import SerialComm
    from checks_standalone import (
        check_serial_and_version,
        check_anchor_reboot,
        check_heartbeat_and_errors,
        check_crc_integrity,
    )

    report = SmokeTestReport(mode="standalone",
                             timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    comm = SerialComm(port=args.serial_port)
    if not comm.open():
        print(f"❌ 无法打开串口 {args.serial_port}")
        print("   请确认:")
        print("   1. uwb 服务已停止: systemctl stop uwb")
        print(f"   2. 串口设备存在: ls -la {args.serial_port}")
        sys.exit(1)
    print(f"📡 串口 {args.serial_port} 已打开\n")

    total = 6  # 串口通信, 版本, 重启恢复, 心跳, 错误状态, CRC
    n = [0]

    def step(label):
        n[0] += 1
        print(f"[{n[0]}/{total}] {label}...")

    # 1+2: 串口通信 + Anchor 版本
    step("检查串口通信 + Anchor 版本")
    serial_r, version_r, anchor_ver = check_serial_and_version(comm, verbose=args.verbose)
    report.add(serial_r); _print_result(serial_r)
    report.add(version_r); _print_result(version_r)
    if anchor_ver:
        report.anchor_version = str(anchor_ver)
    n[0] += 1

    # 3: Anchor 重启恢复
    step("检查 Anchor 重启恢复")
    r = check_anchor_reboot(comm, verbose=args.verbose)
    report.add(r); _print_result(r)

    # 4+5: 心跳 + 错误状态
    step("检查 Anchor 心跳 + 错误状态")
    hb_r, err_r = check_heartbeat_and_errors(comm, duration=5.0, verbose=args.verbose)
    report.add(hb_r); _print_result(hb_r)
    report.add(err_r); _print_result(err_r)
    n[0] += 1

    # 6: CRC 完整性
    step("检查 CRC 校验完整性")
    r = check_crc_integrity(comm)
    report.add(r); _print_result(r)

    comm.close()
    return report


def run_online(args):
    """Online 模式：不停服务，通过 ROS2 接口检查 Anchor + Tag + 测距。"""
    from checks_online import (
        check_anchor_version_online,
        check_tag_version_online,
        check_uwb_status_online,
        check_ranging_online,
        check_data_quality_online,
        check_error_status_online,
    )

    report = SmokeTestReport(mode="online",
                             timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    import shutil
    if not shutil.which("ros2"):
        print("❌ 未找到 ros2 命令，请 source ROS2 环境")
        sys.exit(1)

    print("🔍 Online 模式：通过 ROS2 接口检查 (不停服务)\n")

    print("[1/6] 检查 Anchor 版本...")
    r, v = check_anchor_version_online()
    report.add(r)
    if v: report.anchor_version = v
    _print_result(r)

    print("[2/6] 检查 Tag 版本...")
    r, v = check_tag_version_online()
    report.add(r)
    if v: report.tag_version = v
    _print_result(r)

    print("[3/6] 检查 Tag 状态/电量...")
    r = check_uwb_status_online()
    report.add(r); _print_result(r)

    print(f"[4/6] 检查测距功能 ({args.ranging_duration}s)...")
    r, _ = check_ranging_online(duration=args.ranging_duration)
    report.add(r); _print_result(r)

    print(f"[5/6] 检查数据质量 ({args.ranging_duration}s)...")
    r = check_data_quality_online(duration=args.ranging_duration)
    report.add(r); _print_result(r)

    print("[6/6] 检查错误状态...")
    r = check_error_status_online()
    report.add(r); _print_result(r)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="UWB 固件冒烟测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Standalone — 仅验证 Anchor (D6) 固件 (需先 systemctl stop uwb)
  python3 uwb_smoke_test.py --mode standalone
  python3 uwb_smoke_test.py --mode standalone --serial-port /dev/ttyS7

  # Online — 验证 Anchor + Tag + 测距 (不停服务)
  python3 uwb_smoke_test.py --mode online
  python3 uwb_smoke_test.py --mode online --ranging-duration 15
        """,
    )
    parser.add_argument("--mode", choices=["standalone", "online"], required=True,
                        help="standalone: 停服务验证 Anchor | online: 不停服务全量检查")
    parser.add_argument("--serial-port", default="/dev/ttyS7",
                        help="串口设备路径 (standalone, 默认 /dev/ttyS7)")
    parser.add_argument("--ranging-duration", type=float, default=10.0,
                        help="测距采集时长秒 (online, 默认 10)")
    parser.add_argument("--output-dir", default=".", help="报告输出目录")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    print()
    print("=" * 56)
    print("  UWB 固件冒烟测试")
    print(f"  模式: {args.mode}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 56)
    print()

    report = run_standalone(args) if args.mode == "standalone" else run_online(args)

    report.print_report()
    filepath = report.save_json(args.output_dir)
    print(f"📄 报告已保存: {filepath}\n")

    sys.exit(1 if report.summary.get(CheckStatus.FAIL, 0) > 0 else 0)


if __name__ == "__main__":
    main()
