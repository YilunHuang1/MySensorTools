# Foxglove 点云可视化集成

万集 WLR-722Z `/lidar_packets` → `/lidar_points` 可视化方案

---

## 两种方案对比

| | 方案 A：Message Converter | 方案 B：离线转换脚本 |
|---|---|---|
| **文件** | `vanjee_722z_converter.ts` | `mcap_add_lidar_points.py` |
| **原理** | Foxglove 内置 JS 脚本实时转换 | Python 生成含 `/lidar_points` 的新 MCAP |
| **依赖** | 无（Foxglove Desktop 内置） | `pip install mcap numpy` |
| **适合场景** | 快速调试，原始 mcap 不动 | 分享、归档，生成标准格式文件 |

---

## 方案 A：User Scripts（推荐，即开即用）

### 步骤

1. 打开 **Foxglove Desktop**，加载含 `/lidar_packets` 的 mcap

2. 左侧边栏点击 **`</>`** 图标（User Scripts），或菜单 **View → User Scripts**

3. 点击左上角 **`+`** 新建脚本

4. 将 `vanjee_722z_converter.ts` 的**全部内容**粘贴进去

5. **Ctrl+S** 保存，脚本自动编译（顶部无红色报错即成功）

6. 添加 **3D panel**，在 topic 列表选 `/lidar_points`，点云即显示 ✅

### 关于 `frame_id`

脚本输出 `frame_id: "lidar"`，如果你的 TF 树中有对应坐标系，点云会正确定位。
如需修改，编辑 `.ts` 文件中的：

```ts
frame_id: "lidar",
```

---

## 方案 B：Python 离线转换脚本

### 安装依赖

```bash
pip install mcap numpy
```

### 使用

```bash
# 基本用法（自动生成 *_with_points.mcap）
python3 foxglove/mcap_add_lidar_points.py  input.mcap

# 指定输出路径
python3 foxglove/mcap_add_lidar_points.py  input.mcap  output.mcap

# 只转换前 100 帧（快速验证）
python3 foxglove/mcap_add_lidar_points.py  input.mcap  -n 100

# 指定校准文件
python3 foxglove/mcap_add_lidar_points.py  input.mcap  -c path/to/VA.csv
```

### 在 Foxglove 中打开

1. 打开生成的 `*_with_points.mcap`
2. 添加 **3D panel**，订阅 `/lidar_points`
3. 点云显示（`sensor_msgs/PointCloud2`，含 x/y/z/intensity 字段）

---

## 技术细节

### 坐标转换

参考驱动 `decoder_vanjee_722z.hpp`：

```
horiz_final = (horiz_offset[ch] + azimuth * 10) % 360000  // 毫度
optcent_hor = (azimuth * 10 + 21570) % 360000              // 毫度

xy = distance * cos(vert[ch])
x  = xy * sin(horiz_final) + 0.02067 * sin(optcent_hor)
y  = xy * cos(horiz_final) + 0.02067 * cos(optcent_hor)
z  = distance * sin(vert[ch]) + 0.00795
```

### 帧切割

纯回落检测（对齐 C++ `SplitStrategyByAngle`）：

```
azimuth_trans = (azimuth + 60) % 36000
if azimuth_trans < prev_azimuth_trans → 新帧开始
```

### 校准文件

`config/calibration/Vanjee_722z_VA.csv`：每行 `vert_deg, horiz_deg`，16 通道。
