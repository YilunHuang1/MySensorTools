/*
 * Copyright (C) Vita Dynamics, Inc. - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 */

#pragma once

#include <memory>
#include <string>

#include "base/base_node.h"
#include "base/node_factory.h"

namespace vita {
namespace infrared {

/**
 * @brief 红外相机节点类
 *
 * 负责管理红外相机系统的初始化、配置和运行
 * 继承自BaseNode，提供ROS2节点功能
 * 使用task框架进行周期性的红外相机处理
 */
class InfraredNode : public vita::common::BaseNode {
 public:
  /**
   * @brief 默认构造函数
   */
  InfraredNode(const std::string& node_name, const rclcpp::NodeOptions& options)
      : BaseNode(node_name, options) {}

  /**
   * @brief 析构函数
   */
  virtual ~InfraredNode() = default;

  /**
   * @brief 禁用拷贝构造和赋值
   */
  InfraredNode(const InfraredNode&) = delete;
  InfraredNode& operator=(const InfraredNode&) = delete;

  /**
   * @brief 初始化节点
   * @param cfg_path 配置文件路径
   * @return 成功返回0，失败返回-1
   */
  int Init(std::string cfg_path = "") override;
};

COMMON_REGISTER_NODE("InfraredNode", InfraredNode);

}  // namespace infrared
}  // namespace vita