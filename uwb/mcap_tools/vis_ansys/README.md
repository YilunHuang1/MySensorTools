# UWB MCAP 处理工具（简洁版）

本工具读取与现有数据一致的 MCAP（ROS2/CDR）文件，解析 UWB 消息并输出 CSV，同时提供 2D/3D 轨迹可视化。

## 安装依赖

```
pip install mcap pandas numpy matplotlib plotly
```

Plotly 为可选依赖，仅用于交互式图。

## 快速开始

1) 将 MCAP 转 CSV：

```
python mcap_to_csv.py /path/to/file.mcap -o /path/to/out.csv
```

处理大文件时建议使用流式模式：

```
python mcap_to_csv.py /path/to/file.mcap -o out.csv --stream --flush-every 2000 -c config.ini
```

关键输出列：
- `timestamp_sec`：消息时间戳（秒）
- `device_id`：设备ID（基于路径推断，007/062）
- `raw_x_m`/`raw_y_m`：原始坐标（m）
- `filtered_x_m`/`filtered_y_m`：滤波坐标（m）
- `z_m_est`：基于 `distance * sin(pitch)` 的高度估计
- `rssi_mean`/`rssi_min`/`rssi_max`：信号强度聚合（裁剪于[-100, 0]）
- 其他：`angle`/`distance`/`pos_confidence`/`has_living_body`/`has_head_touch` 等

2) 可视化（输出到 `charts` 目录）：

```
python visualization.py out.csv -o charts
```

交互式图（需安装 plotly）：

```
python visualization.py out.csv -o charts --interactive
```

## 配置说明（config.ini）

```
[parse]
topic = /uwb/data

[clean]
min_distance_m = 0.0
max_distance_m = 50.0
pos_confidence_min = 0
drop_zero_distance = false
angle_normalize = true
rssi_clip_min = -100
rssi_clip_max = 0

[output]
flush_every = 2000
```

## 注意事项

- 角度统一到 `0..360`，062 版本的负角按 `360 + angle` 处理。
- `device_id` 通过文件路径中的版本（007/062）推断，不影响数值解析。
- 大文件建议开启 `--stream` 以降低内存占用。
- 若 CSV 中 `rssi` 列为 JSON 字符串，旨在保留原始序列结构完整性。

## 许可

本工具随项目一起使用，不单独提供许可声明。