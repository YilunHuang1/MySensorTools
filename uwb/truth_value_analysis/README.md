# UWB 真值准度分析（距离 & 角度）

本目录提供一个面向批量 MCAP 数据的分析脚本，基于文件名真值（距离/角度/高度）计算测量误差，生成每文件与总体统计报告，并输出角度误差可视化图。

## 数据命名规范

MCAP 文件名格式应为：

- `距离_角度_高度_序号.mcap`
- 示例：`50_30_25_0.mcap`

解析规则：

- 距离：cm（输出统计统一换算为 m）
- 角度：deg（归一化到 `[0, 360)`）
- 高度：cm（当前用于筛选，不参与统计指标）

## 运行方式

主入口脚本：`uwb_analysis_pipeline.py`

```bash
python uwb_analysis_pipeline.py --help
```

常用示例：

```bash
python uwb_analysis_pipeline.py -s /path/to/mcap_dir --recursive
```

按高度筛选（单位 cm）：

```bash
python uwb_analysis_pipeline.py -s /path/to/mcap_dir --recursive --filter-height 25
```

运行自检（验证文件名解析与角度误差环形差值计算，不依赖 mcap 数据）：

```bash
python uwb_analysis_pipeline.py --self-test
```

## 输出说明

输出根目录：`processed_results/`

- `per_file_stats/`
  - 每个文件的统计汇总（含距离/角度均值、标准差、绝对误差/相对误差统计、异常计数等）
- `overall/`
  - `overall_summary.csv`：总体原始距离/角度分布统计
  - `overall_diff_summary.csv`：总体距离/角度误差分布统计（mean/std/min/max/median）
  - `overall_summary.pdf`：总体可视化（含误差直方图与箱线图）
  - `diff_stats_documentation.md`：误差与异常检测指标定义说明
  - `self_test_report.md`：自检报告（仅在 `--self-test` 运行时生成）
- `accuracy_reports/`
  - `*_accuracy_detail.csv`：逐点误差明细（distance/angle 的 abs diff 与 rel error）
  - `*_accuracy_report.md`：每文件距离+角度准度报告
  - `overall_accuracy_summary.csv` / `overall_accuracy_summary.md`：总体准度摘要
  - `plots/`：角度误差可视化
    - `*_angle_error_polar.png`：角度误差极坐标分布
    - `*_angle_error_scatter.png`：测量角度-有符号误差散点图
    - `overall_angle_error_polar.png`：按真值角度汇总的极坐标图（文件级）

## 配置

可通过配置文件调整 topic 名称、字段映射、阈值等参数。示例参考 `config_example.json`，使用时复制为本地配置文件即可。
