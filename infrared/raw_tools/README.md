# 红外相机 RAW 工具集

本目录包含两个用于处理红外相机 YUYV RAW 数据的工具脚本。

---

## 工具说明

### 1. `IrConverter.py` — ROS 2 实时转换节点

**用途**：在 ROS 2 环境中，订阅红外相机发布的 YUV422（YUYV）格式原始图像话题，实时转换为 `mono8` 灰度图后重新发布，可直接在 Foxglove 等工具中正常显示。

**原理**：
- 订阅：`/infrared_camera/image_raw`（YUV422 格式）
- 转换：提取 Y 通道 → 灰度图（丢弃 UV 色彩分量）
- 发布：`/infrared_camera/image_mono`（mono8 格式）
- **无需 `cv_bridge`**，手动构建 ROS 2 Image 消息，兼容性更好。

**依赖**：
```bash
pip install rclpy numpy opencv-python
```

**运行方式**：
```bash
python3 IrConverter.py
```

**说明**：需在已初始化的 ROS 2 环境中运行（`source /opt/ros/<distro>/setup.bash`）。

---

### 2. `read_local_raw.py` — 本地 RAW 文件解析对比工具

**用途**：读取本地保存的红外相机 `.raw` 二进制文件（YUYV 格式），导出两张对比图，直观展示**错误读取（RGB 模式）** 与 **正确读取（YUYV→灰度）** 的区别。

**依赖**：
```bash
pip install numpy opencv-python
```

**运行方式**：
```bash
python3 read_local_raw.py <raw_file> [--width WIDTH] [--height HEIGHT] [--output-dir OUTPUT_DIR]
```

**参数说明**：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `raw_file` | ✅ | — | 输入的 `.raw` 文件路径 |
| `--width` | ❌ | `640` | 图像宽度（像素） |
| `--height` | ❌ | `480` | 图像预期高度（像素），用于校验 |
| `--output-dir` | ❌ | `.`（当前目录） | 输出图片保存目录 |

**示例**：
```bash
# 基本用法
python3 read_local_raw.py frame_001.raw

# 指定分辨率和输出目录
python3 read_local_raw.py frame_001.raw --width 640 --height 480 --output-dir ./output
```

**输出文件**：

| 文件名 | 说明 |
|--------|------|
| `glitch_view.jpg` | ❌ **错误示范**：将 YUYV 数据强行按 RGB 3通道解析，画面变扁、呈现粉/绿交替色块 |
| `correct_view.jpg` | ✅ **正确还原**：按 YUYV 2通道解析并转灰度，正常的黑白红外图像 |

---

## 背景知识

红外相机原始数据通常以 **YUYV（YUV422）** 格式输出：
- 每个像素占 **2 字节**（Y + UV 交替排列）
- 分辨率 640×480 对应文件大小 = `640 × 480 × 2 = 614,400 字节`
- 若误按 RGB（3字节/像素）解析，会导致图像高度缩水（约 2/3）且颜色错乱

正确处理方式：用 `cv2.COLOR_YUV2GRAY_YUYV` 仅提取亮度（Y）通道即可得到清晰灰度图。
