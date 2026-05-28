#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quanji 1.2m 静态数据核查与重新计算脚本
- 目标文件: quanji_test/1.2m-log-2025_10_24-14_38_52_218.csv
- 输出:
  - analysis_results/quanji_1_2m_static_recheck.json
  - analysis_results/plots/quanji_1_2m_static_angle_hist.png
  - analysis_results/plots/quanji_1_2m_static_angle_ts.png
  - analysis_results/plots/quanji_1_2m_static_distance_hist.png
"""

import json
import math
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).parent
CSV_PATH = BASE_DIR / "quanji_test/1.2m_log-2025_10_24-14_38_52_218.csv"
OUT_DIR = BASE_DIR / "analysis_results"
PLOTS_DIR = OUT_DIR / "plots"
OUT_JSON = OUT_DIR / "quanji_1_2m_static_recheck.json"
ORIG_JSON = OUT_DIR / "analysis_results.json"

ANGLE_COL = "原始角度"
DIST_CENTER_COL = "车中心距离"
TIME_STR_COL = "时间"
ANCHOR_MS_COL = "锚点时间ms"

def parse_time(s: str):
    try:
        return datetime.strptime(s, "%Y_%m_%d-%H_%M_%S_%f")
    except Exception:
        return None

def ensure_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_csv():
    df = pd.read_csv(CSV_PATH)
    return df


def recompute_angle_stats(angle_series: pd.Series):
    # 去除不可用与缺失
    angle = pd.to_numeric(angle_series, errors="coerce")
    angle_valid = angle.dropna()
    n = len(angle_valid)

    mean_val = angle_valid.mean()
    # 用户指定公式：std = sqrt(mean((x - mean)^2)) ——总体标准差
    pop_var = ((angle_valid - mean_val) ** 2).mean()
    pop_std = math.sqrt(pop_var)
    # 样本标准差（ddof=1）
    sample_std = angle_valid.std(ddof=1)

    return {
        "count": n,
        "mean": float(mean_val) if n > 0 else None,
        "std_population": float(pop_std) if n > 0 else None,
        "std_sample": float(sample_std) if n > 1 else None,
        "min": float(angle_valid.min()) if n > 0 else None,
        "max": float(angle_valid.max()) if n > 0 else None,
        "all_equal": bool(n > 0 and angle_valid.nunique() == 1),
        "unique_values": int(angle_valid.nunique()) if n > 0 else 0
    }


def summarize_numeric_columns(df: pd.DataFrame):
    summary = {}
    dtypes = {}
    conversion_notes = {}

    for col in df.columns:
        dtypes[col] = str(df[col].dtype)
        # 尝试数值化（不影响原df，仅用于统计）
        col_num = pd.to_numeric(df[col], errors="coerce")
        valid = col_num.dropna()
        n = len(valid)
        if n > 0:
            summary[col] = {
                "count": n,
                "min": float(valid.min()),
                "max": float(valid.max()),
                "mean": float(valid.mean()),
                "std_sample": float(valid.std(ddof=1)) if n > 1 else None,
                "nan_count": int(col_num.isna().sum()),
                "nan_ratio": float(col_num.isna().mean()),
            }
        else:
            summary[col] = {
                "count": 0,
                "note": "非数值或全部非数值化",
            }
        # 标注可能的类型问题
        if summary[col].get("count", 0) == 0 and df[col].dtype == object:
            conversion_notes[col] = "对象列可能含非数值内容（例如字符串，如'<0m'或键值）"
    return summary, dtypes, conversion_notes


def check_time_continuity(df: pd.DataFrame):
    result = {"time_string": {}, "anchor_ms": {}}
    # 时间字符串
    if TIME_STR_COL in df.columns:
        # 统一使用 pandas 的 to_datetime 解析为 datetime64[ns]
        t_series = pd.to_datetime(df[TIME_STR_COL], format="%Y_%m_%d-%H_%M_%S_%f", errors="coerce")
        valid_times = t_series.dropna()
        if len(valid_times) > 1:
            # 直接使用 dt.total_seconds() 获取毫秒差，确保为 float64 类型
            deltas = valid_times.diff().dropna().dt.total_seconds() * 1000.0
            result["time_string"] = {
                "count": int(len(valid_times)),
                "not_parsed": int(t_series.isna().sum()),
                "delta_ms_min": float(deltas.min()),
                "delta_ms_max": float(deltas.max()),
                "delta_ms_mean": float(deltas.mean()),
                "delta_ms_std": float(deltas.std(ddof=1)) if len(deltas) > 1 else None,
                "non_monotonic": bool((deltas <= 0).any()),
            }
        else:
            result["time_string"] = {"count": int(len(valid_times)), "note": "时间列解析不足或缺失"}
    else:
        result["time_string"] = {"note": "未找到时间列"}

    # 锚点时间ms
    if ANCHOR_MS_COL in df.columns:
        ms_num = pd.to_numeric(df[ANCHOR_MS_COL], errors="coerce")
        valid_ms = ms_num.dropna()
        if len(valid_ms) > 1:
            deltas = valid_ms.diff().dropna()
            result["anchor_ms"] = {
                "count": int(len(valid_ms)),
                "nan_count": int(ms_num.isna().sum()),
                "delta_ms_min": float(deltas.min()),
                "delta_ms_max": float(deltas.max()),
                "delta_ms_mean": float(deltas.mean()),
                "delta_ms_std": float(deltas.std(ddof=1)) if len(deltas) > 1 else None,
                "non_monotonic": bool((deltas <= 0).any()),
            }
        else:
            result["anchor_ms"] = {"count": int(len(valid_ms)), "note": "锚点时间不足或缺失"}
    else:
        result["anchor_ms"] = {"note": "未找到锚点时间ms列"}
    return result


def compare_with_original(angle_stats: dict):
    comparison = {"exists": False}
    try:
        with ORIG_JSON.open("r", encoding="utf-8") as f:
            orig = json.load(f)
        orig_angle = orig["static_analysis"]["1.2m_static"]["Quanji"]["angle"]
        comparison = {
            "exists": True,
            "original_mean": orig_angle.get("mean"),
            "original_std": orig_angle.get("std"),
            "recomputed_mean": angle_stats.get("mean"),
            "recomputed_std_population": angle_stats.get("std_population"),
            "recomputed_std_sample": angle_stats.get("std_sample"),
            "delta_mean": (angle_stats.get("mean") - orig_angle.get("mean")) if angle_stats.get("mean") is not None else None,
            "delta_std": (angle_stats.get("std_sample") - orig_angle.get("std")) if angle_stats.get("std_sample") is not None else None,
        }
    except Exception:
        pass
    return comparison


def make_plots(df: pd.DataFrame):
    # 角度直方图
    angle = pd.to_numeric(df[ANGLE_COL], errors="coerce") if ANGLE_COL in df.columns else pd.Series(dtype=float)
    plt.figure(figsize=(6,4))
    angle.dropna().plot(kind="hist", bins=30, color="#3b82f6", alpha=0.8)
    plt.title("Quanji 1.2m Static 原始角度分布")
    plt.xlabel("原始角度 (deg)")
    plt.ylabel("频数")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "quanji_1_2m_static_angle_hist.png")
    plt.close()

    # 角度时间序列
    if TIME_STR_COL in df.columns:
        # 统一解析为 datetime64[ns]，避免对象类型进入数值绘图
        t_series = pd.to_datetime(df[TIME_STR_COL], format="%Y_%m_%d-%H_%M_%S_%f", errors="coerce")
        # 对齐有效样本，避免对象类型/缺失导致绘图转换错误
        mask = (~t_series.isna()) & (~angle.isna())
        t_valid = t_series[mask]
        angle_valid = angle[mask]
        plt.figure(figsize=(8,4))
        plt.plot(t_valid, angle_valid, color="#ef4444", linewidth=1)
        plt.title("Quanji 1.2m Static 原始角度时间序列")
        plt.xlabel("时间")
        plt.ylabel("原始角度 (deg)")
        plt.tight_layout()
        plt.savefig(PLOTS_DIR / "quanji_1_2m_static_angle_ts.png")
        plt.close()

    # 车中心距离直方图
    dist = pd.to_numeric(df[DIST_CENTER_COL], errors="coerce") if DIST_CENTER_COL in df.columns else pd.Series(dtype=float)
    plt.figure(figsize=(6,4))
    dist.dropna().plot(kind="hist", bins=30, color="#10b981", alpha=0.8)
    plt.title("Quanji 1.2m Static 车中心距离分布")
    plt.xlabel("车中心距离 (m)")
    plt.ylabel("频数")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "quanji_1_2m_static_distance_hist.png")
    plt.close()


def main():
    ensure_dirs()
    df = load_csv()

    # 1) 标准差验证
    angle_stats = recompute_angle_stats(df[ANGLE_COL] if ANGLE_COL in df.columns else pd.Series(dtype=float))

    # 2) 全面数据核查
    numeric_summary, dtypes, conversion_notes = summarize_numeric_columns(df)

    # 3) 时间连续性
    time_check = check_time_continuity(df)

    # 4) 计算过程审计
    audit = {
        "angle_col_present": ANGLE_COL in df.columns,
        "used_rows_for_angle": int(pd.to_numeric(df[ANGLE_COL], errors="coerce").dropna().shape[0]) if ANGLE_COL in df.columns else 0,
        "filters_applied": False,
    }

    # 5) 与原始结果对比
    comparison = compare_with_original(angle_stats)

    # 6) 可视化
    make_plots(df)

    # 汇总并保存
    out = {
        "file": str(CSV_PATH),
        "angle_stats": angle_stats,
        "numeric_columns_summary": numeric_summary,
        "dtypes": dtypes,
        "conversion_notes": conversion_notes,
        "time_continuity": time_check,
        "audit": audit,
        "comparison_with_original": comparison,
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("核查完成，结果已保存:", OUT_JSON)
    print("图表保存目录:", PLOTS_DIR)


if __name__ == "__main__":
    main()