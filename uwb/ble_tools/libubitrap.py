import serial
import threading
import queue
import struct
import time
from gi.repository import GLib
from crc16_utils import crc16_xmodem, swap_uint16
from PacketParser import PacketParser
from CmdBuilder import CmdEnum, CmdBuilder

# 串口配置参数
PORT = '/dev/ttyUSB0'  # Linux下为 /dev/ttyUSBx 或 /dev/ttySx，Windows下如 COM3
BAUDRATE = 115200
BYTESIZE = serial.EIGHTBITS
PARITY = serial.PARITY_NONE
STOPBITS = serial.STOPBITS_ONE
TIMEOUT = 0.011  # 读超时秒数

# 定义包头标志
PACKET_HEAD0 = 0x55
PACKET_HEAD1 = 0xAA

# 创建线程安全的队列
packet_queue = queue.Queue()

def read_from_port(ser):
    buffer = bytearray()
    while True:
        data = ser.read(1024)
        if data:
            buffer.extend(data)
            # print(f"receive:{data}")
            while len(buffer) >= 7:
                if buffer[0] == PACKET_HEAD0 and buffer[1] == PACKET_HEAD1:
                    # 提取 TLV 总长度（小端格式）
                    tlv_total_len = struct.unpack_from('<H', buffer, 3)[0]
                    packet_len = tlv_total_len + 7
                    if len(buffer) >= packet_len:
                        packet = buffer[:packet_len]
                        # 校验 CRC
                        crc_received = struct.unpack_from('>H', packet, packet_len - 2)[0]
                        crc_calculated = crc16_xmodem(packet[5:packet_len - 2])
                        print(f"{crc_received} {crc_calculated}")
                        if crc_received == crc_calculated:
                            # 将完整的数据包放入队列
                            packet_queue.put(packet)
                            buffer = buffer[packet_len:]
                        else:
                            print("check crc failed")
                            # CRC 校验失败，丢弃当前包头
                            buffer = buffer[1:]
                    else:
                        # 数据不足，等待更多数据
                        break
                else:
                    # 找不到包头，丢弃第一个字节
                    buffer = buffer[1:]
        else:
            time.sleep(0.01)

def process_packets(tx_char_global):
    # print("tick process_packets")
    while not packet_queue.empty():
        packet = packet_queue.get()
        print(f"Received rsp packet:")
        print(' '.join(f'{b:02X}' for b in packet))
        
        metric_result = PacketParser.parse(packet)
        if metric_result is not None:
            print(f"ranging data: {metric_result}")

        # 在此处添加对 packet 的处理逻辑
        tlv = packet[5:]
        tlv_type = tlv[0] if tlv[0] != 0x00 else tlv[2]
        if tlv_type == 0x24 :
            print ("Set apple fira success")
            if tx_char_global is not None:
                tx_char_global.Notify(bytearray([0x02]))
            cmdStartRanging = CmdBuilder.build(CmdEnum.START_RANGING, session_id)
            sendCmd(cmdStartRanging)

        elif tlv_type == 0x07:
            tlv_len = tlv[1]
            cmd = tlv[2]
            if cmd == 0x02:
                print(f"Received version response data:{tlv_len} ")

        packet_queue.task_done()
    return True  # 返回 True 以继续调用

def sendCmd(cmd):
    print(f"send cmd :{cmd.hex(' ')}")  # 输出: 01 02 0a ff
    written = ser.write(cmd)
    if written == len(cmd):
        print("✅ 写入成功")
    else:
        print(f"⚠️ 写入字节数不匹配：{written} / {len(cmd)}")

def startSerial():
    global ser
    try:
        ser = serial.Serial(
            port=PORT,
            baudrate=BAUDRATE,
            bytesize=BYTESIZE,
            parity=PARITY,
            stopbits=STOPBITS,
            timeout=TIMEOUT
        )
        print(f"✅ Opened serial port {PORT} successfully.")
        # 开启读取线程
        threading.Thread(target=read_from_port, args=(ser,), daemon=True).start()
    except serial.SerialException as e:
        print(f"❌ Failed to open {PORT}: {e}")

def closeSerial():
    try:
        ser.close()
    except serial.SerialException as e:
        print(f"❌ Failed to open {PORT}: {e}")

def main():
    global ser
    try:
        ser = serial.Serial(
            port=PORT,
            baudrate=BAUDRATE,
            bytesize=BYTESIZE,
            parity=PARITY,
            stopbits=STOPBITS,
            timeout=TIMEOUT
        )
        print(f"✅ Opened serial port {PORT} successfully.")

        # 开启读取线程
        threading.Thread(target=read_from_port, args=(ser,), daemon=True).start()
        # ret = GLib.timeout_add(10, process_packets)
        # print(f"glib add timeout {ret}")
        # mainloop = GLib.MainLoop()
        # mainloop.run()
        # 主线程循环输入并写入串口
        while True:
            to_send = input("📤 Enter data to send: ")
            input_cmd = to_send.strip().lower()

            if input_cmd == 'exit':
                break

            if input_cmd == 'version':
                get_version_cmd = CmdBuilder.build(CmdEnum.GET_VERSION)
                sendCmd(get_version_cmd)

            if input_cmd == 'fira':
                hex_str = "0b0100010019434e3ec100000b090600100ec600036ae1eb7e398fee33c800"
                sharedConfig = bytes.fromhex(hex_str)
                print(f"shared config: {sharedConfig.hex(' ')}")
                fira_apple_cmd = CmdBuilder.build(CmdEnum.SET_APPLE_FIRA, sharedConfig)
                print(fira_apple_cmd.hex(' '))  # 输出: 01 02 0a ff
                sendCmd(fira_apple_cmd)

            process_packets(None)
                
        ser.close()
        print("🔌 Serial port closed.")

    except serial.SerialException as e:
        print(f"❌ Failed to open {PORT}: {e}")

if __name__ == "__main__":
    main()
