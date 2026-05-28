#!/usr/bin/env python3
"""
UWB 轨迹可视化模块（简洁版）

提供核心轨迹显示组件：
- 2D 原始/滤波轨迹对比（线条样式）
- 轻量动画（Matplotlib FuncAnimation）
- GIF 自动保存（自定义帧率与分辨率）
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Tuple, Any, cast

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.widgets import Button


def load_df(csv_path: Path) -> pd.DataFrame:
    """读取CSV为DataFrame。"""
    df = pd.read_csv(csv_path)
    # 兼容字段名称
    for col in ["timestamp_sec", "raw_x_m", "raw_y_m", "filtered_x_m", "filtered_y_m", "z_m_est"]:
        if col not in df.columns:
            df[col] = np.nan
    return df


def plot_raw_vs_filtered_2d(
    df: pd.DataFrame,
    save_path: Optional[Path] = None,
    title: str = "Trajectory: Raw vs Filtered",
    figsize: Tuple[float, float] = (8, 8),
    dpi: int = 150,
 ) -> Tuple[Figure, Axes]:
    """绘制原始与滤波后的2D轨迹对比（线条样式），参考示例风格。"""
    rx = df["raw_x_m"].to_numpy()
    ry = df["raw_y_m"].to_numpy()
    fx = df["filtered_x_m"].to_numpy()
    fy = df["filtered_y_m"].to_numpy()

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.plot(rx, ry, color="gray", linewidth=1.2, alpha=0.7, label="Raw")
    ax.plot(fx, fy, color="royalblue", linewidth=1.8, alpha=0.9, label="Filtered")

    ax.set_title(title)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(loc="upper right")

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
    return fig, ax


def plot_trajectory_3d(
    df: pd.DataFrame,
    use_filtered: bool = True,
    color_by: str = "timestamp_sec",
    mark_key_points: bool = True,
    save_path: Optional[Path] = None,
    title: str = "UWB 3D Trajectory",
 ) -> Tuple[Figure, Axes3D]:
    """使用Matplotlib绘制3D轨迹，颜色按时间渐变。"""
    x_col = "filtered_x_m" if use_filtered else "raw_x_m"
    y_col = "filtered_y_m" if use_filtered else "raw_y_m"
    z_col = "z_m_est"

    x = df[x_col].to_numpy()
    y = df[y_col].to_numpy()
    z = df[z_col].to_numpy()
    c = df[color_by].to_numpy()

    fig = plt.figure(figsize=(9, 7))
    # fig.add_subplot 返回类型为 Axes，但在 projection="3d" 下实际为 Axes3D，这里进行显式类型转换
    ax = cast(Axes3D, fig.add_subplot(111, projection="3d"))
    # 使用 scatter3D 传入 x, y, z，避免类型检查对 zs 的限制
    # 使用 cast(Any, ax).scatter3D 以绕过类型检查器对 3D scatter 的严格签名推断
    sc = cast(Any, ax).scatter3D(x, y, z, c=c, cmap="viridis", s=10)
    cb = fig.colorbar(sc, ax=ax)
    cb.set_label(color_by)

    ax.set_title(title)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z est (m)")
    ax.grid(True, linestyle="--", alpha=0.3)

    if mark_key_points and len(df) > 0:
        ax.scatter3D(x[0], y[0], z[0], marker="*", s=100, color="red")
        ax.scatter3D(x[-1], y[-1], z[-1], marker="X", s=100, color="orange")

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, ax


# 已移除网页交互式绘图函数


# 已移除基于网页的动态轨迹实现


def main():
    parser = argparse.ArgumentParser(description="UWB 轨迹可视化（简洁版）")
    parser.add_argument("csv", help="输入CSV路径")
    parser.add_argument("-o", "--outdir", default="charts", help="输出目录")
    parser.add_argument("--animate", action="store_true", help="显示简洁动画界面（Start/Pause/Save）")
    parser.add_argument("--gif", default="trajectory_anim.gif", help="GIF输出路径（自动保存）")
    parser.add_argument("--fps", type=int, default=20, help="GIF帧率")
    parser.add_argument("--dpi", type=int, default=150, help="输出DPI")
    parser.add_argument("--px-width", type=int, default=800, help="图宽（像素）")
    parser.add_argument("--px-height", type=int, default=800, help="图高（像素）")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    outdir = Path(args.outdir)

    df = load_df(csv_path)
    outdir.mkdir(parents=True, exist_ok=True)

    # 静态对比图（PNG）
    plot_raw_vs_filtered_2d(
        df,
        save_path=outdir / "trajectory_raw_vs_filtered.png",
        figsize=(args.px_width / args.dpi, args.px_height / args.dpi),
        dpi=args.dpi,
    )

    # 动画与GIF保存（自动保存）
    gif_path = outdir / args.gif if not Path(args.gif).is_absolute() else Path(args.gif)
    fig, anim = animate_raw_vs_filtered(
        df,
        fps=args.fps,
        px_width=args.px_width,
        px_height=args.px_height,
        dpi=args.dpi,
        save_gif=gif_path,
    )
    print(f"✓ 静态图: {outdir / 'trajectory_raw_vs_filtered.png'}")
    print(f"✓ GIF 已保存: {gif_path}")

    if args.animate:
        plt.show()

    print("✓ 处理完成")


def animate_raw_vs_filtered(
    df: pd.DataFrame,
    fps: int = 20,
    px_width: int = 800,
    px_height: int = 800,
    dpi: int = 150,
    save_gif: Optional[Path] = None,
    title: str = "Trajectory: Raw vs Filtered",
) -> Tuple[Figure, FuncAnimation]:
    """使用 Matplotlib 轻量动画绘制原始/滤波轨迹，并支持 GIF 保存。"""
    rx = df["raw_x_m"].to_numpy()
    ry = df["raw_y_m"].to_numpy()
    fx = df["filtered_x_m"].to_numpy()
    fy = df["filtered_y_m"].to_numpy()

    figsize = (px_width / dpi, px_height / dpi)
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_title(title)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.grid(True, linestyle="--", alpha=0.3)

    # 预创建线对象
    line_raw, = ax.plot([], [], color="gray", linewidth=1.2, alpha=0.7, label="Raw")
    line_filt, = ax.plot([], [], color="royalblue", linewidth=1.8, alpha=0.9, label="Filtered")
    ax.legend(loc="upper right")

    # 固定视图边界
    all_x = np.concatenate([rx, fx])
    all_y = np.concatenate([ry, fy])
    if np.isfinite(all_x).any() and np.isfinite(all_y).any():
        pad_x = (np.nanmax(all_x) - np.nanmin(all_x)) * 0.05
        pad_y = (np.nanmax(all_y) - np.nanmin(all_y)) * 0.05
        ax.set_xlim(np.nanmin(all_x) - pad_x, np.nanmax(all_x) + pad_x)
        ax.set_ylim(np.nanmin(all_y) - pad_y, np.nanmax(all_y) + pad_y)

    n = len(df)
    def init():
        line_raw.set_data([], [])
        line_filt.set_data([], [])
        return line_raw, line_filt

    def update(i: int):
        line_raw.set_data(rx[: i + 1], ry[: i + 1])
        line_filt.set_data(fx[: i + 1], fy[: i + 1])
        return line_raw, line_filt

    anim = FuncAnimation(fig, update, frames=n, init_func=init, interval=max(1, int(1000 / max(1, fps))), blit=True)

    # 简洁控制按钮
    # add_axes 的 rect 需要元组类型，避免类型检查报错
    ax_start = fig.add_axes((0.78, 0.02, 0.10, 0.05))
    ax_save = fig.add_axes((0.89, 0.02, 0.10, 0.05))
    btn_start = Button(ax_start, "Start/Pause")
    btn_save = Button(ax_save, "Save GIF")

    running = {"state": True}
    def on_start(_):
        if running["state"]:
            anim.event_source.stop()
            running["state"] = False
        else:
            anim.event_source.start()
            running["state"] = True
    btn_start.on_clicked(on_start)

    def on_save(_):
        target = save_gif or Path("trajectory_anim.gif")
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = PillowWriter(fps=fps)
        anim.save(str(target), writer=writer, dpi=dpi)
    btn_save.on_clicked(on_save)

    # 自动保存到指定路径（如提供）
    if save_gif is not None:
        try:
            save_gif.parent.mkdir(parents=True, exist_ok=True)
            writer = PillowWriter(fps=fps)
            anim.save(str(save_gif), writer=writer, dpi=dpi)
        except Exception:
            pass

    return fig, anim

# 入口调用放在文件末尾，确保所有函数已定义
if __name__ == "__main__":
    main()