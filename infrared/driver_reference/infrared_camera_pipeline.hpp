#pragma once

#include <functional>
#include <memory>
#include <string>
#include <vector>
#include <cstring>

#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "codec/platform_adapter.h"
#include "logger/vlog.h"

// 来自 HBN SDK 的节点/相机接口
#include "hb_camera_interface.h"
#include "hbn_vpf_interface.h"
#include "hbn_vpf_data_info.h"
#include "hb_media_codec.h"
#include "hb_media_error.h"
#include "hbn_pym_cfg.h"
#include "hbn_sth_cfg.h"
#include "hbn_error.h"
#include "vp_sensors.h"


namespace vita {
namespace infrared {

// 简版 PYM 输出配置（目前只使用 layer0 作为主输出）
struct PymOutputConfig {
  std::string name;
  bool enable = true;
  uint32_t width = 0;
  uint32_t height = 0;
};

struct PipelineConfig {
  bool gdc_enable = false;
};

enum class VendorPolicyId { UNIMAGE, SENSING };

// PYM 输出的 group frame（RAII: 自动 releaseframe_group）
struct PymFrameGroup {
  hbn_vnode_handle_t node = 0;
  uint32_t ochn_id = 0;
  hbn_vnode_image_group_t group{};
  uint64_t timestamp_ns = 0;

  PymFrameGroup() = default;
  ~PymFrameGroup() {
    if (node) {
      (void)hbn_vnode_releaseframe_group(node, ochn_id, &group);
    }
  }
  PymFrameGroup(const PymFrameGroup&) = delete;
  PymFrameGroup& operator=(const PymFrameGroup&) = delete;
  PymFrameGroup(PymFrameGroup&& other) noexcept {
    node = other.node;
    ochn_id = other.ochn_id;
    group = other.group;
    timestamp_ns = other.timestamp_ns;
    other.node = 0;
    other.ochn_id = 0;
    std::memset(&other.group, 0, sizeof(other.group));
    other.timestamp_ns = 0;
  }
  PymFrameGroup& operator=(PymFrameGroup&& other) noexcept {
    if (this != &other) {
      if (node) {
        (void)hbn_vnode_releaseframe_group(node, ochn_id, &group);
      }
      node = other.node;
      ochn_id = other.ochn_id;
      group = other.group;
      timestamp_ns = other.timestamp_ns;
      other.node = 0;
      other.ochn_id = 0;
      std::memset(&other.group, 0, sizeof(other.group));
      other.timestamp_ns = 0;
    }
    return *this;
  }
};

/**
 * @brief 单路红外相机现代化流水线（MIPI -> VIN -> ISP -> YNR -> PYM）
 *
 * 参考 stereo/CameraPipline 的实现方式，不依赖 multimedia_samples 的 C 代码。
 */
class InfraredCameraPipeline {
 public:
  InfraredCameraPipeline(int camera_index = 0,
                         VendorPolicyId vendor = VendorPolicyId::UNIMAGE);
  ~InfraredCameraPipeline();

  absl::Status Init(const std::vector<PymOutputConfig>& pym_outputs,
                    const PipelineConfig& pipeline_config = PipelineConfig{});
  absl::Status DeInit();
  absl::Status Start();
  absl::Status Stop();

  absl::StatusOr<PymFrameGroup> GetPymFrameGroup(uint32_t timeout_ms = 1000);

  const vp_csi_config_t& GetCsiConfig() const { return pipe_context_->csi_config; }
  int GetCsiIndex() const { return 0; }

 private:
  absl::Status create_modern_sensor_config();
  absl::Status InitializeCameraWithFixedCSI();
  absl::Status create_and_run_vflow();
  absl::Status create_camera_node();
  absl::Status create_vin_node();
  absl::Status creat_isp_node(bool is_online_to_next);
  absl::Status create_ynr_node(uint32_t slot_id, uint32_t work_mode);
  absl::Status create_pym_node(uint32_t hw_id, uint32_t slot_id, uint32_t pym_mode);

  // 内部工具
  vp_sensor_config_t* get_current_sensor_config() const;

  struct InfraredPipeContext {
    hbn_vflow_handle_t vflow_fd = 0;
    hbn_vnode_handle_t vin_node_handle = 0;
    hbn_vnode_handle_t isp_node_handle = 0;
    hbn_vnode_handle_t ynr_node_handle = 0;
    hbn_vnode_handle_t pym_node_handle = 0;
    hbn_vnode_handle_t cam_fd = 0;
    vp_sensor_config_t sensor_config{};
    vp_csi_config_t csi_config{};
  };

  std::unique_ptr<InfraredPipeContext> pipe_context_;
  std::unique_ptr<vp_sensor_config_t, std::function<void(vp_sensor_config_t*)>>
      sensor_config_;

  std::vector<PymOutputConfig> pym_outputs_;
  PipelineConfig pipeline_config_;

  int camera_index_ = 0;
  VendorPolicyId vendor_;
};

}  // namespace infrared
}  // namespace vita


