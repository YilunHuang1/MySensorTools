/*
 * Copyright (C) Vita Dynamics, Inc. - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 */

#include "infrared_node.h"

#include "logger/vlog.h"

namespace vita {
namespace infrared {

int InfraredNode::Init(std::string cfg_path) {
  // 调用基类的初始化方法
  if (BaseNode::Init(cfg_path) != 0) {
    return -1;
  }

  VLOGI("Successfully initialized infrared node");
  return 0;
}

}  // namespace infrared
}  // namespace vita