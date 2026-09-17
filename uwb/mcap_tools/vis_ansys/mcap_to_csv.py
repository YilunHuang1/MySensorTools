#!/usr/bin/env python3
"""
MCAP UWB 处理工具（简洁版）

功能概述：
- 读取与现有格式一致的 MCAP（ROS2 CDR 序列化）UWB 消息
- 转换为 CSV，包含：时间戳、设备ID、X/Y/Z坐标、信号强度、常用UWB指标
- 支持基础的数据清洗（异常与缺失处理）与大文件的流式写入
- 提供简单CLI与日志输出，遵循PEP8与文档字符串规范

依赖：mcap pandas numpy
"""

from __future__ import annotations

import argparse
import configparser
import csv
import json
import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sensor_tools.uwb import iter_uwb_rows, detect_version_from_path


# ---------------------- 日志配置 ----------------------

logger = logging.getLogger("mcap_to_csv")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ---------------------- 角度与设备ID ----------------------

def normalize_angle(angle_deg: float, version: str) -> float:
    """统一角度到 0..360 顺时针。
    - 007: 原始即 0..360
    - 062: 输入 0..180 与 -180..0，负值加360后再取 0..360
    """
    if version == "062" and angle_deg < 0:
        angle_deg = 360.0 + angle_deg
    return angle_deg % 360.0



def detect_device_id(path: Path) -> str:
    """基于路径推断设备ID（与现有数据集保持一致）。"""
    ver = detect_version_from_path(path)
    return ver


# ---------------------- 清洗配置 ----------------------

@dataclass
class CleanConfig:
    min_distance_m: float = 0.0
    max_distance_m: float = 50.0
    pos_confidence_min: int = 0
    drop_zero_distance: bool = False
    angle_normalize: bool = True
    rssi_clip_min: int = -100
    rssi_clip_max: int = 0


def load_clean_config(cfg_path: Optional[Path]) -> CleanConfig:
    if not cfg_path or not cfg_path.exists():
        return CleanConfig()
    cp = configparser.ConfigParser()
    cp.read(cfg_path)
    section = cp["clean"] if "clean" in cp else {}
    return CleanConfig(
        min_distance_m=float(section.get("min_distance_m", 0.0)),
        max_distance_m=float(section.get("max_distance_m", 50.0)),
        pos_confidence_min=int(section.get("pos_confidence_min", 0)),
        drop_zero_distance=cp.getboolean("clean", "drop_zero_distance", fallback=False),
        angle_normalize=cp.getboolean("clean", "angle_normalize", fallback=True),
        rssi_clip_min=int(section.get("rssi_clip_min", -100)),
        rssi_clip_max=int(section.get("rssi_clip_max", 0)),
    )


def _to_float(x: Any, default: float = float("nan")) -> float:
    """安全将任意值转换为 float；失败则返回默认值。"""
    try:
        return float(x)  # type: ignore[arg-type]
    except Exception:
        return default


def clean_and_augment(rec: Dict[str, object], version: str, cfg: CleanConfig) -> Optional[Dict[str, object]]:
    """基础清洗与增强：
    - 角度统一与坐标计算
    - 距离范围与零值过滤
    - RSSI裁剪与聚合
    - 估计Z坐标：distance * sin(pitch)
    - 填补 distance/angle 缺失：优先使用 filtered
    返回 None 表示该记录被丢弃。
    """
    # 距离/角度填充
    dist = _to_float(rec.get("distance", np.nan))
    dist_f = _to_float(rec.get("distance_filtered", np.nan))
    ang = _to_float(rec.get("angle", np.nan))
    ang_f = _to_float(rec.get("angle_filtered", np.nan))
    pitch = _to_float(rec.get("pitch", 0.0), default=0.0)

    if np.isnan(dist) and not np.isnan(dist_f):
        dist = dist_f
    if np.isnan(ang) and not np.isnan(ang_f):
        ang = ang_f

    if cfg.angle_normalize:
        ang = normalize_angle(ang, version)
        ang_f = normalize_angle(ang_f, version)

    # 距离过滤
    if not np.isfinite(dist):
        return None
    if dist < cfg.min_distance_m:
        return None
    if dist > cfg.max_distance_m:
        return None
    if cfg.drop_zero_distance and abs(dist) < 1e-6:
        return None

    # 坐标（原始/滤波）
    ang_rad = np.radians(ang)
    raw_x = dist * np.cos(ang_rad)
    raw_y = dist * np.sin(ang_rad)

    filt_x = np.nan
    filt_y = np.nan
    if np.isfinite(dist_f) and np.isfinite(ang_f):
        ang_f_rad = np.radians(ang_f)
        filt_x = dist_f * np.cos(ang_f_rad)
        filt_y = dist_f * np.sin(ang_f_rad)

    # Z估计
    z_est = dist * np.sin(np.radians(pitch))

    # RSSI聚合
    rssi_val = rec.get("rssi", [])
    rssi_list: List[int] = []
    if isinstance(rssi_val, list):
        try:
            rssi_list = [int(v) for v in rssi_val]
        except Exception:
            rssi_list = []
    rssi_list = [int(max(cfg.rssi_clip_min, min(cfg.rssi_clip_max, v))) for v in rssi_list]
    rssi_mean = float(np.mean(rssi_list)) if rssi_list else np.nan
    rssi_min = float(np.min(rssi_list)) if rssi_list else np.nan
    rssi_max = float(np.max(rssi_list)) if rssi_list else np.nan

    # 组合输出记录
    out = dict(rec)  # 保留原始字段
    out.update(
        {
            "angle": ang,
            "angle_filtered": ang_f,
            "raw_x_m": raw_x,
            "raw_y_m": raw_y,
            "filtered_x_m": filt_x,
            "filtered_y_m": filt_y,
            "z_m_est": z_est,
            "rssi_mean": rssi_mean,
            "rssi_min": rssi_min,
            "rssi_max": rssi_max,
        }
    )
    return out


# ---------------------- MCAP -> CSV ----------------------

def mcap_to_records(
    mcap_file: Path,
    topic_name: str = "/uwb/data",
    cfg: Optional[CleanConfig] = None,
    ) -> List[Dict[str, Any]]:
    """解析MCAP为记录列表（适合中小文件）。"""
    cfg = cfg or CleanConfig()
    version = detect_version_from_path(mcap_file)
    device_id = detect_device_id(mcap_file)
    records: List[Dict[str, Any]] = []

    for parsed in iter_uwb_rows(mcap_file, topic_name):
        parsed["device_id"] = device_id
        out = clean_and_augment(parsed, version, cfg)
        if out:
            out["rssi"] = json.dumps(out.get("rssi", []), ensure_ascii=False)
            records.append(out)

    logger.info("总共处理了 %d 条消息", len(records))
    return records


def mcap_to_csv_stream(
    mcap_file: Path,
    output_csv: Path,
    topic_name: str = "/uwb/data",
    cfg: Optional[CleanConfig] = None,
    flush_every: int = 2000,
) -> None:
    """流式写出大文件，避免占用过多内存。"""
    cfg = cfg or CleanConfig()
    version = detect_version_from_path(mcap_file)
    device_id = detect_device_id(mcap_file)

    fieldnames = [
        # header & meta
        "stamp_sec",
        "stamp_nsec",
        "frame_id",
        "timestamp_sec",
        "device_id",
        # raw metrics
        "rssi_len",
        "pitch",
        "angle",
        "distance",
        "rssi",
        "angle_filtered",
        "distance_filtered",
        "pos_confidence",
        "has_living_body",
        "has_head_touch",
        # derived
        "raw_x_m",
        "raw_y_m",
        "filtered_x_m",
        "filtered_y_m",
        "z_m_est",
        "rssi_mean",
        "rssi_min",
        "rssi_max",
        # misc
        "message_count",
        "channel_topic",
        "timestamp_ns", "sync_cnt", "source_schema", "source_encoding",
        "log_time_ns", "publish_time_ns",
    ]

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if flush_every <= 0:
        raise ValueError("flush_every must be positive")
    # Write atomically so malformed input cannot leave an apparently valid partial CSV.
    import tempfile
    import os
    fd, temp = tempfile.mkstemp(prefix=".uwb-", dir=output_csv.parent)
    written = 0
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            for parsed in iter_uwb_rows(mcap_file, topic_name):
                parsed["device_id"] = device_id
                out = clean_and_augment(parsed, version, cfg)
                if out:
                    out["rssi"] = json.dumps(out.get("rssi", []), ensure_ascii=False)
                    writer.writerow({key: out.get(key) for key in fieldnames})
                    written += 1
                    if written % flush_every == 0:
                        f_out.flush()
        if not written:
            raise ValueError("no valid ranging messages after filtering")
        Path(temp).replace(output_csv)
    finally:
        Path(temp).unlink(missing_ok=True)

    logger.info("✓ CSV 已保存：%s", output_csv)


# ---------------------- CLI ----------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="MCAP UWB 解析为CSV（含清洗与坐标）")
    parser.add_argument("mcap", help="输入MCAP文件路径")
    parser.add_argument("-o", "--output", help="输出CSV路径，省略则与输入同名")
    parser.add_argument("-t", "--topic", default="/uwb/data", help="解析的topic名称")
    parser.add_argument("-c", "--config", help="配置文件路径config.ini")
    parser.add_argument("--stream", action="store_true", help="启用流式写出，适合大文件")
    parser.add_argument("--flush-every", type=int, default=2000, help="流式模式下批量写出条数")

    args = parser.parse_args()
    mcap_path = Path(args.mcap)
    if not mcap_path.exists():
        logger.error("MCAP 文件不存在：%s", mcap_path)
        return 1

    cfg = load_clean_config(Path(args.config)) if args.config else CleanConfig()

    if args.stream:
        out = Path(args.output) if args.output else mcap_path.with_suffix(".csv")
        mcap_to_csv_stream(
            mcap_path,
            out,
            topic_name=args.topic,
            cfg=cfg,
            flush_every=args.flush_every,
        )
    else:
        records = mcap_to_records(mcap_path, topic_name=args.topic, cfg=cfg)
        if not records:
            logger.error("未解析到有效数据")
            return 1
        df = pd.DataFrame(records)
        out = Path(args.output) if args.output else mcap_path.with_suffix(".csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        logger.info("✓ CSV 已保存：%s", out)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        logger.error("%s", error)
        raise SystemExit(1)