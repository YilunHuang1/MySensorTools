# Infrared image tools

Copy this folder and run `python3 -m pip install -r requirements.txt`. No ROS runtime or root project installation is needed.

```bash
python infrared/raw_tools/read_local_raw.py frame.raw --width 640 --height 480 --encoding mono8 --output-dir output/ir
python infrared/raw_tools/IrConverter.py capture.mcap --output-dir output/ir --max-frames 100
```

Dimensions, encoding and row stride must match the raw data. `IrConverter.py` now
exports source MCAP images and timestamp metadata; it no longer republishes ROS
messages. Mono8 and Y planes retain their original values. YUYV, UYVY, NV12 and
RGB/BGR conversion validate dimensions and buffer length. Use the buildable
`infrared/ir_qr_bench/ir_qr_bench.py` for bounded passive live capture and detection.
