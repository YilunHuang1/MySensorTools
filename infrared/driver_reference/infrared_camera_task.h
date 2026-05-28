/*
 * Copyright (C) Vita Dynamics, Inc. - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 */

#pragma once

#include <atomic>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include "codec/codec_interface.h"
#include "base/task/task_factory.h"
#include "base/task/timed_task.h"
#include "common_def.h"
#include "infrared_camera_pipeline.hpp"
#include "logger/vlog.h"
#include "foxglove_msgs/msg/compressed_video.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"

namespace sw { namespace faultmgr { class FaultmgrClient; } }
namespace vita {
namespace infrared {

/**
 * @brief 红外相机任务
 *
 * 重新实现的红外流水线：使用 vp_sensors + vp_pipeline + VSE
 * 输出 NV12 帧并发布到 ROS 话题。
 */
class InfraredCameraTask : public vita::common::TimedTask {
 public:
  InfraredCameraTask(rclcpp::Node::SharedPtr node, const std::string& name,
                     int period_ms = 200,
                     int phase_ms = 0)  // 默认5fps (200ms周期)
      : vita::common::TimedTask(node, name, period_ms, phase_ms) {}

  /**
   * @brief 设置相机参数
   * @param device_path 设备路径
   * @param width 宽度
   * @param height 高度
   * @param fps 帧率
   */
  void SetCameraParams(const std::string& device_path, int width, int height,
                       int fps) {
    device_path_ = device_path;
    camera_width_ = width;
    camera_height_ = height;
    camera_fps_ = fps;

    VLOGI("Set camera params: %s %dx%d @ %dfps", device_path_.c_str(),
          camera_width_, camera_height_, camera_fps_);
    VLOGI("Task execution period: %dms (%.2f Hz application rate)", GetPeriod(),
          1000.0 / GetPeriod());
  }

  /**
   * @brief 设置帧率
   * @param fps 帧率（帧/秒）
   */
  void SetFrameRate(int fps) {
    camera_fps_ = fps;
    VLOGI("Set camera frame rate: %dfps", camera_fps_);
    VLOGI("Task execution period: %dms (%.2f Hz application rate)", GetPeriod(),
          1000.0 / GetPeriod());
  }

  /**
   * @brief 获取当前帧率
   * @return 当前帧率
   */
  int GetFrameRate() const { return camera_fps_; }

  /**
   * @brief 获取实际帧率（统计值）
   * @return 实际帧率
   */
  double GetActualFrameRate() const { return fps_; }

  /**
   * @brief 获取相机状态信息
   * @return 状态信息字符串
   */
  std::string GetCameraStatus() const;

  /**
   * @brief 设置任务执行周期（独立于相机FPS）
   * @param period_ms 执行周期（毫秒）
   */
  void SetExecutionPeriod(int period_ms) {
    SetPeriod(period_ms);
    VLOGI(
        "Set task execution period: %dms (%.2f Hz application rate, camera "
        "FPS: %d)",
        period_ms, 1000.0 / period_ms, camera_fps_);
  }

  /**
   * @brief 获取任务执行周期
   * @return 执行周期（毫秒）
   */
  int GetExecutionPeriod() const { return GetPeriod(); }

  /**
   * @brief 设置执行频率（Hz）
   * @param frequency_hz 执行频率
   *
   * 示例：相机30fps，应用层5fps
   * - 相机以30fps连续运行
   * - 应用层每200ms执行一次，获取最新帧
   * - 实现低延迟的图像获取
   */
  void SetExecutionFrequency(double frequency_hz) {
    if (frequency_hz > 0) {
      int period_ms = static_cast<int>(1000.0 / frequency_hz);
      SetPeriod(period_ms);
      VLOGI(
          "Set task execution frequency: %.2f Hz (%dms period, camera FPS: %d)",
          frequency_hz, period_ms, camera_fps_);
    }
  }

  /**
   * @brief 初始化任务
   * @return 成功返回0，失败返回错误代码
   */
  int Init() override;

  /**
   * @brief 析构函数
   */
  ~InfraredCameraTask() override;

 protected:
  /**
   * @brief 执行红外相机任务
   * @return 成功返回0，失败返回错误代码
   */
  int Execute() override;

 private:
  // 统计信息
  void updateStatistics(bool success);

  // 配置参数
  std::string device_path_ = "/dev/video0";
  std::string sensor_name_ = "sc202cs";
  int camera_width_ = 1536;
  int camera_height_ = 1160;
  int camera_fps_ = 15;
  int timeout_ms_ = 5000;
  int vse_channel_ = 0;
  bool enable_gdc_ = false;

  // 图像保存相关
  bool enable_image_save_ = false;
  std::string save_dir_ = "/tmp/infrared_camera";
  int save_frame_interval_ = 30;
  int save_frame_count_ = 0;

  // 统计信息
  int total_frames_ = 0;
  int total_errors_ = 0;
  double fps_ = 0.0;
  vita::common::time::Clock::time_point last_fps_time_;

  // 性能监控
  bool enable_performance_monitoring_ = true;
  vita::common::time::Clock::time_point last_performance_time_;
  double avg_execution_time_ = 0.0;

  // 故障管理
  std::shared_ptr<sw::faultmgr::FaultmgrClient> fault_client_;
  vita::common::time::Clock::time_point last_frame_ok_time_;
  bool stream_timeout_active_ = false;

  // 新的红外流水线
  std::unique_ptr<InfraredCameraPipeline> pipeline_;

  // H.265 编码与发布
  bool enable_h265_encode_{false};
  std::string h265_topic_{kInfraredH265Topic};
  vita::codec::VideoEncodeConfig h265_encode_config_{};
  std::unique_ptr<vita::codec::VideoCodecInterface> h265_encoder_;
};

COMMON_REGISTER_TIMED_TASK(InfraredCameraTask);

}  // namespace infrared
}  // namespace vita