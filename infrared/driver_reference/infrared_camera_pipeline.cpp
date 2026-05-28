#include "infrared_camera_pipeline.hpp"

#include <array>
#include <cassert>
#include <cstring>

#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "absl/strings/str_cat.h"
#include "logger/vlog.h"

#include "hb_camera_interface.h"
#include "hbn_vpf_interface.h"
#include "hbn_vpf_data_info.h"
#include "hb_media_codec.h"
#include "hb_media_error.h"
#include "hbn_pym_cfg.h"
#include "hbn_sth_cfg.h"
#include "hbn_error.h"
#include "ynr_cfg.h"
#include "vp_sensors.h"

namespace vita {
namespace infrared {

InfraredCameraPipeline::InfraredCameraPipeline(int camera_index,
                                               VendorPolicyId vendor)
    : camera_index_(camera_index), vendor_(vendor) {}

InfraredCameraPipeline::~InfraredCameraPipeline() { (void)DeInit(); }

absl::Status InfraredCameraPipeline::Init(
    const std::vector<PymOutputConfig>& pym_outputs,
    const PipelineConfig& pipeline_config) {
  pipe_context_ = std::make_unique<InfraredPipeContext>();
  pym_outputs_ = pym_outputs;
  pipeline_config_ = pipeline_config;

  auto status = create_modern_sensor_config();
  if (!status.ok()) {
    return status;
  }

  status = InitializeCameraWithFixedCSI();
  if (!status.ok()) {
    return status;
  }

  status = create_and_run_vflow();
  if (!status.ok()) {
    return status;
  }

  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::DeInit() { return Stop(); }

absl::Status InfraredCameraPipeline::Start() {
  // vflow 已在 create_and_run_vflow 中启动
  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::Stop() {
  if (!pipe_context_) return absl::OkStatus();
  if (pipe_context_->vflow_fd) {
    hbn_vflow_stop(pipe_context_->vflow_fd);
    hbn_vflow_destroy(pipe_context_->vflow_fd);
    pipe_context_->vflow_fd = 0;
  }
  if (pipe_context_->cam_fd) {
    hbn_camera_destroy(pipe_context_->cam_fd);
    pipe_context_->cam_fd = 0;
  }
  if (pipe_context_->pym_node_handle) {
    hbn_vnode_close(pipe_context_->pym_node_handle);
    pipe_context_->pym_node_handle = 0;
  }
  if (pipe_context_->ynr_node_handle) {
    hbn_vnode_close(pipe_context_->ynr_node_handle);
    pipe_context_->ynr_node_handle = 0;
  }
  if (pipe_context_->isp_node_handle) {
    hbn_vnode_close(pipe_context_->isp_node_handle);
    pipe_context_->isp_node_handle = 0;
  }
  if (pipe_context_->vin_node_handle) {
    hbn_vnode_close(pipe_context_->vin_node_handle);
    pipe_context_->vin_node_handle = 0;
  }
  return absl::OkStatus();
}

vp_sensor_config_t* InfraredCameraPipeline::get_current_sensor_config() const {
  assert(sensor_config_);
  return sensor_config_.get();
}

namespace {
std::unique_ptr<vp_sensor_config_t, std::function<void(vp_sensor_config_t*)>>
CreateSc202csConfig() {
  auto deleter = [](vp_sensor_config_t* cfg) {
    if (!cfg) return;
    delete cfg->camera_config;
    delete cfg->mipi_cfg_attr;
    delete cfg->vin_node_attr;
    delete cfg->vin_ichn_attr;
    delete cfg->vin_ochn_attr;
    delete cfg->vin_attr_ex;
    delete cfg->isp_attr;
    delete cfg->isp_ichn_attr;
    delete cfg->isp_ochn_attr;
    delete cfg->ynr_attr;
    delete cfg;
  };

  auto cfg = std::unique_ptr<vp_sensor_config_t, std::function<void(vp_sensor_config_t*)>>(
      new vp_sensor_config_t{}, deleter);

  // 基础信息
  cfg->chip_id_reg = 0xefff;
  cfg->chip_id = 0x00;
  std::memset(cfg->sensor_i2c_addr_list, 0, sizeof(cfg->sensor_i2c_addr_list));
  cfg->sensor_i2c_addr_list[0] = 0x10;
  std::snprintf(cfg->sensor_name, sizeof(cfg->sensor_name), "%s", "sc202cs");
  std::snprintf(cfg->config_file, sizeof(cfg->config_file), "%s",
                "linear_1536x1160_raw10_30fps_1lane.c");

  // camera_config
  auto* cam = new camera_config_t{};
  cam->addr = 0x10;
  cam->eeprom_addr = 0x51;
  cam->serial_addr = 0x40;
  cam->sensor_mode = 1;
  cam->fps = 15;
  cam->width = 1536;
  cam->height = 1160;
  cam->extra_mode = 0;
  cam->config_index = 0;
  cam->end_flag = CAMERA_CONFIG_END_FLAG;
  std::snprintf(cam->name, sizeof(cam->name), "%s", "sc202cs");
  std::strcpy(cam->calib_lname, "/app/infrared/lib/lib_sc202cs_linear.so");

  // mipi_cfg
  auto* mipi = new mipi_config_t{};
  mipi->rx_enable = 1;
  mipi->rx_attr.phy = 0;
  mipi->rx_attr.lane = 1;
  mipi->rx_attr.datatype = 0x2b;
  mipi->rx_attr.fps = 15;
  mipi->rx_attr.mclk = 24;
  mipi->rx_attr.mipiclk = 600;
  mipi->rx_attr.width = 1536;
  mipi->rx_attr.height = 1160;
  mipi->rx_attr.linelenth = 1894;
  mipi->rx_attr.framelenth = 1250;
  mipi->rx_attr.settle = 0;
  mipi->rx_attr.channel_num = 0;
  mipi->rx_attr.channel_sel[0] = 0;
  mipi->rx_ex_mask = 0x40;
  mipi->rx_attr_ex.stop_check_instart = 1;
  mipi->end_flag = MIPI_CONFIG_END_FLAG;

  cam->mipi_cfg = mipi;

  // VIN
  auto* vin_node = new vin_node_attr_t{};
  vin_node->magicNumber = MAGIC_NUMBER;
  vin_node->cim_attr.mipi_en = 1;
  vin_node->cim_attr.cim_isp_flyby = 0;
  vin_node->cim_attr.cim_pym_flyby = 0;
  vin_node->cim_attr.mipi_rx = 0;
  vin_node->cim_attr.vc_index = 0;
  vin_node->cim_attr.ipi_channels = 1;
  vin_node->cim_attr.y_uv_swap = 0;
  vin_node->cim_attr.func.enable_frame_id = 1;
  vin_node->cim_attr.func.set_init_frame_id = 1;
  vin_node->cim_attr.func.enable_pattern = 0;
  vin_node->cim_attr.rdma_input.rdma_en = 0;
  vin_node->cim_attr.rdma_input.stride = 0;
  vin_node->cim_attr.rdma_input.pack_mode = 1;
  vin_node->cim_attr.rdma_input.buff_num = 6;

  auto* vin_ichn = new vin_ichn_attr_t{};
  vin_ichn->width = 1536;
  vin_ichn->height = 1160;
  vin_ichn->format = 0x2b;

  auto* vin_ochn = new vin_ochn_attr_t{};
  vin_ochn->magicNumber = MAGIC_NUMBER;
  vin_ochn->ddr_en = 1;
  vin_ochn->vin_basic_attr.format = 0x2b;
  vin_ochn->vin_basic_attr.wstride = 0;
  vin_ochn->vin_basic_attr.pack_mode = 1;
  vin_ochn->pingpong_ring = 1;
  vin_ochn->roi_en = 0;
  vin_ochn->rawds_en = 0;

  auto* vin_attr_ex = new vin_attr_ex_t{};
  vin_attr_ex->cim_static_attr.water_level_mark = 0;

  // ISP
  auto* isp_attr = new isp_attr_t{};
  // 参考 multimedia_samples: ISP+YNR 场景固定使用 ISP1（hw_id=1）
  isp_attr->channel.hw_id = 1;
  isp_attr->channel.slot_id = 4;
  isp_attr->channel.ctx_id = -1;
  isp_attr->work_mode = (isp_work_mode_e)0;
  isp_attr->hdr_mode = (hdr_mode_e)1;
  isp_attr->size.width = 1536;
  isp_attr->size.height = 1160;
  isp_attr->frame_rate = 15;
  isp_attr->sched_mode = (sched_mode_e)1;
  isp_attr->algo_state = 1;
  isp_attr->isp_combine.isp_channel_mode = (isp_channel_mode_e)0;
  isp_attr->isp_combine.bind_channel.bind_hw_id = 1;
  isp_attr->isp_combine.bind_channel.bind_slot_id = 0;
  isp_attr->clear_record = 0;
  isp_attr->isp_sw_ctrl.ae_stat_buf_en = 1;
  isp_attr->isp_sw_ctrl.awb_stat_buf_en = 1;
  isp_attr->isp_sw_ctrl.ae5bin_stat_buf_en = 1;
  isp_attr->isp_sw_ctrl.ctx_buf_en = 0;
  isp_attr->isp_sw_ctrl.pixel_consistency_en = 0;

  auto* isp_ichn = new isp_ichn_attr_t{};
  isp_ichn->input_crop_cfg.enable = (HB_BOOL)0;
  isp_ichn->in_buf_noclean = 1;
  isp_ichn->in_buf_noncached = 0;

  auto* isp_ochn = new isp_ochn_attr_t{};
  isp_ochn->output_crop_cfg.enable = (HB_BOOL)0;
  isp_ochn->out_buf_noinvalid = 1;
  isp_ochn->out_buf_noncached = 0;
  isp_ochn->output_raw_level = (isp_output_raw_level_e)0;
  // 默认先按 offline 配置；在 creat_isp_node() 会根据 ISP->YNR 是否 online 再调整
  isp_ochn->stream_output_mode = (isp_stream_output_mode_e)0;
  isp_ochn->axi_output_mode = (isp_axi_output_mode_e)9;
  isp_ochn->buf_num = 3;

  // YNR（参考 sc202cs 配置；用于 ISP->YNR->PYM 链路）
  auto* ynr = new ynr_init_attr{};
  ynr->work_mode = 1;
  ynr->slot_id = 4;
  ynr->width = 1536;
  ynr->height = 1160;
  ynr->nr_static_switch = 0b11;
  ynr->in_stride[0] = 1536;
  ynr->in_stride[1] = 1160;
  ynr->nr2d_en = 1;
  ynr->nr3d_en = 1;
  ynr->dma_output_en = 1;
  ynr->debug_en = 0;

  cfg->camera_config = cam;
  cfg->mipi_cfg_attr = mipi;
  cfg->vin_node_attr = vin_node;
  cfg->vin_ichn_attr = vin_ichn;
  cfg->vin_ochn_attr = vin_ochn;
  cfg->vin_attr_ex = vin_attr_ex;
  cfg->isp_attr = isp_attr;
  cfg->isp_ichn_attr = isp_ichn;
  cfg->isp_ochn_attr = isp_ochn;
  cfg->ynr_attr = ynr;
  cfg->sensor_type = SENSOR_TYPE_NORMAL;

  return cfg;
}
}  // namespace

absl::Status InfraredCameraPipeline::create_modern_sensor_config() {
  sensor_config_ = CreateSc202csConfig();
  VLOGI("Infrared sensor config: %s %dx%d@%dfps format=0x%x",
        sensor_config_->sensor_name, sensor_config_->camera_config->width,
        sensor_config_->camera_config->height, sensor_config_->camera_config->fps,
        sensor_config_->camera_config->format);
  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::InitializeCameraWithFixedCSI() {
  int csi_index = 0;  // 单路红外固定使用 CSI0
  auto* sensor_config = get_current_sensor_config();
  pipe_context_->sensor_config = *sensor_config;
  if (sensor_config->vin_node_attr) {
    sensor_config->vin_node_attr->cim_attr.mipi_rx = csi_index;
  }

  enable_sensor_pin(457, 1);
//   pipe_context_->csi_config.index = csi_index;
  pipe_context_->csi_config.mipi_rx = csi_index;
  pipe_context_->csi_config.sensor_addr = sensor_config->camera_config->addr;
  pipe_context_->csi_config.mclk_is_not_configed = 0;
  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::create_and_run_vflow() {
  // 对齐 demo: CSI0 时 vin->isp offline；isp->ynr online；ynr->pym online；slot_id=4
  const int is_online_vin_isp = 0;
  const int is_online_isp_ynr = 1;
  const int is_online_ynr_pym = 1;

  auto st = create_camera_node();
  if (!st.ok()) return st;
  st = create_vin_node();
  if (!st.ok()) return st;
  st = creat_isp_node(/*is_online_to_next=*/is_online_isp_ynr != 0);
  if (!st.ok()) return st;
  // 参考 sample: ISP(1) -> YNR(1) -> PYM(1)
  st = create_ynr_node(/*slot_id*/ 4, /*work_mode*/ 1);
  if (!st.ok()) return st;
  st = create_pym_node(/*hw_id*/ 1, /*slot_id*/ 4, /*pym_mode*/ PYM_MANUAL_MODE);
  if (!st.ok()) return st;

  int ret = hbn_vflow_create(&pipe_context_->vflow_fd);
  if (ret != 0) return absl::InternalError(absl::StrCat("hbn_vflow_create: ", ret));

  ret = hbn_vflow_add_vnode(pipe_context_->vflow_fd, pipe_context_->vin_node_handle);
  if (ret != 0) return absl::InternalError(absl::StrCat("add vin: ", ret));
  ret = hbn_vflow_add_vnode(pipe_context_->vflow_fd, pipe_context_->isp_node_handle);
  if (ret != 0) return absl::InternalError(absl::StrCat("add isp: ", ret));
  ret = hbn_vflow_add_vnode(pipe_context_->vflow_fd, pipe_context_->ynr_node_handle);
  if (ret != 0) return absl::InternalError(absl::StrCat("add ynr: ", ret));
  ret = hbn_vflow_add_vnode(pipe_context_->vflow_fd, pipe_context_->pym_node_handle);
  if (ret != 0) return absl::InternalError(absl::StrCat("add pym: ", ret));

  // 参考 sample: csi0 时 vin->isp 为 offline（is_online=0）
  ret = hbn_vflow_bind_vnode(pipe_context_->vflow_fd, pipe_context_->vin_node_handle,
                             /*is_online*/ is_online_vin_isp,
                             pipe_context_->isp_node_handle, 0);
  if (ret != 0) return absl::InternalError(absl::StrCat("bind vin->isp: ", ret));

  ret = hbn_vflow_bind_vnode(pipe_context_->vflow_fd, pipe_context_->isp_node_handle,
                             /*is_online*/ is_online_isp_ynr,
                             pipe_context_->ynr_node_handle, 0);
  if (ret != 0) return absl::InternalError(absl::StrCat("bind isp->ynr: ", ret));

  ret = hbn_vflow_bind_vnode(pipe_context_->vflow_fd, pipe_context_->ynr_node_handle,
                             /*is_online*/ is_online_ynr_pym,
                             pipe_context_->pym_node_handle, 0);
  if (ret != 0) return absl::InternalError(absl::StrCat("bind ynr->pym: ", ret));

  ret = hbn_camera_attach_to_vin(pipe_context_->cam_fd, pipe_context_->vin_node_handle);
  if (ret != 0) return absl::InternalError(absl::StrCat("attach cam to vin: ", ret));

  ret = hbn_vflow_start(pipe_context_->vflow_fd);
  if (ret != 0) return absl::InternalError(absl::StrCat("vflow start: ", ret));

  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::create_camera_node() {
  vp_sensor_config_t* sensor_config = get_current_sensor_config();
  auto* camera_config = sensor_config->camera_config;
  if (!camera_config) {
    return absl::FailedPreconditionError("camera_config is null");
  }
  int ret = hbn_camera_create(camera_config, &pipe_context_->cam_fd);
  if (ret != 0) {
    return absl::InternalError("hbn_camera_create failed: " + std::to_string(ret));
  }
  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::create_vin_node() {
  auto* sensor_config = get_current_sensor_config();
  auto* vin_node_attr = sensor_config->vin_node_attr;
  auto* vin_ichn_attr = sensor_config->vin_ichn_attr;
  auto* vin_ochn_attr = sensor_config->vin_ochn_attr;
  if (!vin_node_attr || !vin_ichn_attr || !vin_ochn_attr) {
    return absl::FailedPreconditionError("vin attributes missing");
  }

  uint32_t hw_id = vin_node_attr->cim_attr.mipi_rx;
  uint32_t chn_id = 0;

  int ret = hbn_vnode_open(HB_VIN, hw_id, AUTO_ALLOC_ID,
                           &pipe_context_->vin_node_handle);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("open vin: ", ret));
  }

  ret = hbn_vnode_set_attr(pipe_context_->vin_node_handle, vin_node_attr);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("set vin attr: ", ret));
  }
  ret = hbn_vnode_set_ichn_attr(pipe_context_->vin_node_handle, chn_id,
                                vin_ichn_attr);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("set vin ichn: ", ret));
  }
  ret = hbn_vnode_set_ochn_attr(pipe_context_->vin_node_handle, chn_id,
                                vin_ochn_attr);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("set vin ochn: ", ret));
  }

  // 对齐 multimedia_samples: offline 链路（ddr_en=1）需要显式配置输出 buffer 池，
  // 否则下游容易出现 dqbuf timeout / dequeue buffer error。
  if (vin_ochn_attr->ddr_en) {
    hbn_buf_alloc_attr_t alloc_attr{};
    alloc_attr.buffers_num = 6;
    alloc_attr.is_contig = 1;
    alloc_attr.flags = HB_MEM_USAGE_CPU_READ_OFTEN | HB_MEM_USAGE_CPU_WRITE_OFTEN |
                       HB_MEM_USAGE_CACHED;
    ret = hbn_vnode_set_ochn_buf_attr(pipe_context_->vin_node_handle, chn_id,
                                      &alloc_attr);
    if (ret != 0) {
      return absl::InternalError(absl::StrCat("set vin ochn buf: ", ret));
    }
  }

  // 设置 MCLK 扩展
//   vin_attr_ex_t vin_attr_ex{};
//   if (!pipe_context_->csi_config.mclk_is_not_configed) {
//     vin_attr_ex.vin_attr_ex_mask = 0x80;
//     vin_attr_ex.mclk_ex_attr.mclk_freq = 24000000;
//   }
//   ret = hbn_vnode_set_attr_ex(pipe_context_->vin_node_handle, &vin_attr_ex);
//   if (ret != 0) {
//     return absl::InternalError(absl::StrCat("set vin attr ex: ", ret));
//   }

  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::creat_isp_node(bool is_online_to_next) {
  auto* sensor_config = get_current_sensor_config();
  auto* isp_attr = sensor_config->isp_attr;
  auto* isp_ichn_attr = sensor_config->isp_ichn_attr;
  auto* isp_ochn_attr = sensor_config->isp_ochn_attr;
  if (!isp_attr || !isp_ichn_attr || !isp_ochn_attr) {
    return absl::FailedPreconditionError("isp attributes missing");
  }

  uint32_t hw_id = isp_attr->channel.hw_id;
  uint32_t chn_id = 0;

  int ret = hbn_vnode_open(HB_ISP, hw_id, AUTO_ALLOC_ID,
                           &pipe_context_->isp_node_handle);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("open isp: ", ret));
  }

  // 对齐 demo 的 create_isp_node(): online 时启用 stream 输出、禁用 DDR 输出
  if (is_online_to_next) {
    isp_ochn_attr->stream_output_mode = STREAM_OUTPUT_MODE_ENABLE;
    isp_ochn_attr->axi_output_mode = AXI_OUTPUT_MODE_DISABLE;
  } else {
    isp_ochn_attr->stream_output_mode = STREAM_OUTPUT_MODE_DISABLE;
    isp_ochn_attr->axi_output_mode = AXI_OUTPUT_MODE_YUV420;
  }

  ret = hbn_vnode_set_attr(pipe_context_->isp_node_handle, isp_attr);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("set isp attr: ", ret));
  }
  ret = hbn_vnode_set_ichn_attr(pipe_context_->isp_node_handle, chn_id,
                                isp_ichn_attr);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("set isp ichn: ", ret));
  }
  ret = hbn_vnode_set_ochn_attr(pipe_context_->isp_node_handle, chn_id,
                                isp_ochn_attr);
  if (ret != 0) {
    return absl::InternalError(absl::StrCat("set isp ochn: ", ret));
  }

  return absl::OkStatus();
}

absl::Status InfraredCameraPipeline::create_ynr_node(uint32_t slot_id,
                                                    uint32_t work_mode) {
  auto* sensor_config = get_current_sensor_config();
  if (!sensor_config || !sensor_config->ynr_attr) {
    return absl::FailedPreconditionError("ynr_attr missing in sensor config");
  }

  sensor_config->ynr_attr->work_mode = work_mode;
  sensor_config->ynr_attr->slot_id = slot_id;

  int ret =
      hbn_vnode_open(HB_YNR, /*hw_id*/ 1, AUTO_ALLOC_ID,
                     &pipe_context_->ynr_node_handle);
  if (ret != 0) return absl::InternalError(absl::StrCat("open ynr: ", ret));

  ret = hbn_vnode_set_attr(pipe_context_->ynr_node_handle, sensor_config->ynr_attr);
  if (ret != 0) return absl::InternalError(absl::StrCat("set ynr attr: ", ret));

  hobot_ynr_channel_input_config channel_input_cfg{};
  ret = hbn_vnode_set_ichn_attr(pipe_context_->ynr_node_handle, 0, &channel_input_cfg);
  if (ret != 0) return absl::InternalError(absl::StrCat("set ynr ichn0: ", ret));
  ret = hbn_vnode_set_ichn_attr(pipe_context_->ynr_node_handle, 1, &channel_input_cfg);
  if (ret != 0) return absl::InternalError(absl::StrCat("set ynr ichn1: ", ret));

  hobot_ynr_channel_output_config channel_output_cfg{};
  ret = hbn_vnode_set_ochn_attr(pipe_context_->ynr_node_handle, 0, &channel_output_cfg);
  if (ret != 0) return absl::InternalError(absl::StrCat("set ynr ochn: ", ret));

  if (sensor_config->ynr_attr->nr3d_en) {
    hbn_buf_alloc_attr_t alloc_attr{};
    alloc_attr.buffers_num = 3;
    alloc_attr.is_contig = 1;
    alloc_attr.flags = (int64_t)((uint64_t)HB_MEM_USAGE_CPU_READ_OFTEN |
                                 (uint64_t)HB_MEM_USAGE_CPU_WRITE_OFTEN |
                                 (uint64_t)HB_MEM_USAGE_CACHED);
    ret = hbn_vnode_set_ochn_buf_attr(pipe_context_->ynr_node_handle, 0, &alloc_attr);
    if (ret != 0) return absl::InternalError(absl::StrCat("set ynr buf: ", ret));
  }

  return absl::OkStatus();
}

static inline uint32_t Align16(uint32_t x) { return (x + 15u) & ~15u; }
static inline uint32_t FloorAlign2(uint32_t x) { return x & ~1u; }

absl::Status InfraredCameraPipeline::create_pym_node(uint32_t hw_id,
                                                     uint32_t slot_id,
                                                     uint32_t pym_mode) {
  if (pym_outputs_.empty()) {
    return absl::FailedPreconditionError("No PYM outputs configured");
  }
  const auto& out0 = pym_outputs_[0];

  pym_cfg_t pym_cfg{};
  pym_cfg.hw_id = static_cast<uint8_t>(hw_id);
  pym_cfg.pym_mode = static_cast<uint8_t>(pym_mode);
  pym_cfg.slot_id = static_cast<uint8_t>(slot_id);
  pym_cfg.output_buf_num = 3;
  pym_cfg.fb_buf_num = 2;
  pym_cfg.layer_num_trans_next = 0;
  pym_cfg.layer_num_share_prev = -1;
  pym_cfg.out_buf_noinvalid = 1;
  pym_cfg.out_buf_noncached = 0;
  pym_cfg.in_buf_noclean = 1;
  pym_cfg.in_buf_noncached = 0;
  pym_cfg.magicNumber = MAGIC_NUMBER;

  auto* sensor_config = get_current_sensor_config();
  const uint32_t in_w = sensor_config->camera_config->width;
  const uint32_t in_h = sensor_config->camera_config->height;

  pym_cfg.chn_ctrl.pixel_num_before_sol = 2;
  pym_cfg.chn_ctrl.suffix_hb_val = 100;
  pym_cfg.chn_ctrl.prefix_hb_val = 2;
  pym_cfg.chn_ctrl.suffix_vb_val = 10;
  pym_cfg.chn_ctrl.prefix_vb_val = 0;
  pym_cfg.chn_ctrl.bl_max_layer_en = 0;

  pym_cfg.chn_ctrl.src_in_width = in_w;
  pym_cfg.chn_ctrl.src_in_height = in_h;
  pym_cfg.chn_ctrl.src_in_stride_y = Align16(in_w);
  pym_cfg.chn_ctrl.src_in_stride_uv = Align16(in_w);

  pym_cfg.chn_ctrl.ds_roi_en = 1 << 0;  // only SRC
  pym_cfg.chn_ctrl.ds_roi_sel[0] = 0;
  pym_cfg.chn_ctrl.ds_roi_layer[0] = 0;

  roi_box_t* roi = &pym_cfg.chn_ctrl.ds_roi_info[0];
  roi->start_left = 0;
  roi->start_top = 0;
  roi->region_width = FloorAlign2(out0.width ? out0.width : in_w);
  roi->region_height = FloorAlign2(out0.height ? out0.height : in_h);
  roi->out_width = FloorAlign2(roi->region_width);
  roi->out_height = FloorAlign2(roi->region_height);
  roi->wstride_y = Align16(roi->out_width);
  roi->wstride_uv = Align16(roi->out_width);
  roi->vstride = roi->out_height;

  int ret = hbn_vnode_open(HB_PYM, pym_cfg.hw_id, AUTO_ALLOC_ID,
                           &pipe_context_->pym_node_handle);
  if (ret != 0) return absl::InternalError(absl::StrCat("open pym: ", ret));

  ret = hbn_vnode_set_attr(pipe_context_->pym_node_handle, &pym_cfg);
  if (ret != 0) return absl::InternalError(absl::StrCat("set pym attr: ", ret));

  ret = hbn_vnode_set_ichn_attr(pipe_context_->pym_node_handle, 0, &pym_cfg);
  if (ret != 0) return absl::InternalError(absl::StrCat("set pym ichn: ", ret));
  ret = hbn_vnode_set_ochn_attr(pipe_context_->pym_node_handle, 0, &pym_cfg);
  if (ret != 0) return absl::InternalError(absl::StrCat("set pym ochn: ", ret));

  hbn_buf_alloc_attr_t alloc_attr{};
  alloc_attr.buffers_num = pym_cfg.output_buf_num;
  alloc_attr.is_contig = 1;
  alloc_attr.flags = HB_MEM_USAGE_CPU_READ_OFTEN | HB_MEM_USAGE_CPU_WRITE_OFTEN |
                     HB_MEM_USAGE_CACHED;
  ret = hbn_vnode_set_ochn_buf_attr(pipe_context_->pym_node_handle, 0, &alloc_attr);
  if (ret != 0) return absl::InternalError(absl::StrCat("set pym buf: ", ret));

  return absl::OkStatus();
}

absl::StatusOr<PymFrameGroup> InfraredCameraPipeline::GetPymFrameGroup(
    uint32_t timeout_ms) {
  if (!pipe_context_ || !pipe_context_->pym_node_handle) {
    return absl::FailedPreconditionError("PYM pipeline not started");
  }

  PymFrameGroup out{};
  out.node = pipe_context_->pym_node_handle;
  out.ochn_id = 0;
  int ret = hbn_vnode_getframe_group(pipe_context_->pym_node_handle, 0, timeout_ms,
                                     &out.group);
  if (ret != 0) {
    out.node = 0;
    return absl::InternalError(absl::StrCat("hbn_vnode_getframe_group: ", ret));
  }

  const uint64_t tv_us =
      static_cast<uint64_t>(out.group.info.tv.tv_sec) * 1000000ULL +
      static_cast<uint64_t>(out.group.info.tv.tv_usec);
  const uint64_t trig_tv_us =
      static_cast<uint64_t>(out.group.info.trig_tv.tv_sec) * 1000000ULL +
      static_cast<uint64_t>(out.group.info.trig_tv.tv_usec);
  out.timestamp_ns = out.group.info.timestamps - (tv_us - trig_tv_us) * 1000ULL;

  return out;
}

}  // namespace infrared
}  // namespace vita


