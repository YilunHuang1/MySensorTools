# UWB测试数据版本记录

本文件用于维护项目测试数据的版本信息与变更记录，确保数据格式一致、处理逻辑可追踪。

## v1.1.0 (2025-10-24)
- 新增：自动发现并整合动态测试数据组（active_*），当前新增 `active_4`, `active_5`。
- 简化：Quanji静态数据处理移除 pitch，统一采用平面极坐标→XY（x_m/y_m），与 Feirui 保持一致。
- 规范：Quanji静态距离统一为车中心距离（优先），如不存在则回退到原始距离。
- 验证：新增统一数据字段验证（distance_m, azimuth_deg, x_m, y_m），自动补齐缺失字段并输出验证结果。
- 范围：动态数据仅处理类型4和类型5（active_4/active_5），其他类型忽略，并在存在类型列时进行过滤。
- 校准：Quanji角度统一应用固定偏移 `+60°`（azimuth_deg += 60.0），影响静态与动态XY计算及角度统计。

### 数据格式与字段
- Feirui：`timestamp, distance_cm → distance_m, azimuth_deg, x_m, y_m`
- Quanji：`distance_m` 优先采用 `车中心距离`，无则使用 `原始距离`；`原始角度 → azimuth_deg`；如存在 `pitch` 列则忽略。

### 兼容性说明
- 统一坐标计算：`x_m = distance_m * sin(azimuth_deg)，y_m = distance_m * cos(azimuth_deg)`。
- 所有分析与可视化统一使用 `x_m / y_m` 坐标，不再依赖 VCS 坐标或 pitch。

### 验证输出
- 验证结果写入：`analysis_results/analysis_results.json -> metadata.validation`。
- 数据版本写入：`analysis_results/analysis_results.json -> metadata.data_version`，当前为 `v1.1.0`。

## 历史版本
- v1.0.0：初始化数据与分析流程，支持静态与动态测试基本分析与可视化。