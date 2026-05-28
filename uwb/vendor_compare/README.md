# UWB数据专业分析系统

专业分析飞睿(Feirui)和全迹(Quanji)UWB测试数据的完整解决方案，支持静态和动态测试数据的全面对比分析。

## 🎯 功能特性

### 静态测试数据分析
- **统计分析**: 测距和测角数据的均值、标准差、最大/最小值计算
- **可视化展示**: 箱线图、误差带图、热力图展示数据分布特征
- **精度对比**: 相同坐标尺度下的稳定性对比
- **性能评估**: 标准差标注和参考真值线对比

### 动态测试数据分析
- **轨迹分析**: 
  - 飞睿数据: 验证x_m/y_m与distance_cm/azimuth_deg的计算关系
  - 全迹数据: 统一采用平面极坐标→XY转换（不使用pitch）
- **轨迹可视化**: 二维平面轨迹图，标注运动方向和跳变点
- **性能指标**: 轨迹长度、移动速度、活动范围分析
- **处理范围**: 仅处理类型4/5（active_4/active_5），其他类型将被忽略；如数据中存在类型列（如`type`或`类型`），将进行类型过滤。

### 对比分析
- **组内对比**: 相同设备不同测试条件下的稳定性对比
- **组间对比**: 两组设备在相同条件下的性能差异分析
- **综合评估**: 测量稳定性排名和关键性能指标对比表

## 📁 项目结构

```
uwb_comnpare_feirui_quanji/
├── feirui_test/                    # 飞睿测试数据
│   ├── 1.2m_uwb_data_*.csv        # 1.2m静态测试
│   ├── 1.2m_block_uwb_data_*.csv  # 1.2m遮挡测试
│   ├── 2.4m_uwb_data_*.csv        # 2.4m静态测试
│   ├── 2.4m_block_uwb_data_*.csv  # 2.4m遮挡测试
│   └── active_*_uwb_data_*.csv    # 动态测试
├── quanji_test/                    # 全迹测试数据
│   ├── 1.2m_log-*.csv             # 1.2m静态测试
│   ├── 1.2m_block_log-*.csv       # 1.2m遮挡测试
│   ├── 2.4m_log-*.csv             # 2.4m静态测试
│   ├── 2.4m_block_log-*.csv       # 2.4m遮挡测试
│   └── active_*_log-*.csv         # 动态测试
├── uwb_data_analyzer.py            # 数据分析核心模块
├── uwb_visualizer.py               # 可视化模块
├── main_analysis.py                # 主程序
├── requirements.txt                # 依赖包列表
└── README.md                       # 使用说明
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装依赖包
pip install -r requirements.txt
```

### 2. 运行分析

```bash
# 基本用法 - 使用默认参数
python main_analysis.py

# 指定数据目录和输出目录
python main_analysis.py -d /path/to/data -o /path/to/output

# 不保存图表（仅生成分析结果）
python main_analysis.py --no-plots

# 不生成综合报告
python main_analysis.py --no-report
```

### 3. 查看结果

分析完成后，结果将保存在 `analysis_results/` 目录中：

```
analysis_results/
├── static_distance_comparison.png      # 静态距离精度对比
├── static_angle_comparison.png         # 静态角度精度对比
├── error_bands_analysis.png            # 误差带时间序列分析
├── stability_radar_chart.png           # 稳定性雷达图
├── performance_heatmap.png             # 性能对比热力图
├── dynamic_trajectories.png            # 动态轨迹对比
├── comprehensive_report.png            # 综合分析报告
├── analysis_report.txt                 # 文本格式报告
└── analysis_results.json               # 详细分析数据
```

## 📊 数据格式说明

### 飞睿数据格式
```csv
timestamp,packet_seq,module_id,distance_cm,azimuth_deg,x_m,y_m,a_fom,rssi_dbm
```

### 全迹数据格式
```csv
原始距离,原始角度,车中心距离,x,y,锚点偏移Y,车中心偏移Y,距离车边缘距离,距离偏移,角度偏移,尾距离偏移,尾角度偏移,滤波窗口,排除比例,index,key,时间,锚点时间ms,rx_power,rssi_fpp,rssi_np,rssi_ble,pitch
```
说明：处理逻辑统一为XY坐标（x_m,y_m），`distance_m`优先使用`车中心距离`，若不存在则回退到`原始距离`；如存在`pitch`列则忽略，不参与处理。

## 🔧 高级用法

### 单独使用分析器

```python
from uwb_data_analyzer import UWBDataAnalyzer

# 创建分析器
analyzer = UWBDataAnalyzer("data_directory")

# 加载数据
analyzer.load_all_data()

# 执行分析
static_results = analyzer.analyze_static_data()
dynamic_results = analyzer.analyze_dynamic_data()
```

### 单独使用可视化器

```python
from uwb_visualizer import UWBVisualizer

# 创建可视化器
visualizer = UWBVisualizer("output_directory")

# 生成图表
visualizer.plot_static_comparison(static_results)
visualizer.plot_dynamic_trajectories(feirui_data, quanji_data, dynamic_results)
```

## 📈 分析指标说明

### 静态测试指标
- **距离精度**: 测量值与真值的偏差
- **角度稳定性**: 角度测量的标准差
- **数据质量**: 有效数据点数量和变异系数
- **稳定性评分**: 综合考虑精度和稳定性的评分

### 动态测试指标
- **轨迹长度**: 总移动距离
- **活动范围**: X和Y方向的最大活动范围
- **平均步长**: 相邻测量点间的平均距离
- **速度统计**: 移动速度的均值、标准差和最大值

## 📝 更新日志

### v1.1.0 (2025-10-24)
- 新增：自动发现并整合新增动态测试数据（active_*）。
- 简化：Quanji静态数据处理去除pitch，统一采用XY坐标（x_m/y_m）。
- 更新：动态轨迹图支持可变测试组并统一坐标引用。
- 文档：更新数据格式与处理说明，强调统一的XY坐标。

### v1.0.0 (2025-01-XX)
- 初始版本发布
- 支持飞睿和全迹数据分析
- 完整的静态和动态测试分析功能
- 专业的可视化和报告生成

## 📄 许可证

本项目采用 MIT 许可证 - 详见 LICENSE 文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！

## 📧 联系方式

如有问题或建议，请联系项目维护者。