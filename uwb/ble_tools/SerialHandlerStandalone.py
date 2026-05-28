"""
SerialHandler standalone version - no ROS2 dependency.
Enhanced with diagnostics: FPS tracking, statistics, frame gap detection, CSV logging.
"""
import struct
import serial
import threading
import queue
import time
import csv
import os
from datetime import datetime
from collections import deque
from CmdBuilder import CmdEnum, CmdBuilder
from PacketParser import PacketParser
from crc16_utils import crc16_xmodem


class RangingStats:
    """实时统计测距数据"""

    def __init__(self, window_size=50):
        self.window_size = window_size
        self.timestamps = deque(maxlen=window_size)
        self.distances = deque(maxlen=window_size)
        self.angles = deque(maxlen=window_size)
        self.pitches = deque(maxlen=window_size)
        self.rssi_list = deque(maxlen=window_size)

        # 全局计数
        self.total_frames = 0
        self.start_time = None
        self.last_frame_time = None

        # 帧间隔统计
        self.frame_gaps = deque(maxlen=window_size)
        self.max_gap_ever = 0.0
        self.drop_count = 0  # gap > 2x 平均间隔的次数

        # 每秒统计
        self._last_report_time = None
        self._frames_since_report = 0

    def update(self, distance, angle, pitch, rssi_values=None):
        now = time.time()
        if self.start_time is None:
            self.start_time = now
            self._last_report_time = now

        # 帧间隔
        if self.last_frame_time is not None:
            gap = now - self.last_frame_time
            self.frame_gaps.append(gap)
            if gap > self.max_gap_ever:
                self.max_gap_ever = gap
            # 判断丢帧：间隔 > 正常间隔的 2.5 倍
            avg_gap = self.avg_gap()
            if avg_gap > 0 and gap > avg_gap * 2.5:
                self.drop_count += 1

        self.last_frame_time = now
        self.total_frames += 1
        self._frames_since_report += 1

        self.timestamps.append(now)
        self.distances.append(distance)
        self.angles.append(angle)
        self.pitches.append(pitch)
        if rssi_values is not None:
            self.rssi_list.append(rssi_values)

    def fps(self):
        """基于滑动窗口计算实时 FPS"""
        if len(self.timestamps) < 2:
            return 0.0
        dt = self.timestamps[-1] - self.timestamps[0]
        if dt <= 0:
            return 0.0
        return (len(self.timestamps) - 1) / dt

    def avg_gap(self):
        if not self.frame_gaps:
            return 0.0
        return sum(self.frame_gaps) / len(self.frame_gaps)

    def global_fps(self):
        if self.start_time is None or self.total_frames < 2:
            return 0.0
        dt = time.time() - self.start_time
        return self.total_frames / dt if dt > 0 else 0.0

    def distance_stats(self):
        if not self.distances:
            return None
        d = list(self.distances)
        return {
            'min': min(d),
            'max': max(d),
            'avg': sum(d) / len(d),
            'latest': d[-1],
            'std': self._std(d),
        }

    def angle_stats(self):
        if not self.angles:
            return None
        a = list(self.angles)
        return {
            'min': min(a),
            'max': max(a),
            'avg': sum(a) / len(a),
            'latest': a[-1],
            'std': self._std(a),
        }

    def pitch_stats(self):
        if not self.pitches:
            return None
        p = list(self.pitches)
        return {
            'min': min(p),
            'max': max(p),
            'avg': sum(p) / len(p),
            'latest': p[-1],
            'std': self._std(p),
        }

    def should_print_summary(self, interval=3.0):
        """每 interval 秒打印一次摘要"""
        if self._last_report_time is None:
            return False
        if time.time() - self._last_report_time >= interval:
            return True
        return False

    def get_summary_and_reset(self):
        """获取摘要并重置每秒计数"""
        fps = self.fps()
        global_fps = self.global_fps()
        d = self.distance_stats()
        a = self.angle_stats()
        p = self.pitch_stats()
        frames = self._frames_since_report
        elapsed = time.time() - self._last_report_time if self._last_report_time else 0
        period_fps = frames / elapsed if elapsed > 0 else 0

        self._last_report_time = time.time()
        self._frames_since_report = 0

        return {
            'fps': fps,
            'global_fps': global_fps,
            'period_fps': period_fps,
            'total_frames': self.total_frames,
            'distance': d,
            'angle': a,
            'pitch': p,
            'max_gap': self.max_gap_ever,
            'avg_gap': self.avg_gap(),
            'drop_count': self.drop_count,
            'period_frames': frames,
        }

    @staticmethod
    def _std(data):
        if len(data) < 2:
            return 0.0
        avg = sum(data) / len(data)
        variance = sum((x - avg) ** 2 for x in data) / (len(data) - 1)
        return variance ** 0.5


class CSVLogger:
    """将每帧测距数据记录到 CSV"""

    def __init__(self, filepath=None):
        if filepath is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"uwb_log_{ts}.csv"  # 使用当前目录
        self.filepath = filepath
        self.file = open(filepath, 'w', newline='')
        self.writer = csv.writer(self.file)
        self.writer.writerow([
            'timestamp', 'elapsed_s', 'frame_no', 'distance_m', 'angle_deg',
            'pitch_deg', 'fps', 'frame_gap_ms', 'rssi'
        ])
        self.start_time = time.time()
        self.frame_no = 0
        self.last_time = None
        print(f"📝 CSV logging to: {filepath}")

    def log(self, distance, angle, pitch, fps, rssi_values=None):
        now = time.time()
        elapsed = now - self.start_time
        gap_ms = (now - self.last_time) * 1000 if self.last_time else 0
        self.last_time = now
        self.frame_no += 1
        rssi_str = ','.join(str(r) for r in rssi_values) if rssi_values else ''
        self.writer.writerow([
            f"{now:.6f}", f"{elapsed:.3f}", self.frame_no,
            f"{distance:.4f}", f"{angle:.2f}", f"{pitch:.2f}",
            f"{fps:.1f}", f"{gap_ms:.1f}", rssi_str
        ])
        # 每 50 帧 flush 一次避免丢数据
        if self.frame_no % 50 == 0:
            self.file.flush()
    
    def write_summary(self, summary_text):
        """将摘要信息追加到日志文件"""
        # 创建对应的 .log 文件
        log_path = self.filepath.replace('.csv', '.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(summary_text + '\n')

    def close(self):
        self.file.flush()
        self.file.close()
        print(f"📝 CSV saved: {self.filepath} ({self.frame_no} frames)")


class SerialHandler:
    PACKET_HEAD0 = 0x55
    PACKET_HEAD1 = 0xAA

    def __init__(self, port='/dev/ttyS7', baudrate=115200, timeout=0.011,
                 enable_csv=True, csv_path=None, summary_interval=3.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.packet_queue = queue.Queue()
        self.ser = None
        self.tx_char_global = None
        self.session_id = bytes(4)
        self.quit = False

        # 统计 & 日志
        self.stats = RangingStats(window_size=100)
        self.csv_logger = CSVLogger(csv_path) if enable_csv else None
        self.summary_interval = summary_interval

    def start(self):
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            print(f"✅ Opened serial port {self.port} successfully.")
            threading.Thread(target=self.read_from_port, daemon=True).start()
        except serial.SerialException as e:
            print(f"❌ Failed to open {self.port}: {e}")

    def stop(self):
        if self.ser:
            self.ser.close()
        self.quit = True
        if self.csv_logger:
            self.csv_logger.close()
        self._print_final_summary()

    def _print_final_summary(self):
        s = self.stats
        if s.total_frames == 0:
            return
        elapsed = time.time() - s.start_time if s.start_time else 0
        d = s.distance_stats()
        
        summary_lines = []
        summary_lines.append("\n" + "=" * 60)
        summary_lines.append("  📊 最终统计摘要")
        summary_lines.append("=" * 60)
        summary_lines.append(f"  总帧数     : {s.total_frames}")
        summary_lines.append(f"  运行时间   : {elapsed:.1f}s")
        summary_lines.append(f"  平均 FPS   : {s.global_fps():.1f}")
        summary_lines.append(f"  丢帧次数   : {s.drop_count}")
        summary_lines.append(f"  最大帧间隔 : {s.max_gap_ever * 1000:.1f}ms")
        if d:
            summary_lines.append(f"  距离范围   : {d['min']:.3f}m ~ {d['max']:.3f}m")
            summary_lines.append(f"  距离均值±σ : {d['avg']:.3f}m ± {d['std']:.3f}m")
        if self.csv_logger:
            summary_lines.append(f"  CSV 文件   : {self.csv_logger.filepath}")
        summary_lines.append("=" * 60)
        
        summary_text = '\n'.join(summary_lines)
        print(summary_text)
        
        # 写入日志文件
        if self.csv_logger:
            self.csv_logger.write_summary(summary_text)

    def read_from_port(self):
        buffer = bytearray()
        while True:
            if self.quit:
                break
            data = self.ser.read(1024)
            if data:
                buffer.extend(data)
                while len(buffer) >= 7:
                    if buffer[0] == self.PACKET_HEAD0 and buffer[1] == self.PACKET_HEAD1:
                        tlv_total_len = struct.unpack_from('<H', buffer, 3)[0]
                        packet_len = tlv_total_len + 7
                        if len(buffer) >= packet_len:
                            packet = buffer[:packet_len]
                            crc_received = struct.unpack_from('>H', packet, packet_len - 2)[0]
                            crc_calculated = crc16_xmodem(packet[5:packet_len - 2])
                            if crc_received == crc_calculated:
                                self.packet_queue.put(packet)
                                buffer = buffer[packet_len:]
                            else:
                                print("check crc failed")
                                buffer = buffer[1:]
                        else:
                            break
                    else:
                        buffer = buffer[1:]
            else:
                time.sleep(0.01)

    def process_packets(self):
        while not self.packet_queue.empty():
            packet = self.packet_queue.get()

            metric_result = PacketParser.parse(packet)
            if metric_result is not None:
                dist = metric_result['distance']
                angle = metric_result['angle']
                pitch = metric_result['pitch']
                rssi = metric_result.get('rssi_values')

                # 更新统计
                self.stats.update(dist, angle, pitch, rssi)
                fps = self.stats.fps()

                # 逐帧打印（含 FPS）
                gap_ms = (self.stats.frame_gaps[-1] * 1000) if self.stats.frame_gaps else 0
                print(f"📏 d={dist:.3f}m  ang={angle:.1f}°  pitch={pitch:.1f}°  "
                      f"FPS={fps:.1f}  gap={gap_ms:.0f}ms  "
                      f"#={self.stats.total_frames}")

                # CSV 记录
                if self.csv_logger:
                    self.csv_logger.log(dist, angle, pitch, fps, rssi)

                # 定时摘要
                if self.stats.should_print_summary(self.summary_interval):
                    self._print_periodic_summary()

            # 处理 UWB 控制 TLV
            tlv = packet[5:]
            tlv_type = tlv[0] if tlv[0] != 0x00 else tlv[2]
            if tlv_type == 0x24:
                print("Set apple fira success")
                if self.tx_char_global is not None:
                    self.tx_char_global.Notify(bytearray([0x02]))
                cmdStartRanging = CmdBuilder.build(CmdEnum.START_RANGING, self.session_id)
                self.sendCmd(cmdStartRanging)
                time.sleep(0.1)
            elif tlv_type == 0x07:
                tlv_len = tlv[1]
                cmd = tlv[2]
                if cmd == 0x02:
                    print(f"Received version response data:{tlv_len}")

            self.packet_queue.task_done()
        return True

    def _print_periodic_summary(self):
        s = self.stats.get_summary_and_reset()
        d = s['distance']
        a = s['angle']
        p = s['pitch']
        
        summary_lines = []
        summary_lines.append("\n┌─────────────────── 📊 周期统计 ───────────────────┐")
        summary_lines.append(f"│ 时间: {datetime.now().strftime('%H:%M:%S')}")
        summary_lines.append(f"│ FPS: 实时={s['fps']:.1f}  周期={s['period_fps']:.1f}  "
              f"全局={s['global_fps']:.1f}  (周期{s['period_frames']}帧)")
        if d:
            summary_lines.append(f"│ 距离: {d['latest']:.3f}m  "
                  f"[{d['min']:.3f} ~ {d['max']:.3f}]  "
                  f"avg={d['avg']:.3f}±{d['std']:.3f}m")
        if a:
            summary_lines.append(f"│ 角度: {a['latest']:.1f}°  "
                  f"[{a['min']:.1f} ~ {a['max']:.1f}]  "
                  f"avg={a['avg']:.1f}±{a['std']:.1f}°")
        if p:
            summary_lines.append(f"│ 俯仰: {p['latest']:.1f}°  "
                  f"[{p['min']:.1f} ~ {p['max']:.1f}]  "
                  f"avg={p['avg']:.1f}±{p['std']:.1f}°")
        summary_lines.append(f"│ 帧间隔: avg={s['avg_gap']*1000:.1f}ms  "
              f"max_ever={s['max_gap']*1000:.1f}ms  "
              f"丢帧={s['drop_count']}次")
        summary_lines.append(f"│ 总帧数: {s['total_frames']}")
        summary_lines.append("└───────────────────────────────────────────────────┘\n")
        
        summary_text = '\n'.join(summary_lines)
        print(summary_text)
        
        # 写入日志文件
        if self.csv_logger:
            self.csv_logger.write_summary(summary_text)

    def sendCmd(self, cmd):
        print(f"send cmd :{cmd.hex(' ')}")
        written = self.ser.write(cmd)
        if written == len(cmd):
            print("✅ 写入成功")
        else:
            print(f"⚠️ 写入字节数不匹配：{written} / {len(cmd)}")


if __name__ == '__main__':
    handler = SerialHandler()
    handler.start()
