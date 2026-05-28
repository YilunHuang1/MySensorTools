#!/usr/bin/env python3
"""
vendor_b_verify.py - 供应商 B 锚点数据完整性验证
用法: python3 vendor_b_verify.py
"""
import serial, struct, time

PORT = '/dev/ttyS7'
BAUDRATE = 115200

def crc16_xmodem(data):
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def parse_c5(payload):
    """解析 0xC5 AoA 数据包"""
    try:
        offset = 2  # skip type+len
        sync_cnt = struct.unpack_from('<I', payload, offset)[0]; offset += 4
        mac_id   = struct.unpack_from('<I', payload, offset)[0]; offset += 4
        fob_id   = struct.unpack_from('<I', payload, offset)[0]; offset += 4
        fob_type = struct.unpack_from('<H', payload, offset)[0]; offset += 2
        distance = struct.unpack_from('<f', payload, offset)[0]; offset += 4
        angle    = struct.unpack_from('<f', payload, offset)[0]; offset += 4
        pitch    = struct.unpack_from('<f', payload, offset)[0]; offset += 4
        rssi_len = payload[offset]; offset += 1
        rssi_vals = list(payload[offset:offset+rssi_len]); offset += rssi_len
        rssi_rxp = struct.unpack_from('b', payload, offset)[0]; offset += 1
        rssi_fpp = struct.unpack_from('b', payload, offset)[0]; offset += 1
        confidence = payload[offset] if offset < len(payload) else -1
        return dict(distance=distance, angle=angle, pitch=pitch,
                    rssi_rxp=rssi_rxp, rssi_fpp=rssi_fpp,
                    confidence=confidence, mac_id=mac_id)
    except Exception as e:
        return None

def verify_data(d):
    """数据完整性检查"""
    issues = []
    if not (0.0 < d['distance'] < 30.0):
        issues.append(f"❌ 距离异常: {d['distance']:.3f}m (期望 0~30m)")
    else:
        issues.append(f"✅ 距离: {d['distance']:.3f}m")

    if not (-180 <= d['angle'] <= 180):
        issues.append(f"❌ 角度异常: {d['angle']:.1f}°")
    else:
        issues.append(f"✅ 角度: {d['angle']:.1f}°")

    if not (0 <= d['pitch'] <= 90):
        issues.append(f"❌ 俯仰角异常: {d['pitch']:.1f}°")
    else:
        issues.append(f"✅ 俯仰角: {d['pitch']:.1f}°")

    if d['confidence'] < 0:
        issues.append(f"⚠️  置信度字段缺失")
    elif d['confidence'] < 30:
        issues.append(f"❌ 置信度过低: {d['confidence']} (<30，信号差)")
    elif d['confidence'] < 50:
        issues.append(f"⚠️  置信度偏低: {d['confidence']} (建议>50)")
    else:
        issues.append(f"✅ 置信度: {d['confidence']}/100")

    if d['rssi_rxp'] < -100:
        issues.append(f"⚠️  信号强度弱: RxP={d['rssi_rxp']}dBm")
    else:
        issues.append(f"✅ 信号强度: RxP={d['rssi_rxp']}dBm, FPP={d['rssi_fpp']}dBm")

    return issues

def main():
    s = serial.Serial(PORT, BAUDRATE, timeout=0.1)
    print(f"✅ 串口 {PORT} 打开成功，开始监听 0xC5 数据包...")
    print("=" * 60)

    buf = bytearray()
    frame_count = 0
    error_count = 0
    start_time = time.time()
    last_frame_time = None
    fps_list = []

    try:
        while True:
            data = s.read(1024)
            if data:
                buf.extend(data)

            while len(buf) >= 7:
                if buf[0] == 0x55 and buf[1] == 0xAA:
                    tlv_total_len = struct.unpack_from('<H', buf, 3)[0]
                    packet_len = tlv_total_len + 7
                    if len(buf) < packet_len:
                        break

                    packet = buf[:packet_len]
                    crc_recv = struct.unpack_from('>H', packet, packet_len - 2)[0]
                    crc_calc = crc16_xmodem(packet[5:packet_len - 2])

                    if crc_recv != crc_calc:
                        print(f"❌ CRC 校验失败! recv=0x{crc_recv:04X} calc=0x{crc_calc:04X}")
                        error_count += 1
                        buf = buf[1:]
                        continue

                    buf = buf[packet_len:]
                    tlv = packet[5:]
                    tlv_type = tlv[0]

                    if tlv_type == 0xC5:
                        frame_count += 1
                        now = time.time()
                        if last_frame_time:
                            gap = now - last_frame_time
                            fps_list.append(1.0 / gap if gap > 0 else 0)
                        last_frame_time = now
                        fps = (sum(fps_list[-20:]) / len(fps_list[-20:])) if fps_list else 0

                        parsed = parse_c5(tlv)
                        if parsed:
                            print(f"\n──── 第 {frame_count} 帧 | FPS={fps:.1f} ────")
                            for line in verify_data(parsed):
                                print(f"  {line}")
                        else:
                            print(f"❌ 第 {frame_count} 帧解析失败")
                            error_count += 1

                    elif tlv_type == 0x59:
                        range_status = tlv[3] if len(tlv) > 3 else 0xFF
                        status_str = "测距中✅" if range_status == 0x03 else f"状态={range_status:#x}"
                        print(f"💓 心跳包 range_status={status_str}")

                    elif tlv_type == 0xC7:
                        code = tlv[2] if len(tlv) > 2 else 0xFF
                        CODE_MAP = {
                            0x00: "STATUS_OK",
                            0x20: "TX_FAILED 发送失败",
                            0x21: "RX_TIMEOUT 接收超时 ← 常见！Tag信号没收到",
                            0x22: "RX_PHY_DEC_FAILED 解码错误",
                            0x23: "RX_PHY_TOA_FAILED TOA失败",
                            0x24: "RX_PHY_STS_FAILED ← STS密钥不匹配！",
                            0x25: "RX_MAC_DEC_FAILED MAC CRC错误",
                            0xE4: "BASEBAND_ERROR 基带错误",
                            0xE8: "DISTANCE_FAIL 距离数据异常",
                            0xE9: "ANGLE_FAIL 角度数据异常",
                        }
                        desc = CODE_MAP.get(code, f"未知状态码 {code:#x}")
                        print(f"⚠️  错误状态 0xC7: {desc}")
                        error_count += 1

                    else:
                        pass  # 忽略其他 TLV
                else:
                    buf = buf[1:]

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        avg_fps = frame_count / elapsed if elapsed > 0 else 0
        print("\n" + "=" * 60)
        print(f"📊 测试结束汇总")
        print(f"  总帧数   : {frame_count}")
        print(f"  错误次数 : {error_count}")
        print(f"  运行时间 : {elapsed:.1f}s")
        print(f"  平均 FPS : {avg_fps:.1f}")
        if fps_list:
            print(f"  实时 FPS : {sum(fps_list[-20:])/len(fps_list[-20:]):.1f}")
        print("=" * 60)
        s.close()

if __name__ == '__main__':
    main()
