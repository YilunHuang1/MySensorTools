#include <csignal>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "aorta/aorta.h"
#include "stereo_get_jpeg_images_msg.h"

namespace aorta_stereo = ::aorta::services::stereo;

int main(int argc, char* argv[]) {
  (void)aorta::InitLoggingFromEnv();

  std::string node_name = "stereo_aorta_jpeg_client";
  std::string group = "default";
  std::string service_name = "/get_jpeg_images";
  std::string output_path = "/tmp/aorta_stereo.jpg";
  uint32_t channel_id = 0;
  uint32_t width = 1920;
  uint32_t height = 1080;
  uint16_t quality = 85;
  bool undistort = false;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--name" && i + 1 < argc) {
      node_name = argv[++i];
    } else if (arg == "--group" && i + 1 < argc) {
      group = argv[++i];
    } else if (arg == "--service" && i + 1 < argc) {
      service_name = argv[++i];
    } else if (arg == "--output" && i + 1 < argc) {
      output_path = argv[++i];
    } else if (arg == "--channel" && i + 1 < argc) {
      channel_id = static_cast<uint32_t>(std::stoul(argv[++i]));
    } else if (arg == "--width" && i + 1 < argc) {
      width = static_cast<uint32_t>(std::stoul(argv[++i]));
    } else if (arg == "--height" && i + 1 < argc) {
      height = static_cast<uint32_t>(std::stoul(argv[++i]));
    } else if (arg == "--quality" && i + 1 < argc) {
      quality = static_cast<uint16_t>(std::stoul(argv[++i]));
    } else if (arg == "--undistort") {
      undistort = true;
    }
  }

  auto node = aorta::Must(aorta::Node::Create(node_name, group), "Create node");
  auto client = aorta::Must(
      node->CreateClientTyped<aorta_stereo::GetJpegImagesRequest,
                              aorta_stereo::GetJpegImagesResponse>(service_name),
      "Create get_jpeg_images client");

  auto call_result = client->Call([&](aorta_stereo::GetJpegImagesRequestMsg& msg) {
    auto item = std::make_shared<aorta_stereo::JpegRequestItemMsg>();
    item->channel_id = channel_id;
    item->width = width;
    item->height = height;
    item->quality = quality;
    item->undistort = undistort;
    msg.request = std::vector<std::shared_ptr<aorta_stereo::JpegRequestItemMsg>>{
        std::move(item)};
  });

  if (!call_result.ok()) {
    std::cerr << "Aorta get_jpeg_images call failed: "
              << call_result.status().message() << std::endl;
    return 1;
  }

  auto response = std::move(call_result).value();
  const auto* message = response.Message();
  if (message == nullptr || message->response() == nullptr ||
      message->response()->empty()) {
    std::cerr << "Aorta get_jpeg_images returned empty response" << std::endl;
    return 1;
  }

  const auto* item = message->response()->Get(0);
  if (item == nullptr || item->status() != 0 || item->data() == nullptr) {
    std::cerr << "Aorta get_jpeg_images returned error status" << std::endl;
    return 1;
  }

  std::ofstream output(output_path, std::ios::binary);
  if (!output.is_open()) {
    std::cerr << "Failed to open output path: " << output_path << std::endl;
    return 1;
  }

  output.write(reinterpret_cast<const char*>(item->data()->Data()),
               static_cast<std::streamsize>(item->data()->size()));
  output.close();

  std::cout << "Saved JPEG to " << output_path << " ("
            << item->width() << "x" << item->height() << ")" << std::endl;
  return 0;
}