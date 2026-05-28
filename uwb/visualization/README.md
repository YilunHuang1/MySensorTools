# UWB 数据分析与可视化（uwb_data_ansys）

本文件夹用于处理、分析与可视化超宽带（UWB）测试数据。各脚本以 CSV 为主要输入，支持静态散点图、动态轨迹动画、三维交互图及密度过滤等常用分析方式，方便快速验证与展示。

---

## 目录用途
- 汇总与维护 UWB 相关的数据可视化脚本，面向实验验证与结果展示。
- 针对不同数据形态（原始距离/角度、二维坐标、俯仰角与高度等），提供相应的图形化输出。
- 便于在同一目录下统一管理、复用与迭代可视化能力。

## 环境依赖
- Python：建议 3.9 及以上。
- 必需依赖：
  - pandas（CSV 读写与数据处理）
  - matplotlib（二维绘图与动画）
  - numpy（数值计算与角度转换）
- 可选依赖：
  - scikit-learn（`uwb_data_plot.py` 的密度过滤）
  - plotly（`quanji_data_plot2.py` 的 3D 交互式可视化）
  - PyQt5 或 PySide2（当使用 `Qt5Agg` 后端显示时）

安装示例：
```bash
pip install pandas matplotlib numpy scikit-learn plotly
# 如使用 Qt5Agg 后端：
pip install PyQt5
```

---

## 主要脚本与功能说明

### quanji_data_plot.py
- 功能：读取 `x`、`y` 列并绘制静态散点图；正方形画布，坐标比例一致，带网格线。
- 预期列：`x`, `y`。
- 适用场景：观察坐标点的总体分布与范围。
- 运行：修改脚本顶部 `file_path` 为你的 CSV 路径后执行。

### quanji_data_plot_active.py
- 功能：读取 `x`、`y`，以动画逐帧展示轨迹点的动态变化；可设置帧间隔（毫秒）。
- 预期列：`x`, `y`。
- 适用场景：展示轨迹随时间/序列的演进过程。
- 运行：修改 `file_path` 后执行；如需调整动画速度，修改 `interval` 参数。

### quanji_data_plot_active_compare.py
- 功能：读取 `原始距离`、`原始角度`、`x`、`y`；将角度从度转弧度，计算 `calculated_x = 原始距离 * cos(θ)`、`calculated_y = 原始距离 * sin(θ)`；以动画对比原始坐标轨迹与计算坐标轨迹。
- 预期列：`原始距离`, `原始角度`, `x`, `y`。
- 适用场景：检验原始测距离/角度与坐标反算的一致性与偏差。
- 运行：修改 `file_path` 后执行；必要时根据设备坐标系调整角度方向或符号。

### quanji_data_plot_active_ori.py
- 功能：读取 `原始距离`、`原始角度`，转弧度后计算 `calculated_x`/`calculated_y` 并以动画展示；包含初始延迟提示；绘图后端设为 `Qt5Agg`。
- 预期列：`原始距离`, `原始角度`。
- 适用场景：仅基于原始距离与角度的动态轨迹演示与验证。
- 运行：修改 `file_path` 后执行；如使用 `Qt5Agg` 报错，请安装 `PyQt5` 或更换为系统可用后端（如 `MacOSX`）。

### quanji_data_plot2.py
- 功能：读取 `原始距离`、`pitch`、`x`、`y`；由距离与俯仰角计算 `z`（高度），生成 Plotly 交互式 3D 散点；同时进行水平距离校验并输出 Z 高度统计信息。
- 预期列：`原始距离`, `pitch`, `x`, `y`。
- 适用场景：进行三维空间关系的验证、查看高度分布与统计。
- 运行：修改 `file_path` 后执行；首次使用需安装 `plotly`。

### uwb_data_plot.py
- 功能：读取 `x_m`、`y_m`（单位米）；可选使用基于最近邻的密度过滤以移除孤立点（`n_neighbors`、`distance_threshold` 可调）；绘制原始点与保留点，并在 ±30° 与 ±60° 方向绘制虚线参考；坐标比例一致。
- 预期列：`x_m`, `y_m`。
- 适用场景：室内 UWB 点云数据的清理与在参考方向下的分布观察。
- 运行：修改 `file_path` 后执行；如需开启过滤，将 `apply_filter=True` 并调整参数。

---

## 数据格式说明（按脚本）
- 坐标类：
  - `x`, `y`：浮点数，单位视采集方案而定（常为米）。
  - `x_m`, `y_m`：浮点数，单位米。
- 原始测量类：
  - `原始距离`：浮点数，单位米。
  - `原始角度`：浮点数，单位度（脚本会转为弧度参与计算）。
  - `pitch`：浮点数，单位度（用于计算高度 `z`）。
- 计算列（脚本内生成）：
  - `calculated_x`, `calculated_y`：由 `原始距离` 与 `原始角度` 计算得到。
  - `z`：由 `原始距离` 与 `pitch` 计算得到的高度。

---

## 使用说明（快速开始）
1. 将各脚本顶部的 `file_path` 修改为你的 CSV 文件路径。
2. 在当前目录下执行脚本，例如：
```bash
python quanji_data_plot.py
python quanji_data_plot_active.py
python quanji_data_plot_active_compare.py
python quanji_data_plot_active_ori.py
python quanji_data_plot2.py
python uwb_data_plot.py
```
3. 按需调整参数：
   - 动画：`interval`（毫秒）、`initial_delay`（秒）。
   - 过滤：`n_neighbors`（邻居数量阈值）、`distance_threshold`（距离阈值，米）。

---

## 使用注意事项
- 路径配置：示例路径为本地样例，需改为你的数据路径。
- 字体与中文显示：
  - 若中文不显示，请调整 `plt.rcParams["font.family"]` 或安装中文字体（如 `SimHei`）。
  - `axes.unicode_minus=False` 可确保负号正常显示。
- Matplotlib 后端：
  - `quanji_data_plot_active_ori.py` 使用 `Qt5Agg` 后端；如报错，请安装 `PyQt5` 或切换后端。
- 单位与角度方向：
  - 角度为度需转为弧度；角度零点与正负方向应与设备安装和坐标系约定一致。
- 数据清洗：
  - CSV 中如包含 NUL（`\0`）字符可能导致无法打开或解析，需先清理再使用。
- 输出保存：
  - 目前脚本以显示为主；可在展示前添加 `plt.savefig("out.png", dpi=300)` 保存静态图，或使用 `matplotlib.animation` 保存 GIF/MP4（需安装对应 writer）。
- 依赖按需安装：
  - `scikit-learn` 用于密度过滤；`plotly` 用于 3D 交互。按需安装以保持环境简洁。

---

## 版本更新记录（文档）
- 2025-10-20 v0.1
  - 新增：README 初版，梳理脚本用途、数据格式与使用方式。
  - 说明：脚本版本以源代码为准；此记录仅针对文档变更。

---

## 维护建议
- 将硬编码的 `file_path` 改为命令行参数（`argparse`）或统一配置文件，支持批量运行。
- 为关键计算与过滤逻辑添加单元测试与数据校验，提升鲁棒性。
- 统一输出目录与命名规范（如 `charts/`、`reports/`），便于归档与比对。
- 在文档中补充坐标系定义、角度转换约定与单位说明，减少歧义。