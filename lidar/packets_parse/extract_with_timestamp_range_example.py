#!/usr/bin/env python3
"""
使用时间戳范围过滤提取 LiDAR 数据的示例

场景：只提取某个特定时间段的 LiDAR 数据，例如问题发生的时刻
"""

import extract_lidar_pcd_with_ts as m

# ============================================================
# 配置：指定时间戳范围
# ============================================================

# 例1：只提取日志中问题时间段（15:11:14.048 ~ 15:11:15.170）
#      对应 Unix 时间戳：1778051474.048 ~ 1778051475.170
#      这是 lowlevel 崩溃 + 两个 Drop 事件的时间段
print("示例1: 提取问题时间段 15:11:14.048 ~ 15:11:15.170")
m.TIMESTAMP_RANGE = (1778051474.048, 1778051475.170)
m.SAVE_PCD = True   # 保存 PCD 文件以便查看点云
m.OUTPUT_DIR = 'pcd_output_problem_period'
m.main()

print("\n" + "="*70)
print("提示:")
print("1. 可以修改上面的 TIMESTAMP_RANGE 来指定不同的时间段")
print("2. 格式: (start_unix_ts, end_unix_ts)")
print("3. 例如只提取 1 秒的数据:")
print("   TIMESTAMP_RANGE = (1778051474.048, 1778051474.148)")
print("4. 如果设为 None，表示解析全部数据（默认）")
