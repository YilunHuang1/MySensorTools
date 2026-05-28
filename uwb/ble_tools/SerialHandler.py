import struct
from enum import Enum
import serial
import threading
import queue
import time
from CmdBuilder import CmdEnum, CmdBuilder
from PacketParser import PacketParser
from crc16_utils import crc16_xmodem, swap_uint16
import rclpy
from rclpy.node import Node
from uwb_msg.msg import UWB
from std_msgs.msg import Header


class SerialHandler(Node):
    PACKET_HEAD0 = 0x55
    PACKET_HEAD1 = 0xAA

    def __init__(self, port='/dev/ttyS7', baudrate=115200, timeout=0.011):
        rclpy.init(args=None)
        super().__init__('uwb_iphone')

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.packet_queue = queue.Queue()
        self.ser = None
        self.tx_char_global = None
        self.session_id = bytes(4)
        self.uwb_pub = self.create_publisher(UWB, '/uwb/data', 10)
        self.quit = False

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
                            # print(f'crc_received {crc_received} crc_calculated {crc_calculated}')
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
            # print(f"Received rsp packet:")
            # print(' '.join(f'{b:02X}' for b in packet))

            metric_result = PacketParser.parse(packet)
            if metric_result is not None:
                msg = UWB()
                msg.header = Header()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.header.frame_id = "uwb_0"
                msg.distance = metric_result["distance"]
                msg.angle = metric_result["angle"]
                msg.pitch = metric_result["pitch"]
                msg.rssi = metric_result["rssi_values"]
                msg.rssi_len = metric_result["rssi_len"]
                self.uwb_pub.publish(msg)
                print(f"rcv reported range data")

            
            # 这里可以调用 PacketParser.parse(packet) 等逻辑
            tlv = packet[5:]
            tlv_type = tlv[0] if tlv[0] != 0x00 else tlv[2]
            if tlv_type == 0x24:
                print("Set apple fira success")
                if self.tx_char_global is not None:
                    self.tx_char_global.Notify(bytearray([0x02]))
                cmdStartRanging = CmdBuilder.build(CmdEnum.START_RANGING, self.session_id)
                self.sendCmd(cmdStartRanging)
                time.sleep(0.1)
                # cmdDetectLivess = CmdBuilder.build(CmdEnum.DETECT_LIVENESS)
                # self.sendCmd(cmdDetectLivess)

            elif tlv_type == 0x07:
                tlv_len = tlv[1]
                cmd = tlv[2]
                if cmd == 0x02:
                    print(f"Received version response data:{tlv_len} ")

            self.packet_queue.task_done()
        return True

    def sendCmd(self, cmd):
        print(f"send cmd :{cmd.hex(' ')}")
        written = self.ser.write(cmd)
        if written == len(cmd):
            print("✅ 写入成功")
        else:
            print(f"⚠️ 写入字节数不匹配：{written} / {len(cmd)}")

# 示例使用
if __name__ == '__main__':
    handler = SerialHandler()
    handler.start()

    # 可定期调用：handler.process_packets()
