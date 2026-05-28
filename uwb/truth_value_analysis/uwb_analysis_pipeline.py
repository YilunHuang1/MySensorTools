#!/usr/bin/env python3
"""
UWB 原始数据分析管道：
- 目录组织：在当前目录下创建 UWB_Data_Analysis/{raw_data, processed_results}
- 原始数据来源：../UWB原始数据-216个数据/*.mcap
- 将每个 .mcap 复制到 raw_data/【同名文件夹】/ 下（满足“216个数据文件夹”要求）
- 统计规范：仅针对距离与角度，分别统计均值/标准差/最大/最小；不统计高度
- 输出：
  * 每个文件单独统计 CSV（processed_results/per_file_stats/*.csv，含时间戳与版本信息）
  * 整体统计汇总 PDF（processed_results/overall/overall_summary.pdf）与 CSV（processed_results/overall/overall_summary.csv）
  * 所有统计结果均包含完整的时间戳（数据起止、生成时间）与版本信息（如果可检测）
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from typing import Union, List, Dict, Optional
import argparse
import json
from fnmatch import fnmatch

# 允许从父目录导入已有的解析逻辑
CUR_DIR = Path(__file__).resolve().parent
PARENT_DIR = CUR_DIR.parent
sys.path.append(str(PARENT_DIR))

_MCAP_IMPORT_ERROR: Optional[BaseException] = None
try:
    from mcap_to_csv_cdr_correct import mcap_to_dataframe, detect_version_from_path
except Exception as e:
    mcap_to_dataframe = None

    def detect_version_from_path(_path: Path):
        return 'unknown'

    _MCAP_IMPORT_ERROR = e

ANALYSIS_ROOT = CUR_DIR
RAW_DIR = ANALYSIS_ROOT / 'raw_data'
RESULT_DIR = ANALYSIS_ROOT / 'processed_results'
PER_FILE_DIR = RESULT_DIR / 'per_file_stats'
OVERALL_DIR = RESULT_DIR / 'overall'
ORIG_DATA_DIR = PARENT_DIR / 'UWB原始数据-216个数据'
ERRORS = []

# 差值与异常阈值配置
EPS_DISTANCE = 1e-9
EPS_ANGLE = 1e-6
DIST_ABS_DIFF_THRESH_M = 0.05      # 距离绝对差阈值（米）
DIST_REL_ERR_THRESH = 0.10         # 距离相对误差阈值（比例）
ANGLE_ABS_DIFF_THRESH_DEG = 5.0    # 角度绝对差阈值（度）
ANGLE_REL_ERR_THRESH = 0.20        # 角度相对误差阈值（比例）


def ensure_dirs():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    PER_FILE_DIR.mkdir(parents=True, exist_ok=True)
    OVERALL_DIR.mkdir(parents=True, exist_ok=True)

# 动态配置与数据源定位
DEFAULT_CONFIG = {
    'raw_source_locator': {
        'patterns': [
            'UWB原始数据*',
            'UWB原始数据-216*',
            'UWB原始数据-216个数据*',
        ],
        'recursive': True,
        'extra_paths': [],
    },
    'topic_name': '/uwb/data',
    'prefer_filtered': True,
    'distance_unit': 'm',
    'rename_map': {
        'timestamp_sec': ['timestamp_sec', 'time_sec', 'timestamp', 'ts'],
        'angle': ['angle', 'theta_deg'],
        'angle_filtered': ['angle_filtered', 'theta_filtered'],
        'distance': ['distance', 'range_m', 'distance_m'],
        'distance_filtered': ['distance_filtered', 'range_filtered_m'],
    },
    'thresholds': {
        'eps_distance': EPS_DISTANCE,
        'eps_angle': EPS_ANGLE,
        'dist_abs_diff_thresh_m': DIST_ABS_DIFF_THRESH_M,
        'dist_rel_err_thresh': DIST_REL_ERR_THRESH,
        'angle_abs_diff_thresh_deg': ANGLE_ABS_DIFF_THRESH_DEG,
        'angle_rel_err_thresh': ANGLE_REL_ERR_THRESH,
    },
    'error_handling': {
        'on_missing_mcap': 'warn',
        'on_parse_error': 'log',
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(source_dir: Optional[str] = None) -> dict:
    cfg = DEFAULT_CONFIG
    cfg_path = ANALYSIS_ROOT / 'config.json'
    try:
        if cfg_path.exists():
            user_cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
            cfg = _deep_merge(cfg, user_cfg)
    except Exception as e:
        log_error('config_load', str(cfg_path), f'加载配置失败: {e}')
    
    # 如果通过命令行指定了源目录，则覆盖配置
    if source_dir:
        cfg['raw_source_locator']['extra_paths'] = [source_dir]
        # 清空模式匹配，直接使用指定目录
        cfg['raw_source_locator']['patterns'] = []
    
    return cfg


def locate_raw_data_dirs(cfg: dict) -> list:
    locator = cfg.get('raw_source_locator', {})
    patterns = locator.get('patterns', [])
    recursive = bool(locator.get('recursive', True))
    extras = locator.get('extra_paths', [])
    dirs = []

    # 基于模式在父目录搜索
    search_roots = [CUR_DIR, PARENT_DIR]
    for root in search_roots:
        try:
            for p in root.iterdir():
                if not p.is_dir():
                    continue
                name = p.name
                if any(fnmatch(name, pat) for pat in patterns):
                    # 如果包含 .mcap 或其子目录包含 .mcap 则加入
                    has_mcap = False
                    try:
                        if recursive:
                            for _ in p.rglob('*.mcap'):
                                has_mcap = True
                                break
                        else:
                            if list(p.glob('*.mcap')):
                                has_mcap = True
                    except Exception:
                        pass
                    if has_mcap:
                        dirs.append(p)
        except Exception as e:
            log_error('dir_search', str(root), f'搜索失败: {e}')

    # 默认已知目录
    try:
        if ORIG_DATA_DIR.exists():
            if (recursive and list(ORIG_DATA_DIR.rglob('*.mcap'))) or (not recursive and list(ORIG_DATA_DIR.glob('*.mcap'))):
                if ORIG_DATA_DIR not in dirs:
                    dirs.append(ORIG_DATA_DIR)
    except Exception:
        pass

    # 额外路径
    for ep in extras:
        try:
            pp = Path(ep)
            if pp.exists() and pp.is_dir():
                if (recursive and list(pp.rglob('*.mcap'))) or (not recursive and list(pp.glob('*.mcap'))):
                    dirs.append(pp)
        except Exception as e:
            log_error('extra_path', str(ep), f'附加路径处理失败: {e}')

    # 去重
    unique = []
    seen = set()
    for d in dirs:
        if str(d) not in seen:
            unique.append(d)
            seen.add(str(d))
    return unique


def copy_mcap_to_raw(source_dirs, recursive: bool = False):
    """从指定 source_dirs 中收集 .mcap 文件并复制到 raw_data/同名文件夹/ 下。"""
    files = []
    for sd in source_dirs:
        try:
            it = sd.rglob('*.mcap') if recursive else sd.glob('*.mcap')
            for fp in sorted(it):
                files.append(fp)
                dest_folder = RAW_DIR / fp.stem
                dest_folder.mkdir(parents=True, exist_ok=True)
                dest_file = dest_folder / fp.name
                if not dest_file.exists():
                    shutil.copy2(fp, dest_file)
        except Exception as e:
            # 延后定义的 log_error 会在运行时可用；若未定义则静默
            try:
                log_error('scan_copy', str(sd), f'遍历/复制失败: {e}')
            except Exception:
                pass
    return files

# 新增：从文件名解析真值（距离cm、角度deg、可选高度cm），返回统一单位
import re

def parse_truth_from_filename(fp: Path) -> dict:
    """从文件名中解析真值，文件名格式应为：距离_角度_高度_序号.mcap。
    距离单位：cm（输出为 m）；角度单位：deg（归一化到 [0, 360)）；高度单位：cm。
    返回：{'truth_distance_m': float|np.nan, 'truth_angle_deg': float|np.nan, 'truth_height_cm': float|np.nan}
    """
    stem = fp.stem if isinstance(fp, Path) else str(fp).split('.')[0]

    parts = stem.split('_')
    if len(parts) >= 4:
        try:
            dist_cm = float(parts[0])
            ang_deg = float(parts[1])
            height_cm = float(parts[2])
            ang_deg = float(((ang_deg % 360) + 360) % 360)
            return {
                'truth_distance_m': dist_cm / 100.0,
                'truth_angle_deg': ang_deg,
                'truth_height_cm': height_cm,
            }
        except Exception:
            pass

    nums = re.findall(r"-?\d+(?:\.\d+)?", stem)
    if len(nums) < 2:
        return {'truth_distance_m': np.nan, 'truth_angle_deg': np.nan, 'truth_height_cm': np.nan}
    try:
        dist_cm = float(nums[0])
        ang_deg = float(nums[1])
        ang_deg = float(((ang_deg % 360) + 360) % 360)

        height_cm = np.nan
        if len(nums) >= 3:
            height_cm = float(nums[2])

        return {
            'truth_distance_m': dist_cm / 100.0,
            'truth_angle_deg': ang_deg,
            'truth_height_cm': height_cm,
        }
    except Exception:
        return {'truth_distance_m': np.nan, 'truth_angle_deg': np.nan, 'truth_height_cm': np.nan}


def log_error(error_type: str, subject: str, message: str):
    """错误记录：写入 processed_results/overall/error_log.txt 并缓存到内存列表。"""
    try:
        OVERALL_DIR.mkdir(parents=True, exist_ok=True)
        log_file = OVERALL_DIR / 'error_log.txt'
        with log_file.open('a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {error_type} | {subject} | {message}\n")
    except Exception:
        pass
    # 内存缓存
    try:
        ERRORS.append({'error_type': error_type, 'subject': subject, 'message': message, 'time': datetime.now().isoformat(timespec='seconds')})
    except Exception:
        pass


def _resolve_first_column(df: pd.DataFrame, candidates: list) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    return ''


def timestamp_series(df: pd.DataFrame, cfg: dict) -> pd.Series:
    rm = cfg.get('rename_map', {})
    ts_candidates = rm.get('timestamp_sec', []) + ['timestamp_sec', 'timestamp', 'time_sec', 'ts']
    col = _resolve_first_column(df, ts_candidates)
    if col:
        return pd.to_numeric(df[col], errors='coerce')
    return pd.Series(np.nan, index=df.index)


def angle_series(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """获取角度序列：优先 filtered，再 raw；并确保 float。"""
    rm = cfg.get('rename_map', {})
    filtered_col = _resolve_first_column(df, rm.get('angle_filtered', []) + ['angle_filtered'])
    raw_col = _resolve_first_column(df, rm.get('angle', []) + ['angle'])
    prefer = bool(cfg.get('prefer_filtered', True))

    filtered = pd.to_numeric(df[filtered_col], errors='coerce') if filtered_col else None
    raw = pd.to_numeric(df[raw_col], errors='coerce') if raw_col else None

    if prefer:
        if filtered is not None and raw is not None:
            s = filtered.fillna(raw)
        elif filtered is not None:
            s = filtered
        elif raw is not None:
            s = raw
        else:
            s = pd.Series(np.nan, index=df.index)
    else:
        if raw is not None:
            s = raw
        elif filtered is not None:
            s = filtered
        else:
            s = pd.Series(np.nan, index=df.index)

    s = s.astype(float)
    return s


def distance_series_m(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """获取距离（米）序列：优先 filtered，再 raw；并进行单位转换。"""
    rm = cfg.get('rename_map', {})
    filtered_col = _resolve_first_column(df, rm.get('distance_filtered', []) + ['distance_filtered'])
    raw_col = _resolve_first_column(df, rm.get('distance', []) + ['distance'])
    prefer = bool(cfg.get('prefer_filtered', True))

    filtered = pd.to_numeric(df[filtered_col], errors='coerce') if filtered_col else None
    raw = pd.to_numeric(df[raw_col], errors='coerce') if raw_col else None

    if prefer:
        if filtered is not None and raw is not None:
            s = filtered.fillna(raw)
        elif filtered is not None:
            s = filtered
        elif raw is not None:
            s = raw
        else:
            s = pd.Series(np.nan, index=df.index)
    else:
        if raw is not None:
            s = raw
        elif filtered is not None:
            s = filtered
        else:
            s = pd.Series(np.nan, index=df.index)

    unit = str(cfg.get('distance_unit', 'm')).lower()
    if unit == 'cm':
        s = s.astype(float) / 100.0
    else:
        s = s.astype(float)
    return s


def detect_version_by_angles(df: pd.DataFrame, fallback: str = '007') -> str:
    """若路径无法判断版本，尝试用角度分布启发式判断：存在负角度则倾向 062。"""
    if 'angle' in df.columns:
        ang = df['angle'].astype(float)
        if (ang.min() < 0.0) and (ang.max() <= 180.0 + 1e-6):
            return '062'
    return fallback


def angle_signed_diff_vec(measured_deg: Union[pd.Series, np.ndarray], truth_deg: float) -> np.ndarray:
    """环形最小有符号差值，范围 [-180, 180)。"""
    arr = measured_deg.to_numpy(dtype=float) if isinstance(measured_deg, pd.Series) else np.asarray(measured_deg, dtype=float)
    if np.isnan(truth_deg):
        return np.full_like(arr, np.nan, dtype=float)
    return ((arr - truth_deg + 180.0) % 360.0) - 180.0


def generate_angle_error_visualizations(
    stem: str,
    measured_angle_deg: pd.Series,
    angle_abs_diff_deg: pd.Series,
    angle_signed_diff_deg: pd.Series,
    truth_angle_deg: float,
    out_dir: Path,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    meas = measured_angle_deg.dropna().astype(float)
    abs_err = angle_abs_diff_deg.loc[meas.index].dropna().astype(float)
    signed_err = angle_signed_diff_deg.loc[meas.index].dropna().astype(float)

    common_idx = meas.index.intersection(abs_err.index).intersection(signed_err.index)
    meas = meas.loc[common_idx]
    abs_err = abs_err.loc[common_idx]
    signed_err = signed_err.loc[common_idx]

    if meas.empty or abs_err.empty:
        return {}

    theta = np.deg2rad(((meas.to_numpy(dtype=float) % 360.0) + 360.0) % 360.0)
    r = abs_err.to_numpy(dtype=float)
    c = signed_err.to_numpy(dtype=float)

    r_max = float(np.nanpercentile(r, 99)) if np.isfinite(r).any() else float(np.nanmax(r))
    r_max = max(r_max, 1e-6)

    polar_path = out_dir / f"{stem}_angle_error_polar.png"
    fig = plt.figure(figsize=(7.5, 7.0))
    ax = fig.add_subplot(111, projection='polar')
    sc = ax.scatter(theta, r, c=c, s=8, alpha=0.75, cmap='coolwarm')
    ax.set_title(f"{stem} Angle Error (polar) | truth={truth_angle_deg:.1f}°" if not np.isnan(truth_angle_deg) else f"{stem} Angle Error (polar)")
    ax.set_rmax(r_max)
    ax.set_rlabel_position(90)
    cb = fig.colorbar(sc, ax=ax, pad=0.12)
    cb.set_label('signed error (deg)')
    fig.tight_layout()
    fig.savefig(polar_path, dpi=180)
    plt.close(fig)

    scatter_path = out_dir / f"{stem}_angle_error_scatter.png"
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    ax.scatter(meas.to_numpy(dtype=float), c, s=8, alpha=0.75, c=np.abs(c), cmap='viridis')
    ax.axhline(0.0, color='black', linewidth=1.0)
    ax.set_title(f"{stem} Signed Angle Error vs Measured Angle")
    ax.set_xlabel('measured angle (deg)')
    ax.set_ylabel('signed error (deg)')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(scatter_path, dpi=180)
    plt.close(fig)

    return {
        'angle_error_polar_png': str(polar_path),
        'angle_error_scatter_png': str(scatter_path),
    }


def series_stats(series: pd.Series):
    s = series.dropna()
    if s.empty:
        return {'mean': np.nan, 'std': np.nan, 'max': np.nan, 'min': np.nan, 'count': 0}
    return {
        'mean': float(s.mean()),
        'std': float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        'max': float(s.max()),
        'min': float(s.min()),
        'count': int(s.count()),
    }


def process_one_file(mcap_path: Path, cfg: dict) -> dict:
    try:
        df = mcap_to_dataframe(mcap_path, topic_name=str(cfg.get('topic_name', '/uwb/data')))
    except Exception as e:
        log_error('parse_mcap', str(mcap_path), f'解析失败: {e}')
        df = pd.DataFrame()

    if df.empty:
        return {
            'file_name': mcap_path.name,
            'version': detect_version_from_path(mcap_path),
            'start_timestamp_sec': np.nan,
            'end_timestamp_sec': np.nan,
            'data_count': 0,
            'distance_mean_m': np.nan,
            'distance_std_m': np.nan,
            'distance_max_m': np.nan,
            'distance_min_m': np.nan,
            'angle_mean_deg': np.nan,
            'angle_std_deg': np.nan,
            'angle_max_deg': np.nan,
            'angle_min_deg': np.nan,
            # 差值与误差统计（空）
            'truth_distance_m': np.nan,
            'truth_angle_deg': np.nan,
            'distance_abs_diff_m_mean': np.nan,
            'distance_abs_diff_m_std': np.nan,
            'distance_abs_diff_m_min': np.nan,
            'distance_abs_diff_m_max': np.nan,
            'distance_abs_diff_m_median': np.nan,
            'angle_abs_diff_deg_mean': np.nan,
            'angle_abs_diff_deg_std': np.nan,
            'angle_abs_diff_deg_min': np.nan,
            'angle_abs_diff_deg_max': np.nan,
            'angle_abs_diff_deg_median': np.nan,
            'distance_rel_error_pct_mean': np.nan,
            'distance_rel_error_pct_std': np.nan,
            'distance_rel_error_pct_min': np.nan,
            'distance_rel_error_pct_max': np.nan,
            'distance_rel_error_pct_median': np.nan,
            'angle_rel_error_pct_mean': np.nan,
            'angle_rel_error_pct_std': np.nan,
            'angle_rel_error_pct_min': np.nan,
            'angle_rel_error_pct_max': np.nan,
            'angle_rel_error_pct_median': np.nan,
            'anomaly_count': 0,
            'anomaly_rate': 0.0,
            'anomaly_thresholds': f"dist_abs>{cfg['thresholds']['dist_abs_diff_thresh_m']}m | dist_rel>{cfg['thresholds']['dist_rel_err_thresh']} | angle_abs>{cfg['thresholds']['angle_abs_diff_thresh_deg']}deg | angle_rel>{cfg['thresholds']['angle_rel_err_thresh']}",
            'generated_at_iso': datetime.now().isoformat(timespec='seconds'),
        }

    # 版本信息：优先路径判断，若不含关键字则用角度分布启发式
    version_guess = detect_version_from_path(mcap_path)
    version = detect_version_by_angles(df, fallback=version_guess)

    # 时间戳
    ts_series = timestamp_series(df, cfg)
    start_ts = float(ts_series.min()) if not ts_series.isna().all() else np.nan
    end_ts = float(ts_series.max()) if not ts_series.isna().all() else np.nan

    # 距离与角度序列
    dist_m = distance_series_m(df, cfg).astype(float)
    ang_deg = angle_series(df, cfg).astype(float)

    # 真值解析
    truth = parse_truth_from_filename(mcap_path)
    truth_distance_m = float(truth['truth_distance_m']) if not np.isnan(truth['truth_distance_m']) else np.nan
    truth_angle_deg = float(truth['truth_angle_deg']) if not np.isnan(truth['truth_angle_deg']) else np.nan

    eps_distance = float(cfg['thresholds'].get('eps_distance', EPS_DISTANCE))
    eps_angle = float(cfg['thresholds'].get('eps_angle', EPS_ANGLE))

    # 差值与相对误差
    if np.isnan(truth_distance_m):
        dist_abs_diff_m = pd.Series(np.nan, index=dist_m.index)
        dist_rel_err_pct = pd.Series(np.nan, index=dist_m.index)
    else:
        dist_abs_diff_m = (dist_m - truth_distance_m).abs()
        dist_rel_err_pct = dist_abs_diff_m / max(eps_distance, abs(truth_distance_m))

    if np.isnan(truth_angle_deg):
        ang_abs_diff_deg = pd.Series(np.nan, index=ang_deg.index)
        ang_rel_err_pct = pd.Series(np.nan, index=ang_deg.index)
    else:
        ang_abs_diff_deg = pd.Series(np.abs(angle_signed_diff_vec(ang_deg, truth_angle_deg)), index=ang_deg.index)
        ang_rel_err_pct = ang_abs_diff_deg / max(eps_angle, abs(truth_angle_deg))

    # 异常检测
    thr = cfg['thresholds']
    anomaly_mask = (
        (dist_abs_diff_m > float(thr['dist_abs_diff_thresh_m'])) |
        (dist_rel_err_pct > float(thr['dist_rel_err_thresh'])) |
        (ang_abs_diff_deg > float(thr['angle_abs_diff_thresh_deg'])) |
        (ang_rel_err_pct > float(thr['angle_rel_err_thresh']))
    ).fillna(False)
    anomaly_count = int(anomaly_mask.sum())
    anomaly_rate = float(anomaly_count / len(df)) if len(df) > 0 else 0.0

    # 基础统计
    dist_stat = series_stats(dist_m)
    ang_stat = series_stats(ang_deg)

    # 差值统计分布
    def stats_with_median(s: pd.Series):
        s = s.dropna().astype(float)
        if s.empty:
            return {'mean': np.nan, 'std': np.nan, 'max': np.nan, 'min': np.nan, 'median': np.nan}
        return {
            'mean': float(s.mean()),
            'std': float(s.std(ddof=1)) if len(s) > 1 else 0.0,
            'max': float(s.max()),
            'min': float(s.min()),
            'median': float(s.median()),
        }

    dist_diff_stat = stats_with_median(dist_abs_diff_m)
    ang_diff_stat = stats_with_median(ang_abs_diff_deg)
    dist_rel_stat = stats_with_median(dist_rel_err_pct)
    ang_rel_stat = stats_with_median(ang_rel_err_pct)

    result = {
        'file_name': mcap_path.name,
        'version': version,
        'start_timestamp_sec': start_ts,
        'end_timestamp_sec': end_ts,
        'data_count': int(len(df)),
        'distance_mean_m': dist_stat['mean'],
        'distance_std_m': dist_stat['std'],
        'distance_max_m': dist_stat['max'],
        'distance_min_m': dist_stat['min'],
        'angle_mean_deg': ang_stat['mean'],
        'angle_std_deg': ang_stat['std'],
        'angle_max_deg': ang_stat['max'],
        'angle_min_deg': ang_stat['min'],
        'truth_distance_m': truth_distance_m,
        'truth_angle_deg': truth_angle_deg,
        'distance_abs_diff_m_mean': dist_diff_stat['mean'],
        'distance_abs_diff_m_std': dist_diff_stat['std'],
        'distance_abs_diff_m_min': dist_diff_stat['min'],
        'distance_abs_diff_m_max': dist_diff_stat['max'],
        'distance_abs_diff_m_median': dist_diff_stat['median'],
        'angle_abs_diff_deg_mean': ang_diff_stat['mean'],
        'angle_abs_diff_deg_std': ang_diff_stat['std'],
        'angle_abs_diff_deg_min': ang_diff_stat['min'],
        'angle_abs_diff_deg_max': ang_diff_stat['max'],
        'angle_abs_diff_deg_median': ang_diff_stat['median'],
        'distance_rel_error_pct_mean': dist_rel_stat['mean'],
        'distance_rel_error_pct_std': dist_rel_stat['std'],
        'distance_rel_error_pct_min': dist_rel_stat['min'],
        'distance_rel_error_pct_max': dist_rel_stat['max'],
        'distance_rel_error_pct_median': dist_rel_stat['median'],
        'angle_rel_error_pct_mean': ang_rel_stat['mean'],
        'angle_rel_error_pct_std': ang_rel_stat['std'],
        'angle_rel_error_pct_min': ang_rel_stat['min'],
        'angle_rel_error_pct_max': ang_rel_stat['max'],
        'angle_rel_error_pct_median': ang_rel_stat['median'],
        'anomaly_count': anomaly_count,
        'anomaly_rate': anomaly_rate,
        'anomaly_thresholds': f"dist_abs>{thr['dist_abs_diff_thresh_m']}m | dist_rel>{thr['dist_rel_err_thresh']} | angle_abs>{thr['angle_abs_diff_thresh_deg']}deg | angle_rel>{thr['angle_rel_err_thresh']}",
        'generated_at_iso': datetime.now().isoformat(timespec='seconds'),
    }
    return result


def save_per_file_stats(stats_rows: list):
    for row in stats_rows:
        stem = Path(row['file_name']).stem
        out_csv = PER_FILE_DIR / f"{stem}.csv"
        pd.DataFrame([row]).to_csv(out_csv, index=False)


def write_diff_stats_doc(cfg: dict):
    """生成统计指标说明文档"""
    doc_path = OVERALL_DIR / 'diff_stats_documentation.md'
    thr = cfg['thresholds']
    lines = [
        '# UWB 差值与误差统计指标说明',
        '',
        '本文档说明在 UWB 数据分析中新增的与真值相关的差值与误差统计方法，以及异常检测规则。',
        '',
        '## 真值解析',
        '- 从文件名解析顺序：`距离_cm`、`角度_deg`、`(高度_cm)`、`0`。仅使用距离与角度作为真值。',
        '- 距离真值统一到 `米`，角度真值统一到 `[0, 360)`。',
        '',
        '## 指标定义',
        '- 距离绝对差 (`distance_abs_diff_m`)：`|measured_distance_m - truth_distance_m|`。',
        '- 角度绝对差 (`angle_abs_diff_deg`)：环形最小绝对差值，`abs(((measured - truth + 180) % 360) - 180)`。',
        f"- 距离相对误差 (`distance_rel_error_pct`)：`distance_abs_diff_m / max(eps, |truth_distance_m|)`，其中 `eps={thr.get('eps_distance', EPS_DISTANCE)}`。",
        f"- 角度相对误差 (`angle_rel_error_pct`)：`angle_abs_diff_deg / max(eps, |truth_angle_deg|)`，其中 `eps={thr.get('eps_angle', EPS_ANGLE)}`。",
        '',
        '## 统计量',
        '- 对每个数据文件与总体，分别统计：`mean`、`std`、`min`、`max`、`median`。',
        '- 标准差使用 `ddof=1`，样本量为 1 时标准差记为 0。',
        '',
        '## 异常检测规则',
        f"- 设定阈值：距离绝对差 > {thr['dist_abs_diff_thresh_m']} m；距离相对误差 > {thr['dist_rel_err_thresh']}；角度绝对差 > {thr['angle_abs_diff_thresh_deg']} deg；角度相对误差 > {thr['angle_rel_err_thresh']}。",
        '- 任一条件满足即标记为异常，输出每文件的异常条数与异常率。',
        '',
        '## 适用性与稳健性',
        '- 连续与离散数值均按数值型处理。角度采用环形差值以避免 0/360 边界问题。',
        '- 当真值接近 0（尤其角度），相对误差使用 `eps` 防止除零，这会使接近 0 的真值对应的相对误差较大；可根据场景调整 eps 与阈值。',
        '',
        '## 输出',
        '- 每文件 CSV：新增真值、绝对差与相对误差的统计列以及异常统计。',
        '- 总体 CSV：`overall_summary.csv`（原始分布）与 `overall_diff_summary.csv`（差值与误差分布）。',
        '- 总体 PDF：在 `overall_summary.pdf` 中新增差值与相对误差的直方图与箱线图，以及摘要页。',
        '',
        '## 版本与时间戳',
        '- 每个结果均包含推断的版本信息与生成时间戳（ISO格式）。',
    ]
    doc_path.write_text('\n'.join(lines), encoding='utf-8')


def generate_individual_accuracy_report(mcap_path: Path, df: pd.DataFrame, cfg: dict) -> dict:
    """为单个mcap文件生成详细的距离准度分析报告"""
    
    # 创建单独的准度报告目录
    accuracy_dir = RESULT_DIR / 'accuracy_reports'
    accuracy_dir.mkdir(exist_ok=True)
    
    # 获取文件基本信息
    stem = mcap_path.stem
    truth = parse_truth_from_filename(mcap_path)
    truth_distance_m = float(truth['truth_distance_m']) if not np.isnan(truth['truth_distance_m']) else np.nan
    truth_angle_deg = float(truth['truth_angle_deg']) if not np.isnan(truth['truth_angle_deg']) else np.nan
    
    # 获取距离和角度序列
    dist_m = distance_series_m(df, cfg).astype(float)
    ang_deg = angle_series(df, cfg).astype(float)
    ts_series = timestamp_series(df, cfg)
    
    # 计算准度指标
    eps_distance = float(cfg['thresholds'].get('eps_distance', EPS_DISTANCE))
    eps_angle = float(cfg['thresholds'].get('eps_angle', EPS_ANGLE))
    
    if np.isnan(truth_distance_m):
        dist_abs_diff_m = pd.Series(np.nan, index=dist_m.index)
        dist_rel_err_pct = pd.Series(np.nan, index=dist_m.index)
    else:
        dist_abs_diff_m = (dist_m - truth_distance_m).abs()
        dist_rel_err_pct = dist_abs_diff_m / max(eps_distance, abs(truth_distance_m))
    
    if np.isnan(truth_angle_deg):
        ang_abs_diff_deg = pd.Series(np.nan, index=ang_deg.index)
        ang_rel_err_pct = pd.Series(np.nan, index=ang_deg.index)
    else:
        ang_abs_diff_deg = pd.Series(np.abs(angle_signed_diff_vec(ang_deg, truth_angle_deg)), index=ang_deg.index)
        ang_rel_err_pct = ang_abs_diff_deg / max(eps_angle, abs(truth_angle_deg))
    
    # 异常检测
    thr = cfg['thresholds']
    anomaly_mask = (
        (dist_abs_diff_m > float(thr['dist_abs_diff_thresh_m'])) |
        (dist_rel_err_pct > float(thr['dist_rel_err_thresh'])) |
        (ang_abs_diff_deg > float(thr['angle_abs_diff_thresh_deg'])) |
        (ang_rel_err_pct > float(thr['angle_rel_err_thresh']))
    ).fillna(False)
    
    # 创建详细的数据分析DataFrame
    analysis_df = pd.DataFrame({
        'timestamp_sec': ts_series,
        'measured_distance_m': dist_m,
        'measured_angle_deg': ang_deg,
        'truth_distance_m': truth_distance_m,
        'truth_angle_deg': truth_angle_deg,
        'distance_abs_diff_m': dist_abs_diff_m,
        'distance_rel_error_pct': dist_rel_err_pct,
        'angle_abs_diff_deg': ang_abs_diff_deg,
        'angle_rel_error_pct': ang_rel_err_pct,
        'is_anomaly': anomaly_mask
    })
    
    # 保存详细数据到CSV
    detail_csv_path = accuracy_dir / f"{stem}_accuracy_detail.csv"
    analysis_df.to_csv(detail_csv_path, index=False)
    
    # 生成统计摘要
    def stats_with_median(s: pd.Series):
        s = s.dropna().astype(float)
        if s.empty:
            return {'mean': np.nan, 'std': np.nan, 'max': np.nan, 'min': np.nan, 'median': np.nan}
        return {
            'mean': float(s.mean()),
            'std': float(s.std(ddof=1)) if len(s) > 1 else 0.0,
            'max': float(s.max()),
            'min': float(s.min()),
            'median': float(s.median()),
        }
    
    dist_diff_stats = stats_with_median(dist_abs_diff_m)
    ang_diff_stats = stats_with_median(ang_abs_diff_deg)
    dist_rel_stats = stats_with_median(dist_rel_err_pct)
    ang_rel_stats = stats_with_median(ang_rel_err_pct)
    
    # 计算准度等级
    def get_accuracy_grade(mean_error, max_error, threshold):
        if np.isnan(mean_error) or np.isnan(max_error):
            return "N/A"
        elif mean_error <= threshold * 0.5 and max_error <= threshold:
            return "优秀"
        elif mean_error <= threshold and max_error <= threshold * 2:
            return "良好"
        elif mean_error <= threshold * 2:
            return "一般"
        else:
            return "较差"
    
    distance_grade = get_accuracy_grade(
        dist_diff_stats['mean'], 
        dist_diff_stats['max'], 
        float(thr['dist_abs_diff_thresh_m'])
    )
    
    angle_grade = get_accuracy_grade(
        ang_diff_stats['mean'], 
        ang_diff_stats['max'], 
        float(thr['angle_abs_diff_thresh_deg'])
    )
    
    # 生成角度误差可视化
    angle_signed_err_deg = pd.Series(angle_signed_diff_vec(ang_deg, truth_angle_deg), index=ang_deg.index)
    plots_dir = accuracy_dir / 'plots'
    angle_plot_paths = {}
    if not np.isnan(truth_angle_deg):
        angle_plot_paths = generate_angle_error_visualizations(
            stem=stem,
            measured_angle_deg=ang_deg,
            angle_abs_diff_deg=ang_abs_diff_deg,
            angle_signed_diff_deg=angle_signed_err_deg,
            truth_angle_deg=truth_angle_deg,
            out_dir=plots_dir,
        )

    # 生成Markdown报告
    report_md_path = accuracy_dir / f"{stem}_accuracy_report.md"

    report_lines = [
        f"# {stem} 距离与角度准度分析报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**数据文件**: {mcap_path.name}",
        f"**数据点数**: {len(df)}",
        "",
        "## 真值信息",
        f"- **真实距离**: {truth_distance_m:.3f} m" if not np.isnan(truth_distance_m) else "- **真实距离**: 未知",
        f"- **真实角度**: {truth_angle_deg:.1f}°" if not np.isnan(truth_angle_deg) else "- **真实角度**: 未知",
        "",
        "## 距离准度分析",
        f"- **准度等级**: {distance_grade}",
        f"- **平均绝对误差**: {dist_diff_stats['mean']:.4f} m",
        f"- **标准差**: {dist_diff_stats['std']:.4f} m",
        f"- **最小误差**: {dist_diff_stats['min']:.4f} m",
        f"- **最大误差**: {dist_diff_stats['max']:.4f} m",
        f"- **中位数误差**: {dist_diff_stats['median']:.4f} m",
        f"- **平均相对误差**: {dist_rel_stats['mean']:.2%}",
        "",
        "## 角度准度分析",
        f"- **准度等级**: {angle_grade}",
        f"- **平均绝对误差**: {ang_diff_stats['mean']:.2f}°",
        f"- **标准差**: {ang_diff_stats['std']:.2f}°",
        f"- **最小误差**: {ang_diff_stats['min']:.2f}°",
        f"- **最大误差**: {ang_diff_stats['max']:.2f}°",
        f"- **中位数误差**: {ang_diff_stats['median']:.2f}°",
        f"- **平均相对误差**: {ang_rel_stats['mean']:.2%}",
        "",
        "## 异常检测结果",
        f"- **异常点数量**: {int(anomaly_mask.sum())}",
        f"- **异常率**: {float(anomaly_mask.sum() / len(df)):.2%}",
        f"- **检测阈值**: 距离>{thr['dist_abs_diff_thresh_m']}m, 角度>{thr['angle_abs_diff_thresh_deg']}°",
        "",
        "## 数据质量评估",
    ]
    
    # 添加数据质量评估
    if not np.isnan(truth_distance_m):
        if dist_diff_stats['mean'] <= 0.02:
            quality_dist = "距离测量精度很高"
        elif dist_diff_stats['mean'] <= 0.05:
            quality_dist = "距离测量精度良好"
        elif dist_diff_stats['mean'] <= 0.1:
            quality_dist = "距离测量精度一般"
        else:
            quality_dist = "距离测量精度较差"
        report_lines.append(f"- **距离测量质量**: {quality_dist}")
    
    if not np.isnan(truth_angle_deg):
        if ang_diff_stats['mean'] <= 2:
            quality_ang = "角度测量精度很高"
        elif ang_diff_stats['mean'] <= 5:
            quality_ang = "角度测量精度良好"
        elif ang_diff_stats['mean'] <= 10:
            quality_ang = "角度测量精度一般"
        else:
            quality_ang = "角度测量精度较差"
        report_lines.append(f"- **角度测量质量**: {quality_ang}")
    
    if angle_plot_paths:
        report_lines.extend([
            "",
            "## 角度误差可视化",
            f"- 极坐标误差分布图: `{Path(angle_plot_paths['angle_error_polar_png']).name}`",
            f"- 散点图(测量角度-有符号误差): `{Path(angle_plot_paths['angle_error_scatter_png']).name}`",
        ])

    report_lines.extend([
        "",
        "## 详细数据",
        f"详细的逐点分析数据已保存到: `{detail_csv_path.name}`",
        "",
        "---",
        "*本报告由UWB数据分析管道自动生成*"
    ])

    report_md_path.write_text('\n'.join(report_lines), encoding='utf-8')

    # 返回报告摘要信息
    out = {
        'file_name': mcap_path.name,
        'report_path': str(report_md_path),
        'detail_csv_path': str(detail_csv_path),
        'distance_grade': distance_grade,
        'angle_grade': angle_grade,
        'distance_mean_error_m': dist_diff_stats['mean'],
        'angle_mean_error_deg': ang_diff_stats['mean'],
        'truth_distance_m': truth_distance_m,
        'truth_angle_deg': truth_angle_deg,
        'truth_height_cm': float(truth.get('truth_height_cm', np.nan)) if truth is not None else np.nan,
        'anomaly_count': int(anomaly_mask.sum()),
        'anomaly_rate': float(anomaly_mask.sum() / len(df)),
        'data_count': len(df),
        'generated_at': datetime.now().isoformat(),
    }
    out.update(angle_plot_paths)
    return out


def generate_overall_accuracy_summary(accuracy_reports: list, cfg: dict):
    """生成总体准度分析摘要报告"""
    
    accuracy_dir = RESULT_DIR / 'accuracy_reports'
    accuracy_dir.mkdir(exist_ok=True)
    
    # 创建总体摘要CSV
    summary_df = pd.DataFrame(accuracy_reports)
    summary_csv_path = accuracy_dir / 'overall_accuracy_summary.csv'
    summary_df.to_csv(summary_csv_path, index=False)
    
    # 计算总体统计
    total_files = len(accuracy_reports)

    overall_angle_polar_path = None
    try:
        if 'truth_angle_deg' in summary_df.columns and 'angle_mean_error_deg' in summary_df.columns:
            plot_df = summary_df[['truth_angle_deg', 'angle_mean_error_deg']].copy()
            plot_df = plot_df.dropna()
            if not plot_df.empty:
                theta = np.deg2rad(((plot_df['truth_angle_deg'].astype(float) % 360.0) + 360.0) % 360.0)
                r = plot_df['angle_mean_error_deg'].astype(float)
                overall_angle_polar_path = accuracy_dir / 'overall_angle_error_polar.png'
                fig = plt.figure(figsize=(7.6, 7.0))
                ax = fig.add_subplot(111, projection='polar')
                ax.scatter(theta, r, s=22, alpha=0.85, color='tomato')
                ax.set_title('Overall Angle Mean Error vs Truth Angle (polar)')
                ax.set_rlabel_position(90)
                ax.grid(True, alpha=0.3)
                fig.tight_layout()
                fig.savefig(overall_angle_polar_path, dpi=180)
                plt.close(fig)
    except Exception:
        overall_angle_polar_path = None
    
    # 距离准度统计
    distance_errors = [r['distance_mean_error_m'] for r in accuracy_reports if not np.isnan(r['distance_mean_error_m'])]
    distance_grades = [r['distance_grade'] for r in accuracy_reports if r['distance_grade'] != 'N/A']
    
    # 角度准度统计
    angle_errors = [r['angle_mean_error_deg'] for r in accuracy_reports if not np.isnan(r['angle_mean_error_deg'])]
    angle_grades = [r['angle_grade'] for r in accuracy_reports if r['angle_grade'] != 'N/A']
    
    # 异常统计
    total_anomalies = sum(r['anomaly_count'] for r in accuracy_reports)
    total_data_points = sum(r['data_count'] for r in accuracy_reports)
    overall_anomaly_rate = total_anomalies / total_data_points if total_data_points > 0 else 0
    
    # 等级分布统计
    def count_grades(grades):
        grade_counts = {'优秀': 0, '良好': 0, '一般': 0, '较差': 0}
        for grade in grades:
            if grade in grade_counts:
                grade_counts[grade] += 1
        return grade_counts
    
    distance_grade_counts = count_grades(distance_grades)
    angle_grade_counts = count_grades(angle_grades)
    
    # 生成Markdown总体摘要报告
    summary_md_path = accuracy_dir / 'overall_accuracy_summary.md'
    
    report_lines = [
        "# UWB 总体准度分析摘要报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**分析文件总数**: {total_files}",
        f"**总数据点数**: {total_data_points:,}",
        "",
        "## 距离准度总体表现",
        f"- **有效分析文件数**: {len(distance_errors)}",
    ]
    
    if distance_errors:
        report_lines.extend([
            f"- **平均误差**: {np.mean(distance_errors):.4f} m",
            f"- **误差标准差**: {np.std(distance_errors, ddof=1):.4f} m",
            f"- **最小误差**: {np.min(distance_errors):.4f} m",
            f"- **最大误差**: {np.max(distance_errors):.4f} m",
            f"- **中位数误差**: {np.median(distance_errors):.4f} m",
            "",
            "### 距离准度等级分布",
            f"- **优秀**: {distance_grade_counts['优秀']} 个文件 ({distance_grade_counts['优秀']/len(distance_grades)*100:.1f}%)",
            f"- **良好**: {distance_grade_counts['良好']} 个文件 ({distance_grade_counts['良好']/len(distance_grades)*100:.1f}%)",
            f"- **一般**: {distance_grade_counts['一般']} 个文件 ({distance_grade_counts['一般']/len(distance_grades)*100:.1f}%)",
            f"- **较差**: {distance_grade_counts['较差']} 个文件 ({distance_grade_counts['较差']/len(distance_grades)*100:.1f}%)",
        ])
    else:
        report_lines.append("- **无有效距离数据**")
    
    report_lines.extend([
        "",
        "## 角度准度总体表现",
        f"- **有效分析文件数**: {len(angle_errors)}",
    ])

    if overall_angle_polar_path is not None:
        report_lines.append(f"- **极坐标汇总图**: `{Path(overall_angle_polar_path).name}`")
    
    if angle_errors:
        report_lines.extend([
            f"- **平均误差**: {np.mean(angle_errors):.2f}°",
            f"- **误差标准差**: {np.std(angle_errors, ddof=1):.2f}°",
            f"- **最小误差**: {np.min(angle_errors):.2f}°",
            f"- **最大误差**: {np.max(angle_errors):.2f}°",
            f"- **中位数误差**: {np.median(angle_errors):.2f}°",
            "",
            "### 角度准度等级分布",
            f"- **优秀**: {angle_grade_counts['优秀']} 个文件 ({angle_grade_counts['优秀']/len(angle_grades)*100:.1f}%)",
            f"- **良好**: {angle_grade_counts['良好']} 个文件 ({angle_grade_counts['良好']/len(angle_grades)*100:.1f}%)",
            f"- **一般**: {angle_grade_counts['一般']} 个文件 ({angle_grade_counts['一般']/len(angle_grades)*100:.1f}%)",
            f"- **较差**: {angle_grade_counts['较差']} 个文件 ({angle_grade_counts['较差']/len(angle_grades)*100:.1f}%)",
        ])
    else:
        report_lines.append("- **无有效角度数据**")
    
    report_lines.extend([
        "",
        "## 异常检测总体结果",
        f"- **总异常点数**: {total_anomalies:,}",
        f"- **总体异常率**: {overall_anomaly_rate:.2%}",
        f"- **检测阈值**: 距离>{cfg['thresholds']['dist_abs_diff_thresh_m']}m, 角度>{cfg['thresholds']['angle_abs_diff_thresh_deg']}°",
        "",
        "## 数据质量总体评估",
    ])
    
    # 总体质量评估
    if distance_errors:
        avg_dist_error = np.mean(distance_errors)
        if avg_dist_error <= 0.02:
            overall_dist_quality = "优秀"
        elif avg_dist_error <= 0.05:
            overall_dist_quality = "良好"
        elif avg_dist_error <= 0.1:
            overall_dist_quality = "一般"
        else:
            overall_dist_quality = "较差"
        report_lines.append(f"- **距离测量总体质量**: {overall_dist_quality}")
    
    if angle_errors:
        avg_angle_error = np.mean(angle_errors)
        if avg_angle_error <= 2:
            overall_angle_quality = "优秀"
        elif avg_angle_error <= 5:
            overall_angle_quality = "良好"
        elif avg_angle_error <= 10:
            overall_angle_quality = "一般"
        else:
            overall_angle_quality = "较差"
        report_lines.append(f"- **角度测量总体质量**: {overall_angle_quality}")
    
    # 推荐改进建议
    report_lines.extend([
        "",
        "## 改进建议",
    ])
    
    if distance_errors and np.mean(distance_errors) > 0.05:
        report_lines.append("- **距离测量**: 建议检查传感器校准和环境干扰因素")
    
    if angle_errors and np.mean(angle_errors) > 5:
        report_lines.append("- **角度测量**: 建议检查角度传感器精度和安装位置")
    
    if overall_anomaly_rate > 0.1:
        report_lines.append("- **异常率偏高**: 建议检查数据采集环境和设备稳定性")
    
    if not (distance_errors and angle_errors):
        report_lines.append("- **数据完整性**: 部分文件缺少真值信息，建议检查文件命名规范")
    
    report_lines.extend([
        "",
        "## 详细报告",
        f"- 每个文件的详细准度分析报告请查看 `accuracy_reports` 目录下的对应 `.md` 文件",
        f"- 详细数据分析请查看对应的 `*_accuracy_detail.csv` 文件",
        f"- 总体摘要数据已保存到: `{summary_csv_path.name}`",
        "",
        "---",
        "*本报告由UWB数据分析管道自动生成*"
    ])
    
    summary_md_path.write_text('\n'.join(report_lines), encoding='utf-8')


def overall_analysis(stats_rows: list, raw_series_pool: dict, cfg: dict):
    # 汇总CSV（按文件）
    df_stats = pd.DataFrame(stats_rows)
    df_stats.to_csv(OVERALL_DIR / 'per_file_summary.csv', index=False)

    # 全体样本的距离与角度分布（拼接）
    dist_all = pd.concat(raw_series_pool['distance'], ignore_index=True) if raw_series_pool['distance'] else pd.Series(dtype=float)
    ang_all = pd.concat(raw_series_pool['angle'], ignore_index=True) if raw_series_pool['angle'] else pd.Series(dtype=float)

    dist_overall = series_stats(dist_all)
    ang_overall = series_stats(ang_all)

    # 汇总CSV（总体原始）
    overall_row = {
        'distance_mean_m': dist_overall['mean'],
        'distance_std_m': dist_overall['std'],
        'distance_max_m': dist_overall['max'],
        'distance_min_m': dist_overall['min'],
        'angle_mean_deg': ang_overall['mean'],
        'angle_std_deg': ang_overall['std'],
        'angle_max_deg': ang_overall['max'],
        'angle_min_deg': ang_overall['min'],
        'generated_at_iso': datetime.now().isoformat(timespec='seconds'),
    }
    pd.DataFrame([overall_row]).to_csv(OVERALL_DIR / 'overall_summary.csv', index=False)

    # 差值与相对误差总体分布
    dist_abs_all = pd.concat(raw_series_pool['dist_abs_diff_m'], ignore_index=True) if raw_series_pool['dist_abs_diff_m'] else pd.Series(dtype=float)
    ang_abs_all = pd.concat(raw_series_pool['angle_abs_diff_deg'], ignore_index=True) if raw_series_pool['angle_abs_diff_deg'] else pd.Series(dtype=float)
    dist_rel_all = pd.concat(raw_series_pool['dist_rel_err_pct'], ignore_index=True) if raw_series_pool['dist_rel_err_pct'] else pd.Series(dtype=float)
    ang_rel_all = pd.concat(raw_series_pool['angle_rel_err_pct'], ignore_index=True) if raw_series_pool['angle_rel_err_pct'] else pd.Series(dtype=float)

    def stats_with_median(s: pd.Series):
        s = s.dropna().astype(float)
        if s.empty:
            return {'mean': np.nan, 'std': np.nan, 'min': np.nan, 'max': np.nan, 'median': np.nan}
        return {
            'mean': float(s.mean()),
            'std': float(s.std(ddof=1)) if len(s) > 1 else 0.0,
            'min': float(s.min()),
            'max': float(s.max()),
            'median': float(s.median()),
        }

    dist_abs_overall = stats_with_median(dist_abs_all)
    ang_abs_overall = stats_with_median(ang_abs_all)
    dist_rel_overall = stats_with_median(dist_rel_all)
    ang_rel_overall = stats_with_median(ang_rel_all)

    overall_diff_row = {
        'distance_abs_diff_m_mean': dist_abs_overall['mean'],
        'distance_abs_diff_m_std': dist_abs_overall['std'],
        'distance_abs_diff_m_min': dist_abs_overall['min'],
        'distance_abs_diff_m_max': dist_abs_overall['max'],
        'distance_abs_diff_m_median': dist_abs_overall['median'],
        'angle_abs_diff_deg_mean': ang_abs_overall['mean'],
        'angle_abs_diff_deg_std': ang_abs_overall['std'],
        'angle_abs_diff_deg_min': ang_abs_overall['min'],
        'angle_abs_diff_deg_max': ang_abs_overall['max'],
        'angle_abs_diff_deg_median': ang_abs_overall['median'],
        'distance_rel_error_pct_mean': dist_rel_overall['mean'],
        'distance_rel_error_pct_std': dist_rel_overall['std'],
        'distance_rel_error_pct_min': dist_rel_overall['min'],
        'distance_rel_error_pct_max': dist_rel_overall['max'],
        'distance_rel_error_pct_median': dist_rel_overall['median'],
        'angle_rel_error_pct_mean': ang_rel_overall['mean'],
        'angle_rel_error_pct_std': ang_rel_overall['std'],
        'angle_rel_error_pct_min': ang_rel_overall['min'],
        'angle_rel_error_pct_max': ang_rel_overall['max'],
        'angle_rel_error_pct_median': ang_rel_overall['median'],
        'generated_at_iso': datetime.now().isoformat(timespec='seconds'),
    }
    pd.DataFrame([overall_diff_row]).to_csv(OVERALL_DIR / 'overall_diff_summary.csv', index=False)

    # PDF报告：原始分布 + 差值/误差分布与箱线图
    with PdfPages(OVERALL_DIR / 'overall_summary.pdf') as pdf:
        # 距离样本分布
        plt.figure(figsize=(8,5))
        plt.hist(dist_all.dropna().astype(float), bins=80, color='steelblue', edgecolor='black')
        plt.title('Distance (m) Distribution - All Samples')
        plt.xlabel('Distance (m)')
        plt.ylabel('Count')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 角度样本分布
        plt.figure(figsize=(8,5))
        plt.hist(ang_all.dropna().astype(float), bins=80, color='darkorange', edgecolor='black')
        plt.title('Angle (deg) Distribution - All Samples')
        plt.xlabel('Angle (deg)')
        plt.ylabel('Count')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 每文件距离均值分布
        if 'distance_mean_m' in df_stats.columns and not df_stats['distance_mean_m'].dropna().empty:
            plt.figure(figsize=(8,5))
            plt.hist(df_stats['distance_mean_m'].dropna().astype(float), bins=50, color='slateblue', edgecolor='black')
            plt.title('Per-File Distance Mean (m)')
            plt.xlabel('Distance mean (m)')
            plt.ylabel('Count of files')
            plt.grid(True, alpha=0.3)
            pdf.savefig(); plt.close()

        # 每文件角度均值分布
        if 'angle_mean_deg' in df_stats.columns and not df_stats['angle_mean_deg'].dropna().empty:
            plt.figure(figsize=(8,5))
            plt.hist(df_stats['angle_mean_deg'].dropna().astype(float), bins=50, color='sandybrown', edgecolor='black')
            plt.title('Per-File Angle Mean (deg)')
            plt.xlabel('Angle mean (deg)')
            plt.ylabel('Count of files')
            plt.grid(True, alpha=0.3)
            pdf.savefig(); plt.close()

        # 指标摘要页
        fig, ax = plt.subplots(figsize=(8.5, 6))
        ax.axis('off')
        text = [
            f"Generated at: {overall_row['generated_at_iso']}",
            f"Distance overall -> mean: {dist_overall['mean']:.4f} m, std: {dist_overall['std']:.4f} m, min: {dist_overall['min']:.4f} m, max: {dist_overall['max']:.4f} m",
            f"Angle overall -> mean: {ang_overall['mean']:.3f} deg, std: {ang_overall['std']:.3f} deg, min: {ang_overall['min']:.3f} deg, max: {ang_overall['max']:.3f} deg",
            f"Files analyzed: {len(stats_rows)}",
        ]
        ax.text(0.05, 0.9, 'UWB Overall Statistics', fontsize=14, fontweight='bold')
        for i, line in enumerate(text):
            ax.text(0.05, 0.8 - i*0.08, line, fontsize=11)
        pdf.savefig(); plt.close()

        # 差值直方图（距离）
        plt.figure(figsize=(8,5))
        plt.hist(dist_abs_all.dropna().astype(float), bins=80, color='teal', edgecolor='black')
        plt.title('Distance Absolute Difference (m) - All Samples')
        plt.xlabel('Abs diff (m)')
        plt.ylabel('Count')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 差值直方图（角度）
        plt.figure(figsize=(8,5))
        plt.hist(ang_abs_all.dropna().astype(float), bins=80, color='tomato', edgecolor='black')
        plt.title('Angle Absolute Difference (deg) - All Samples')
        plt.xlabel('Abs diff (deg)')
        plt.ylabel('Count')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 相对误差直方图（距离）
        plt.figure(figsize=(8,5))
        plt.hist(dist_rel_all.dropna().astype(float), bins=80, color='seagreen', edgecolor='black')
        plt.title('Distance Relative Error (ratio) - All Samples')
        plt.xlabel('Relative error (ratio)')
        plt.ylabel('Count')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 相对误差直方图（角度）
        plt.figure(figsize=(8,5))
        plt.hist(ang_rel_all.dropna().astype(float), bins=80, color='orchid', edgecolor='black')
        plt.title('Angle Relative Error (ratio) - All Samples')
        plt.xlabel('Relative error (ratio)')
        plt.ylabel('Count')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 箱线图（差值）
        plt.figure(figsize=(8,5))
        plt.boxplot([dist_abs_all.dropna().astype(float), ang_abs_all.dropna().astype(float)])
        plt.xticks([1, 2], ['Dist abs (m)', 'Angle abs (deg)'])
        plt.title('Absolute Differences Boxplot - All Samples')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 箱线图（相对误差）
        plt.figure(figsize=(8,5))
        plt.boxplot([dist_rel_all.dropna().astype(float), ang_rel_all.dropna().astype(float)])
        plt.xticks([1, 2], ['Dist rel', 'Angle rel'])
        plt.title('Relative Errors Boxplot - All Samples')
        plt.grid(True, alpha=0.3)
        pdf.savefig(); plt.close()

        # 差值统计摘要页
        fig, ax = plt.subplots(figsize=(8.5, 7))
        ax.axis('off')
        anomalies_sum = int(df_stats['anomaly_count'].sum()) if ('anomaly_count' in df_stats.columns) else 0
        text2 = [
            f"Distance abs diff -> mean: {overall_diff_row['distance_abs_diff_m_mean']:.4f} m, std: {overall_diff_row['distance_abs_diff_m_std']:.4f} m, min: {overall_diff_row['distance_abs_diff_m_min']:.4f} m, max: {overall_diff_row['distance_abs_diff_m_max']:.4f} m, median: {overall_diff_row['distance_abs_diff_m_median']:.4f} m",
            f"Angle abs diff -> mean: {overall_diff_row['angle_abs_diff_deg_mean']:.3f} deg, std: {overall_diff_row['angle_abs_diff_deg_std']:.3f} deg, min: {overall_diff_row['angle_abs_diff_deg_min']:.3f} deg, max: {overall_diff_row['angle_abs_diff_deg_max']:.3f} deg, median: {overall_diff_row['angle_abs_diff_deg_median']:.3f} deg",
            f"Distance relative error -> mean: {overall_diff_row['distance_rel_error_pct_mean']:.4f}, std: {overall_diff_row['distance_rel_error_pct_std']:.4f}, min: {overall_diff_row['distance_rel_error_pct_min']:.4f}, max: {overall_diff_row['distance_rel_error_pct_max']:.4f}, median: {overall_diff_row['distance_rel_error_pct_median']:.4f}",
            f"Angle relative error -> mean: {overall_diff_row['angle_rel_error_pct_mean']:.4f}, std: {overall_diff_row['angle_rel_error_pct_std']:.4f}, min: {overall_diff_row['angle_rel_error_pct_min']:.4f}, max: {overall_diff_row['angle_rel_error_pct_max']:.4f}, median: {overall_diff_row['angle_rel_error_pct_median']:.4f}",
            f"Anomaly thresholds: dist_abs>{cfg['thresholds']['dist_abs_diff_thresh_m']}m | dist_rel>{cfg['thresholds']['dist_rel_err_thresh']} | angle_abs>{cfg['thresholds']['angle_abs_diff_thresh_deg']}deg | angle_rel>{cfg['thresholds']['angle_rel_err_thresh']}",
            f"Total anomalies (sum of per-file): {anomalies_sum}",
        ]
        ax.text(0.05, 0.95, 'UWB Differences & Errors Summary', fontsize=14, fontweight='bold')
        for i, line in enumerate(text2):
            ax.text(0.05, 0.88 - i*0.08, line, fontsize=11)
        pdf.savefig(); plt.close()

    # 生成统计指标说明文档
    write_diff_stats_doc(cfg)


def run_self_tests() -> bool:
    ensure_dirs()
    OVERALL_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    def record(name: str, ok: bool, detail: str = ''):
        results.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})

    try:
        r = parse_truth_from_filename(Path('50_30_25_0.mcap'))
        ok = (abs(r['truth_distance_m'] - 0.5) < 1e-12) and (abs(r['truth_angle_deg'] - 30.0) < 1e-12) and (abs(r['truth_height_cm'] - 25.0) < 1e-12)
        record('parse_truth: 50_30_25_0', ok, str(r))
    except Exception as e:
        record('parse_truth: 50_30_25_0', False, str(e))

    try:
        r = parse_truth_from_filename(Path('100_-10_0_0.mcap'))
        ok = abs(r['truth_angle_deg'] - 350.0) < 1e-12
        record('parse_truth: normalize angle', ok, str(r))
    except Exception as e:
        record('parse_truth: normalize angle', False, str(e))

    try:
        r = parse_truth_from_filename(Path('badname.mcap'))
        ok = np.isnan(r['truth_distance_m']) and np.isnan(r['truth_angle_deg'])
        record('parse_truth: invalid name', ok, str(r))
    except Exception as e:
        record('parse_truth: invalid name', False, str(e))

    try:
        v = angle_signed_diff_vec(np.array([359.0, 1.0, 181.0]), 1.0)
        ok = (abs(v[0] - (-2.0)) < 1e-12) and (abs(v[1] - 0.0) < 1e-12) and (abs(v[2] - (-180.0)) < 1e-12)
        record('angle_signed_diff_vec wrap', ok, f"{v.tolist()}")
    except Exception as e:
        record('angle_signed_diff_vec wrap', False, str(e))

    try:
        meas = pd.Series([10.0, 20.0, 30.0])
        signed = pd.Series(angle_signed_diff_vec(meas, 20.0))
        abs_err = signed.abs()
        ok = (abs(abs_err.mean() - (20.0 / 3.0)) < 1e-12) and (abs(abs_err.max() - 10.0) < 1e-12)
        record('angle_error stats basic', ok, f"mean={abs_err.mean()}, max={abs_err.max()}, std={abs_err.std(ddof=1)}")
    except Exception as e:
        record('angle_error stats basic', False, str(e))

    passed = sum(1 for r in results if r['ok'])
    total = len(results)

    report_path = OVERALL_DIR / 'self_test_report.md'
    lines = [
        '# UWB 分析管道自检报告',
        '',
        f"生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"通过: {passed}/{total}",
        '',
        '## 用例结果',
    ]
    for r in results:
        status = 'PASS' if r['ok'] else 'FAIL'
        lines.append(f"- {status}: {r['name']} {(' | ' + r['detail']) if r['detail'] else ''}")
    report_path.write_text('\n'.join(lines), encoding='utf-8')

    return passed == total


def parse_args():
    parser = argparse.ArgumentParser(description='UWB 数据分析管道')
    parser.add_argument('-s', '--source-dir', action='append', default=None, help='源数据目录，可重复指定')
    parser.add_argument('--recursive', action='store_true', help='递归搜索 .mcap')
    parser.add_argument('--topic-name', default=None, help='主题名，例如 /uwb/data')
    parser.add_argument('--distance-unit', choices=['m', 'cm'], default=None, help='距离单位 m 或 cm')
    parser.add_argument('--prefer-filtered', dest='prefer_filtered', action='store_true', help='优先使用 filtered 列')
    parser.add_argument('--no-prefer-filtered', dest='prefer_filtered', action='store_false', help='不优先使用 filtered 列')
    parser.add_argument('--clean', action='store_true', help='运行前清理旧的 raw_data 目录')
    parser.add_argument('--filter-height', type=float, default=None, help='筛选特定高度的数据（单位：厘米），例如 --filter-height 0 只分析高度为0的数据')
    parser.add_argument('--self-test', action='store_true', help='运行自检（不依赖mcap数据），验证文件名解析与角度误差计算')
    parser.set_defaults(prefer_filtered=None)
    return parser.parse_args()


def main():
    print(f"准备分析目录: {ANALYSIS_ROOT}")
    ensure_dirs()

    cfg = load_config()
    args = parse_args()

    if args.self_test:
        ok = run_self_tests()
        print(f"自检报告已生成: {OVERALL_DIR / 'self_test_report.md'}")
        sys.exit(0 if ok else 2)

    if mcap_to_dataframe is None:
        print("错误: 当前环境缺少 MCAP 解析依赖，无法进行数据分析。")
        print(f"导入失败原因: {_MCAP_IMPORT_ERROR}")
        print("请安装依赖后重试：")
        print("  python -m pip install mcap")
        sys.exit(1)

    # 清理旧数据（如果指定）
    if args.clean:
        if RAW_DIR.exists():
            print(f"清理旧的 raw_data 目录: {RAW_DIR}")
            shutil.rmtree(RAW_DIR)
            RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 覆盖配置（可选）
    if args.topic_name:
        cfg['topic_name'] = args.topic_name
    if args.distance_unit:
        cfg['distance_unit'] = args.distance_unit
    if args.prefer_filtered is not None:
        cfg['prefer_filtered'] = args.prefer_filtered

    # 定位原始数据目录并复制到 raw_data
    if args.source_dir:
        source_dirs = []
        invalid_dirs = []
        for p in args.source_dir:
            pp = Path(p).resolve()
            if pp.exists() and pp.is_dir():
                source_dirs.append(pp)
            else:
                invalid_dirs.append(p)
        
        if invalid_dirs:
            print("错误: 以下指定的源目录不存在或不可用:")
            for invalid_dir in invalid_dirs:
                print(f"  -> {invalid_dir}")
            print("请检查路径是否正确，或使用 --help 查看使用说明。")
            sys.exit(1)
    else:
        source_dirs = locate_raw_data_dirs(cfg)
        if not source_dirs:
            print("错误: 未找到任何原始数据源目录。")
            print("请使用 --source-dir 参数指定数据源目录，或检查默认配置。")
            sys.exit(1)

    recursive_flag = args.recursive or bool(cfg['raw_source_locator'].get('recursive', False))
    src_files = copy_mcap_to_raw(source_dirs, recursive=recursive_flag)
    print(f"已复制/就绪 .mcap 文件数: {len(src_files)}")

    # 遍历 raw_data 下每个文件夹进行统计
    stats_rows = []
    accuracy_reports = []
    raw_series_pool = {'distance': [], 'angle': [], 'dist_abs_diff_m': [], 'angle_abs_diff_deg': [], 'dist_rel_err_pct': [], 'angle_rel_err_pct': []}

    # 高度筛选计数器
    total_files = 0
    filtered_files = 0
    
    for folder in sorted(RAW_DIR.iterdir()):
        if not folder.is_dir():
            continue
        mcap_files = list(folder.glob('*.mcap'))
        if not mcap_files:
            log_error('missing_mcap', folder.name, '该文件夹下未发现 .mcap 文件')
            print(f"警告: {folder.name} 下未发现 .mcap 文件")
            continue
        # 约定每文件夹仅一个 .mcap
        mcap_path = mcap_files[0]
        total_files += 1
        
        # 高度筛选逻辑
        if args.filter_height is not None:
            truth = parse_truth_from_filename(mcap_path)
            file_height = truth.get('truth_height_cm', np.nan)
            if np.isnan(file_height) or file_height != args.filter_height:
                print(f"跳过: {mcap_path.name} (高度: {file_height}cm, 筛选条件: {args.filter_height}cm)")
                continue
        
        filtered_files += 1
        print(f"处理: {mcap_path.name}")
        row = process_one_file(mcap_path, cfg)
        stats_rows.append(row)
        
        # 生成单独的准度分析报告
        try:
            df = mcap_to_dataframe(mcap_path, topic_name=str(cfg.get('topic_name', '/uwb/data')))
            if not df.empty:
                accuracy_report = generate_individual_accuracy_report(mcap_path, df, cfg)
                accuracy_reports.append(accuracy_report)
                print(f"  ✓ 准度报告已生成: {Path(accuracy_report['report_path']).name}")
        except Exception as e:
            log_error('accuracy_report', str(mcap_path), f'生成准度报告失败: {e}')
            print(f"  ⚠ 准度报告生成失败: {e}")

        # 汇总原始与差值序列（用于总体分布）
        try:
            df = mcap_to_dataframe(mcap_path, topic_name=str(cfg.get('topic_name', '/uwb/data')))
            if not df.empty:
                dist_m = distance_series_m(df, cfg).astype(float)
                ang_deg = angle_series(df, cfg).astype(float)
                raw_series_pool['distance'].append(dist_m)
                raw_series_pool['angle'].append(ang_deg)

                truth = parse_truth_from_filename(mcap_path)
                td = float(truth['truth_distance_m']) if not np.isnan(truth['truth_distance_m']) else np.nan
                ta = float(truth['truth_angle_deg']) if not np.isnan(truth['truth_angle_deg']) else np.nan
                eps_distance = float(cfg['thresholds'].get('eps_distance', EPS_DISTANCE))
                eps_angle = float(cfg['thresholds'].get('eps_angle', EPS_ANGLE))
                if not np.isnan(td):
                    dist_abs = (dist_m - td).abs()
                    raw_series_pool['dist_abs_diff_m'].append(dist_abs)
                    raw_series_pool['dist_rel_err_pct'].append(dist_abs / max(eps_distance, abs(td)))
                if not np.isnan(ta):
                    ang_abs = pd.Series(np.abs(angle_signed_diff_vec(ang_deg, ta)), index=ang_deg.index)
                    raw_series_pool['angle_abs_diff_deg'].append(ang_abs)
                    raw_series_pool['angle_rel_err_pct'].append(ang_abs / max(eps_angle, abs(ta)))
        except Exception as e:
            log_error('aggregate_series', str(mcap_path), f'汇总序列失败: {e}')

    # 输出每文件 CSV
    save_per_file_stats(stats_rows)

    # 整体统计与PDF（含差值与误差）
    overall_analysis(stats_rows, raw_series_pool, cfg)

    # 生成总体准度分析报告
    if accuracy_reports:
        generate_overall_accuracy_summary(accuracy_reports, cfg)
        print(f"✓ 总体准度分析报告已生成")

    # 输出筛选统计信息
    if args.filter_height is not None:
        print(f"\n📊 高度筛选统计:")
        print(f"  总文件数: {total_files}")
        print(f"  筛选条件: 高度 = {args.filter_height}cm")
        print(f"  符合条件: {filtered_files}")
        print(f"  跳过文件: {total_files - filtered_files}")
        if total_files > 0:
            print(f"  筛选比例: {filtered_files/total_files*100:.1f}%")
        else:
            print(f"  筛选比例: 无文件可处理")
    else:
        print(f"\n📊 处理统计: 共处理 {filtered_files} 个文件")

    # 输出错误日志汇总
    if ERRORS:
        err_df = pd.DataFrame(ERRORS)
        err_df.to_csv(OVERALL_DIR / 'processing_errors.csv', index=False)
        print(f"⚠ 处理过程中发生 {len(ERRORS)} 个问题，详见: {OVERALL_DIR / 'processing_errors.csv'}")

    print(f"✓ 每文件统计已保存至: {PER_FILE_DIR}")
    print(f"✓ 总体汇总已保存至: {OVERALL_DIR}")
    if accuracy_reports:
        print(f"✓ 准度分析报告已保存至: {RESULT_DIR / 'accuracy_reports'}")
        print(f"  - 单独报告数量: {len(accuracy_reports)}")
        print(f"  - 总体摘要报告: overall_accuracy_summary.md")


if __name__ == '__main__':
    main()