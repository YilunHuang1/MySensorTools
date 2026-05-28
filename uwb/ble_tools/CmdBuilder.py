
from enum import Enum, IntEnum, auto
from crc16_utils import crc16_xmodem, swap_uint16

class CmdEnum(Enum):
    GET_VERSION = 1
    SET_APPLE_FIRA = 2 #For iPhone UWB
    SET_FIRA = 3
    START_RANGING = 4
    STOP_RANGING = 5
    UWB_CONFIGURE_DATA = 6

class CmdBuilder:
    @staticmethod
    def build(cmd, params = None):
        if cmd == CmdEnum.GET_VERSION:
            return CmdBuilder.build_get_version_cmd()
        elif cmd == CmdEnum.SET_APPLE_FIRA:
            if params is None:
                raise ValueError("Parameters required for SET_APPLE_FIRA")
            return CmdBuilder.build_apple_fira_cmd(params)
        elif cmd == CmdEnum.SET_FIRA:
            if params is None:
                raise ValueError("Parameters sesssion_id required for SET_APPLE_FIRA")
            return CmdBuilder.build_fira_cmd(params)
        elif cmd == CmdEnum.START_RANGING:
            if params is None:
                raise ValueError("Parameters sesssion_id required for START_RANGING")
            return CmdBuilder.build_start_ranging_cmd(params)
        elif cmd == CmdEnum.STOP_RANGING:
            if params is None:
                raise ValueError("Parameter sesssion_id required for STOP_RANGING")
            return CmdBuilder.build_stop_ranging_cmd()
        elif cmd == CmdEnum.UWB_CONFIGURE_DATA:
            return CmdBuilder.build_accessory_configuration_data_cmd()
        else:
            return None

    @staticmethod
    def build_accessory_configuration_data_cmd()->bytes:
        cmd = bytes([0x01, 
                0x01, 0x00, 0x00, 0x00, 
                0x14,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
                0x00, 0x00, 0x00, 
                0x15, 
                0x01, 0x00, 
                0x01, 0x00, 
                0x3f, 0xf5, 0x03, 0x00, 
                0xb8, 0x0b, 0x00, 0x00, 
                0x00, 0x00, 0x01, 0x01,
                0x00, 
                0xd9, 0x36, 
                0x19, 0x00])
        return cmd

    @staticmethod
    def build_get_version_cmd()-> bytes:
        cmd = bytearray(11)
        # 固定部分
        cmd[0] = 0x55  # header
        cmd[1] = 0xAA
        cmd[2] = 0x00  # seq
        cmd[3] = 0x04  # tlv_total_len (小端，2字节)
        cmd[4] = 0x00
        cmd[5] = 0x07  # TLV type
        cmd[6] = 0x02  # TLV length
        cmd[7] = 0x01  # CMD = 0x01
        cmd[8] = 0x11  # GET_TYPE = 0x11

        # 计算 CRC（只计算 TLV 部分：cmd[5] 到 cmd[8]）
        crc = crc16_xmodem(cmd[5:9])
        crc_be = swap_uint16(crc)  # 转为大端

        # 填充 CRC 到末尾
        cmd[9]  = crc_be & 0xFF      # 低字节
        cmd[10] = (crc_be >> 8) & 0xFF  # 高字节

        print(' '.join(f'{b:02X}' for b in cmd))  # 输出: 55 AA 01 0F
        return bytes(cmd)

    # typedef struct
    # {
    #     uint32 version;               [0:4]
    #     uint8 config_data_length;     [4]
    #     char country_code[2];         [5:7]
    #     uint32 session_id;            [7:11]   // 49168
    #     uint8 preamble_id;            [11]     //
    #     uint8 channel_number;         [12]     // 9
    #     uint16 num_slots_per_rround;  [13:15]
    #     uint16 slot_duration;         [15:17]// 3600
    #     uint16 ranging_interval;      [17:19]//
    #     uint8 ranging_round_control;  [19]//
    #     uint8 sts_init_iv[6];         [20:26]// 加密使用
    #     uint16 dest_address;          [21:23]//
    # } __attribute__((packed))shareable_data_t;
    @staticmethod
    def build_apple_fira_cmd(shared_configure_data_bytes)->bytes:
        global session_id
        apple = shared_configure_data_bytes[1:]
        session_id = apple[7:11]
        cmd = bytearray(43)
        cmd[0:2] = [0x55, 0xAA] # header
        cmd[2] = 0x00
        cmd[3:5] = [0x24, 0x00]
        try:
            #TLV payload
            cmd[5:7] = [0x24, 0x22]     #type = 0x24, len = 0x22,34 bytes
            cmd[7:11] = apple[0:4]      #version
            cmd[11] = 0x17              #从country_code到vendorId
            cmd[12:14] = apple[5:7]     #country code
            cmd[14:18] = apple[7:11]    #session_id
            cmd[18] = apple[11]         #preamble_id
            cmd[19] = apple[12]         #chan_num
            cmd[20:22] = [0x06, 0x00]   #num_slots_per_rround .和苹果有些不同，直接用文档默认值
            cmd[22:24] = apple[15:17]   #slot_rstu
            cmd[24:26] = apple[17:19]   #range_period
            cmd[26]    = apple[19]      #ranging_round_control
            cmd[27:33] = apple[20:26]   #Vupper48
            cmd[33:35] = apple[26:28]   #dest addr
            cmd[35:37] = [0xd9, 0x36]   #src addr
            cmd[37]    = 0x01           #number of anchors
            cmd[38]    = 0x00           #multimode
            cmd[39:41] = [0x4c, 0x00]   #vendor id
            cmd[41:43] = [0x39, 0x1B]   # CRC
        except e:
            print(e)
        
        crc = crc16_xmodem(cmd[5:41])
        cmd[41:43] = [(crc >> 8) & 0xFF, crc & 0xFF]
        return cmd, session_id
    
    #Normal fira cmd 
    @staticmethod
    def build_fira_cmd(params)->bytes:
        #@todo
        return None
    
    @staticmethod
    def build_start_ranging_cmd(session_id)->bytes:
        cmd = bytearray(14)
        cmd[0:] = [0x55, 0xAA,
        0x00,
        0x07, 0x00,
        0x60, 0x05,
        0x01,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00
        ]
        cmd[8:12] = session_id
        crc = crc16_xmodem(cmd[5:12])
        cmd[12:14] = [(crc >> 8) & 0xFF, crc & 0xFF]
        return cmd
    
    @staticmethod
    def build_stop_ranging_cmd(session_id)->bytes:
        cmd = bytearray(14)
        cmd[0:] = [0x55, 0xAA,
        0x00,
        0x07, 0x00,
        0x60, 0x05,
        0x02,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00
        ]
        cmd[8:12] = session_id
        crc = crc16_xmodem(cmd[5:12])
        cmd[12:14] = [(crc >> 8) & 0xFF, crc & 0xFF]
        return cmd
        