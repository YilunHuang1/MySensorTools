/*
 * Copyright (C) Vita Dynamics, Inc. - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 */

#include "infrared_camera_task.h"

#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>

#include <vector>

#include "fault_ids/fault_id.h"
#include "software_faultmgr/client/fault_client.h"
#include "time/time.h"
#include "common_def.h"

namespace vita {
namespace infrared {

namespace {
// 将带 stride 的 NV12 (Y + interleaved UV) 打包成紧凑布局（width 对齐）：
// output layout: [Y plane (w*h)] + [UV plane (w*h/2)]
static std::vector<uint8_t> PackNv12Compact(const hb_mem_graphic_buf_t& gb,
                                            uint32_t width, uint32_t height) {
  const uint32_t stride = static_cast<uint32_t>(gb.stride);
  const uint8_t* src_y = static_cast<const uint8_t*>(gb.virt_addr[0]);
  const uint8_t* src_uv = static_cast<const uint8_t*>(gb.virt_addr[1]);
  std::vector<uint8_t> out;
  out.resize(static_cast<size_t>(width) * height * 3 / 2);

  uint8_t* dst_y = out.data();
  uint8_t* dst_uv = dst_y + static_cast<size_t>(width) * height;

  // Y: height rows
  for (uint32_t r = 0; r < height; ++r) {
    std::memcpy(dst_y + static_cast<size_t>(r) * width,
                src_y + static_cast<size_t>(r) * stride, width);
  }
  // UV: height/2 rows, row width == width
  const uint32_t uv_rows = height / 2;
  for (uint32_t r = 0; r < uv_rows; ++r) {
    std::memcpy(dst_uv + static_cast<size_t>(r) * width,
                src_uv + static_cast<size_t>(r) * stride, width);
  }
  return out;
}
}  // namespace

int InfraredCameraTask::Init() {
  VLOGI("Initializing InfraredCameraTask (ISP->YNR->PYM)...");

  auto node_config = GetBaseNodePtr()->GetNodeConfig();

  if (auto camera_config = node_config->GetSubConfig("infrared_camera_config")) {
    camera_config->GetStringValue("sensor_name", sensor_name_);
    camera_config->GetInt32Value("width", camera_width_);
    camera_config->GetInt32Value("height", camera_height_);
    camera_config->GetInt32Value("fps", camera_fps_);
  }

  if (auto save_config = node_config->GetSubConfig("image_save_config")) {
    save_config->GetBoolValue("enable_save", enable_image_save_);
    std::string save_dir;
    if (save_config->GetStringValue("save_dir", save_dir)) {
      save_dir_ = save_dir;
    }
    save_config->GetInt32Value("save_frame_interval", save_frame_interval_);
  }

  if (auto perf_config = node_config->GetSubConfig("performance_config")) {
    perf_config->GetBoolValue("enable_monitoring",
                              enable_performance_monitoring_);
    float exec_freq;
    if (perf_config->GetFloatValue("execution_frequency_hz", exec_freq)) {
      SetExecutionFrequency(exec_freq);
    }
  }

  // codec_config: 可选启用 H.265 编码并额外发布一个 topic
  if (auto codec_config = node_config->GetSubConfig("codec_config")) {
    codec_config->GetBoolValue("enable_h265", enable_h265_encode_);
    std::string topic;
    if (codec_config->GetStringValue("h265_topic", topic) && !topic.empty()) {
      h265_topic_ = topic;
    }

    int32_t bitrate = 2048;  // kbps
    int32_t gop = 30;
    codec_config->GetInt32Value("bitrate_kbps", bitrate);
    codec_config->GetInt32Value("gop_size", gop);

    h265_encode_config_.width = camera_width_;
    h265_encode_config_.height = camera_height_;
    h265_encode_config_.fps = camera_fps_;
    h265_encode_config_.bitrate = bitrate;
    h265_encode_config_.gop_size = gop;
    h265_encode_config_.pixel_format = vita::codec::PixelFormat::NV12;
    h265_encode_config_.use_zero_copy = false;  // 红外当前不走 VSE 零拷贝，先用紧凑 buffer 输入
  }

  fault_client_ =
      sw::faultmgr::FaultmgrClient::NewAsyncFmClient("infrared_fault_client");

  std::vector<PymOutputConfig> pym_outputs;
  PymOutputConfig out{};
  out.name = "infrared_main";
  out.enable = true;
  out.width = static_cast<uint32_t>(camera_width_);
  out.height = static_cast<uint32_t>(camera_height_);
  pym_outputs.push_back(out);

  pipeline_ =
      std::make_unique<InfraredCameraPipeline>(0, VendorPolicyId::UNIMAGE);

  auto status = pipeline_->Init(pym_outputs, PipelineConfig{});
  if (!status.ok()) {
    VLOGE("Failed to init infrared pipeline: %s", status.ToString().c_str());
    if (fault_client_) {
      auto now_ts = std::chrono::duration_cast<std::chrono::milliseconds>(
                        vita::common::time::now().time_since_epoch())
                        .count();
      sw::faultmgr::Fault occur_fault{
          PERCEPTION_INFRARED_CAMERA_MAIN_CONNECTION_LOST,
          sw::faultmgr::FaultStatus::FAULT_OCCUR, now_ts};
      fault_client_->AddFaultSync(occur_fault);
    }
    return -1;
  }

  // 初始化 H.265 encoder（可选）
  if (enable_h265_encode_) {
    auto enc_or = vita::codec::CodecFactory::CreateVideoCodec(
        vita::codec::CodecType::H265, vita::codec::CodecMode::ENCODE);
    if (!enc_or.ok()) {
      VLOGE("Failed to create H265 encoder: %s",
            enc_or.status().ToString().c_str());
      enable_h265_encode_ = false;
    } else {
      h265_encoder_ = std::move(enc_or.value());
      status = h265_encoder_->ConfigureEncode(h265_encode_config_);
      if (!status.ok()) {
        VLOGE("Failed to ConfigureEncode(H265): %s", status.ToString().c_str());
        h265_encoder_.reset();
        enable_h265_encode_ = false;
      } else {
        status = h265_encoder_->Initialize();
        if (!status.ok()) {
          VLOGE("Failed to Initialize(H265): %s", status.ToString().c_str());
          h265_encoder_.reset();
          enable_h265_encode_ = false;
        } else {
          status = h265_encoder_->Configure();
          if (!status.ok()) {
            VLOGE("Failed to Configure(H265): %s", status.ToString().c_str());
            h265_encoder_.reset();
            enable_h265_encode_ = false;
          } else {
            status = h265_encoder_->Start();
            if (!status.ok()) {
              VLOGE("Failed to Start(H265): %s", status.ToString().c_str());
              h265_encoder_.reset();
              enable_h265_encode_ = false;
            } else {
              VLOGI("H265 encode enabled, publish topic: %s (%dx%d@%dfps, %dkbps)",
                    h265_topic_.c_str(), h265_encode_config_.width,
                    h265_encode_config_.height, h265_encode_config_.fps,
                    h265_encode_config_.bitrate);
            }
          }
        }
      }
    }
  }

  if (enable_image_save_) {
    std::filesystem::create_directories(save_dir_);
  }

  last_fps_time_ = vita::common::time::now();
  last_frame_ok_time_ = vita::common::time::now();

  if (TimedTask::Init() != 0) {
    VLOGE("Failed to initialize base timed task");
    return -1;
  }

  VLOGI("InfraredCameraTask initialized: %s %dx%d@%dfps (VIN->ISP->YNR->PYM)",
        sensor_name_.c_str(), camera_width_, camera_height_, camera_fps_);
  return 0;
}

std::string InfraredCameraTask::GetCameraStatus() const {
  std::stringstream ss;
  ss << "Infrared pipeline\n";
  ss << "  Sensor: " << sensor_name_ << "\n";
  ss << "  Resolution: " << camera_width_ << "x" << camera_height_ << "\n";
  ss << "  FPS: " << camera_fps_ << "\n";
  ss << "  Pipeline: VIN->ISP->YNR->PYM\n";
  ss << "  Frames: " << total_frames_ << " Errors: " << total_errors_ << "\n";
  ss << "  Measured FPS: " << std::fixed << std::setprecision(2) << fps_
     << "\n";
  return ss.str();
}

InfraredCameraTask::~InfraredCameraTask() {
  if (pipeline_) {
    (void)pipeline_->Stop();
  }
  if (h265_encoder_) {
    (void)h265_encoder_->Stop();
    (void)h265_encoder_->Release();
  }
}

int InfraredCameraTask::Execute() {
  if (!pipeline_) {
    VLOGE("Infrared pipeline not initialized");
    return -1;
  }

  auto group_or = pipeline_->GetPymFrameGroup(1000);
  if (!group_or.ok()) {
    VLOGE("Failed to get frame: %s", group_or.status().ToString().c_str());
    updateStatistics(false);

    auto now_tp = vita::common::time::now();
    auto now_ts = std::chrono::duration_cast<std::chrono::milliseconds>(
                      now_tp.time_since_epoch())
                      .count();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                          now_tp - last_frame_ok_time_)
                          .count();
    if (!stream_timeout_active_ && elapsed_ms >= timeout_ms_ && fault_client_) {
      sw::faultmgr::Fault occur_fault{
          PERCEPTION_INFRARED_CAMERA_MAIN_CONNECTION_LOST,
          sw::faultmgr::FaultStatus::FAULT_OCCUR, now_ts};
      fault_client_->AddFault(occur_fault);
      stream_timeout_active_ = true;
    }
    return -1;
  }

  // PYM layer0 (SRC)
  const auto& group = group_or.value();
  const hb_mem_graphic_buf_t& gb = group.group.buf_group.graph_group[0];

  auto image_msg = std::make_shared<sensor_msgs::msg::Image>();
  image_msg->header.frame_id = "infrared_camera";
  image_msg->header.stamp = rclcpp::Time(static_cast<int64_t>(group.timestamp_ns));
  image_msg->width = gb.width;
  image_msg->height = gb.height;
  image_msg->encoding = "mono8";
  image_msg->is_bigendian = 0;
  image_msg->step = gb.width;

  image_msg->data.resize(static_cast<size_t>(gb.width) * gb.height);
  const uint8_t* src_y = static_cast<const uint8_t*>(gb.virt_addr[0]);
  for (uint32_t r = 0; r < gb.height; ++r) {
    std::memcpy(image_msg->data.data() + static_cast<size_t>(r) * gb.width,
                src_y + static_cast<size_t>(r) * gb.stride, gb.width);
  }

  PublishMessage(kInfraredImageTopic, std::move(*image_msg));

  // 可选：发布 H.265 编码流
  if (enable_h265_encode_ && h265_encoder_) {
    vita::codec::CodecBuffer in{};
    in.data = PackNv12Compact(gb, gb.width, gb.height);
    auto enc = h265_encoder_->EncodeFrame(in);
    if (!enc.ok()) {
      VLOGW("H265 encode failed: %s", enc.status().ToString().c_str());
    } else {
      foxglove_msgs::msg::CompressedVideo msg;
      msg.frame_id = "infrared_camera";
      msg.timestamp.sec = static_cast<int32_t>(group.timestamp_ns / 1000000000ULL);
      msg.timestamp.nanosec =
          static_cast<uint32_t>(group.timestamp_ns % 1000000000ULL);
      msg.format = "h265";
      msg.data = std::move(enc->data);
      PublishMessage(h265_topic_, std::move(msg));
    }
  }

  if (enable_image_save_ &&
      (save_frame_count_ % save_frame_interval_ == 0)) {
    std::string filename =
        save_dir_ + "/infrared_" +
        std::to_string(
            vita::common::time::now().time_since_epoch().count()) +
        ".raw";
    std::ofstream file(filename, std::ios::binary);
    if (file.is_open()) {
      file.write(reinterpret_cast<const char*>(image_msg->data.data()),
                 image_msg->data.size());
      file.close();
    }
  }

  save_frame_count_++;
  updateStatistics(true);

  auto now_tp = vita::common::time::now();
  auto now_ts = std::chrono::duration_cast<std::chrono::milliseconds>(
                    now_tp.time_since_epoch())
                    .count();
  last_frame_ok_time_ = now_tp;
  if (stream_timeout_active_ && fault_client_) {
    sw::faultmgr::Fault restore_fault{
        PERCEPTION_INFRARED_CAMERA_MAIN_CONNECTION_LOST,
        sw::faultmgr::FaultStatus::FAULT_RESTORE, now_ts};
    fault_client_->AddFault(restore_fault);
    stream_timeout_active_ = false;
  }

  return 0;
}

void InfraredCameraTask::updateStatistics(bool success) {
  total_frames_++;
  if (!success) {
    total_errors_++;
  }

  auto now = vita::common::time::now();
  auto elapsed =
      std::chrono::duration_cast<std::chrono::seconds>(now - last_fps_time_)
          .count();

  if (elapsed >= 1) {
    fps_ = static_cast<double>(total_frames_) / elapsed;
    last_fps_time_ = now;
    total_frames_ = 0;
  }
}

}  // namespace infrared
}  // namespace vita


