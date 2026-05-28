import sys
import argparse
from rclpy.serialization import deserialize_message, serialize_message
from rclpy.time import Time
from rosbag2_py import SequentialReader, SequentialWriter, StorageOptions, ConverterOptions, TopicMetadata

# 导入必要的某些消息类型
# ⚠️ 重要：必须确保你的环境能找到 uwb_location 包
try:
    from uwb_location.msg import UWB
    from std_msgs.msg import Float64
except ImportError as e:
    print("❌ 错误: 无法导入消息类型。请确保你已经 source 了包含 'uwb_location' 的工作空间。")
    print(f"详细错误: {e}")
    sys.exit(1)

def calculate_accel(current_val, prev_val, current_time_ns, prev_time_ns, prev_velocity):
    """
    计算加速度
    返回: (当前加速度, 当前速度)
    """
    if prev_val is None or prev_time_ns is None:
        return 0.0, 0.0
    
    dt = (current_time_ns - prev_time_ns) / 1e9  # 纳秒转秒
    
    if dt <= 0.000001: # 防止除以0或时间戳重复
        return 0.0, prev_velocity

    # 计算速度
    current_velocity = (current_val - prev_val) / dt
    
    # 计算加速度
    # 如果是第一帧计算速度，prev_velocity为0，加速度可能会突变，这里简单处理
    accel = (current_velocity - prev_velocity) / dt
    
    return accel, current_velocity

def main():
    parser = argparse.ArgumentParser(description='Process UWB bag to add acceleration data.')
    parser.add_argument('input_bag', help='Path to input .mcap file')
    parser.add_argument('output_bag', help='Path to output .mcap file')
    args = parser.parse_args()

    input_bag_path = args.input_bag
    output_bag_path = args.output_bag

    # 1. 设置读取器
    reader = SequentialReader()
    storage_options = StorageOptions(uri=input_bag_path, storage_id='mcap')
    converter_options = ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr')
    reader.open(storage_options, converter_options)

    # 2. 设置写入器
    writer = SequentialWriter()
    out_storage_options = StorageOptions(uri=output_bag_path, storage_id='mcap')
    writer.open(out_storage_options, converter_options)

    # 3. 准备新话题的元数据
    # 我们将把计算出的加速度发布为 Float64 消息
    new_topics = {
        '/uwb/derived/dist_accel': 'std_msgs/msg/Float64',
        '/uwb/derived/angle_accel_raw': 'std_msgs/msg/Float64',
        '/uwb/derived/angle_accel_filtered': 'std_msgs/msg/Float64'
    }

    # 创建输入话题列表，用于复制
    topics = reader.get_all_topics_and_types()
    for topic in topics:
        writer.create_topic(topic)

    # 创建新话题
    for topic_name, topic_type in new_topics.items():
        writer.create_topic(TopicMetadata(
            name=topic_name,
            type=topic_type,
            serialization_format='cdr',
            offered_qos_profiles=''
        ))

    print(f"开始处理: {input_bag_path} -> {output_bag_path}")

    # 4. 状态变量初始化
    prev_time_ns = None
    
    # 距离相关
    prev_dist = None
    prev_dist_vel = 0.0
    
    # 角度相关 (Raw)
    prev_angle_raw = None
    prev_angle_raw_vel = 0.0
    
    # 角度相关 (Filtered)
    prev_angle_filt = None
    prev_angle_filt_vel = 0.0

    count = 0

    while reader.has_next():
        (topic, data, t) = reader.read_next()
        
        # 将原始数据写入新包 (保持原始数据不变)
        writer.write(topic, data, t)

        if topic == '/uwb/data':
            msg = deserialize_message(data, UWB)
            
            # 获取时间戳 (假设 header.stamp 是标准 ROS 时间)
            current_time_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nsec
            
            # --- 计算距离加速度 (使用 filtered) ---
            dist_accel, dist_vel = calculate_accel(
                msg.distance_filtered, prev_dist, current_time_ns, prev_time_ns, prev_dist_vel
            )
            
            # --- 计算角度加速度 (Raw) ---
            angle_raw_accel, angle_raw_vel = calculate_accel(
                msg.angle, prev_angle_raw, current_time_ns, prev_time_ns, prev_angle_raw_vel
            )

            # --- 计算角度加速度 (Filtered) ---
            angle_filt_accel, angle_filt_vel = calculate_accel(
                msg.angle_filtered, prev_angle_filt, current_time_ns, prev_time_ns, prev_angle_filt_vel
            )

            # --- 封装并写入新消息 ---
            def write_float64(topic_name, value, timestamp):
                new_msg = Float64()
                new_msg.data = value
                serialized = serialize_message(new_msg)
                writer.write(topic_name, serialized, timestamp)

            write_float64('/uwb/derived/dist_accel', dist_accel, t)
            write_float64('/uwb/derived/angle_accel_raw', angle_raw_accel, t)
            write_float64('/uwb/derived/angle_accel_filtered', angle_filt_accel, t)

            # --- 更新状态 ---
            prev_time_ns = current_time_ns
            
            prev_dist = msg.distance_filtered
            prev_dist_vel = dist_vel
            
            prev_angle_raw = msg.angle
            prev_angle_raw_vel = angle_raw_vel
            
            prev_angle_filt = msg.angle_filtered
            prev_angle_filt_vel = angle_filt_vel

        count += 1
        if count % 100 == 0:
            print(f"已处理 {count} 帧...", end='\r')

    print(f"\n处理完成！共处理 {count} 条消息。")

if __name__ == "__main__":
    main()