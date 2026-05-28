#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import cv2
import numpy as np

class IrConverter(Node):
    def __init__(self):
        super().__init__('ir_converter')
        
        # 订阅话题
        self.subscription = self.create_subscription(
            Image,
            '/infrared_camera/image_raw',
            self.listener_callback,
            10)
        
        # 发布话题
        self.publisher_ = self.create_publisher(Image, '/infrared_camera/image_mono', 10)
        
        self.get_logger().info('No-Bridge YUV422 to Mono8 Converter Started...')

    def listener_callback(self, msg):
        try:
            # 1. 解析原始数据
            width = msg.width
            height = msg.height
            
            # 将 buffer 转为 numpy (YUV422, 2 bytes per pixel)
            raw_arr = np.frombuffer(msg.data, dtype=np.uint8)
            yuyv_img = raw_arr.reshape((height, width, 2))

            # 2. 转换颜色 (YUV -> GRAY)
            # 这一步只保留 Y 通道，丢弃 UV
            gray_img = cv2.cvtColor(yuyv_img, cv2.COLOR_YUV2GRAY_YUYV)

            # 3. 手动构建 ROS 2 Image 消息 (替代 cv_bridge)
            out_msg = Image()
            out_msg.header = msg.header  # 继承原始时间戳和frame_id
            out_msg.height = gray_img.shape[0]
            out_msg.width = gray_img.shape[1]
            out_msg.encoding = "mono8"   # 告诉 Foxglove 这是灰度图
            out_msg.is_bigendian = 0
            out_msg.step = out_msg.width # 灰度图步长 = 宽度 * 1字节
            
            # 4. 填充数据
            # gray_img.tobytes() 将 numpy 数组转为纯字节流
            out_msg.data = gray_img.tobytes()
            
            self.publisher_.publish(out_msg)

        except Exception as e:
            self.get_logger().error(f'Error: {str(e)}')

def main(args=None):
    rclpy.init(args=args)
    converter = IrConverter()
    try:
        rclpy.spin(converter)
    except KeyboardInterrupt:
        pass
    finally:
        converter.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()