# 快速开始

## 5 秒上手

```bash
cd lidar/packets_parse
python scripts/extract.py
```

**输出**: `pcd_output/` 目录中的 PCD 文件

---

## 完整命令

```bash
# 基本提取
python scripts/extract.py

# 指定输入/输出
python scripts/extract.py --mcap /path/to/file.mcap -o /output/dir

# 只提取前 50 帧 (快速测试)
python scripts/extract.py --max-frames 50

# 详细日志
python scripts/extract.py -v

# 使用不同型号的校准
python scripts/extract.py --model 722
```

---

## 文件格式

**输入**: MCAP 文件 (ROS2 bag 格式)
```
mcap_data/0000000000000000115_vita-evt-pre-115_1774257429901000000.mcap
```

**输出**: PCD 点云文件 (ASCII 格式，包含 XYZI)
```
pcd_output/
  ├─ frame_0001_1774257429.901083231.pcd   (9850 点)
  ├─ frame_0002_1774257430.240137815.pcd   (5997 点)
  └─ ...
  └─ frame_1316_1774257692.835584164.pcd   (1099 点)
```

**文件名含义**:
- `frame_XXXX`: 帧序号 (从 0001 开始)
- `TTTTTTTTTT.TTTTTTTTT`: MCAP PTP 时间戳 (秒级，纳秒精度)

---

## 环境要求

```bash
# 依赖
pip install mcap numpy open3d

# 验证
python -c "from mcap.reader import make_reader; print('✓ mcap 库就绪')"
```

---

## Python API

```python
from src.core.calibration import CalibrationManager
from src.core.extractor import FrameExtractor
from mcap.reader import make_reader

# 1. 加载校准参数
calib = CalibrationManager()
calib.load_default('722z')
vert_angles, horiz_angles = calib.get_all_angles()

# 2. 初始化提取器
extractor = FrameExtractor(vert_angles, horiz_angles, 'output/')

# 3. 读取 MCAP 并提取
with open('data.mcap', 'rb') as f:
    reader = make_reader(f)
    for schema, channel, message in reader.iter_messages():
        results = extractor.process_message(message)
        for azimuth, points, ts in results:
            extractor.save_frame(frame_id, points, ts)
```

---

## 故障排除

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError: No module named 'mcap'` | `pip install mcap` |
| `FileNotFoundError: 校准文件不存在` | 检查 `config/calibration/` 目录 |
| 点云数量少 | 正常 (距离过滤已应用，94% 的点被过滤) |
| 提取速度慢 | 使用 `--max-frames` 测试 |

更多: 见 `docs/TROUBLESHOOTING.md`
