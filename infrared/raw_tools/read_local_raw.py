import numpy as np
import cv2
import os
import argparse


def main():
    parser = argparse.ArgumentParser(description="读取本地红外 YUYV RAW 并导出对照图")
    parser.add_argument("raw_file", help="输入 .raw 文件")
    parser.add_argument("--width", type=int, default=640, help="图像宽度，默认 640")
    parser.add_argument("--height", type=int, default=480, help="预期图像高度，默认 480")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    args = parser.parse_args()

    if not os.path.exists(args.raw_file):
        print(f"错误: 找不到文件: {args.raw_file}")
        return

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"正在读取: {os.path.basename(args.raw_file)} ...")

    # 1. 读取二进制数据
    with open(args.raw_file, 'rb') as f:
        raw_bytes = f.read()
    
    # 转为 numpy 数组 (uint8)
    data_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    total_bytes = data_arr.size
    print(f"文件总大小: {total_bytes} 字节")

    # -------------------------------------------------
    # 模式 A: 【错误示范】强行按 RGB (3通道) 读取
    # -------------------------------------------------
    # RGB 模式下，每行需要的字节数 = 宽 * 3
    bytes_per_row_rgb = args.width * 3
    
    # 计算能凑出多少行
    height_rgb = total_bytes // bytes_per_row_rgb
    valid_bytes_rgb = height_rgb * bytes_per_row_rgb
    
    # 截取数据并 Reshape
    # 形状变为 (高度缩水, WIDTH, 3)
    glitch_data = data_arr[:valid_bytes_rgb].reshape((height_rgb, args.width, 3))
    
    # 注意：OpenCV 保存图片默认是用 BGR 顺序。
    # 为了模拟 Foxglove (RGB) 显示的效果，我们需要把 RGB 转为 BGR 保存，
    # 否则保存出来的颜色会和你在 Foxglove 看到的红蓝互换。
    glitch_img_bgr = cv2.cvtColor(glitch_data, cv2.COLOR_RGB2BGR)
    
    glitch_path = os.path.join(args.output_dir, "glitch_view.jpg")
    cv2.imwrite(glitch_path, glitch_img_bgr)
    print(f"[错位图] 已保存为 {glitch_path} ({args.width}x{height_rgb})")
    print(f"   -> 现象: 画面变扁，颜色呈现粉/绿交替。")

    # -------------------------------------------------
    # 模式 B: 【正确读取】按 YUYV (2通道) 读取并转灰度
    # -------------------------------------------------
    # YUYV 模式下，每行需要的字节数 = 宽 * 2
    bytes_per_row_yuv = args.width * 2
    
    height_yuv = total_bytes // bytes_per_row_yuv
    valid_bytes_yuv = height_yuv * bytes_per_row_yuv
    
    if height_yuv != args.height:
        print(f"注意: 计算出的高度 ({height_yuv}) 与预期 ({args.height}) 不符")
    else:
        print(f"高度符合预期: {height_yuv}")
    
    # 截取数据并 Reshape
    # 形状变为 (原始高度, WIDTH, 2)
    yuv_data = data_arr[:valid_bytes_yuv].reshape((height_yuv, args.width, 2))
    
    # 转换为灰度图 (丢弃 UV)
    gray_img = cv2.cvtColor(yuv_data, cv2.COLOR_YUV2GRAY_YUYV)
    
    correct_path = os.path.join(args.output_dir, "correct_view.jpg")
    cv2.imwrite(correct_path, gray_img)
    print(f"[还原图] 已保存为 {correct_path} ({args.width}x{height_yuv})")
    print(f"   -> 现象: 正常的黑白红外照片。")

if __name__ == "__main__":
    main()
