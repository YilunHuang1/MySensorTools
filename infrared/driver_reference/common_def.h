#pragma once

namespace vita {
namespace infrared {
// 红外相机相关常量
inline constexpr static const char* kInfraredCameraName = "infrared";
inline constexpr static const char* kInfraredImageTopic =
    "/infrared_camera/image_raw";
inline constexpr static const char* kInfraredH265Topic =
    "/infrared_camera/video_h265";

}  // namespace infrared
}  // namespace vita