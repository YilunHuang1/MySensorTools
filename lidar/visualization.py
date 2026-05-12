"""
lidar/visualization.py — Visualization helpers for LiDAR point clouds.
"""

from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from lidar.data_parser import LidarFrame

matplotlib.use("Agg")


def plot_point_cloud(
    frame: LidarFrame,
    color_by: str = "z",
    title: str = "LiDAR Point Cloud (top-down view)",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """2-D top-down scatter plot of a :class:`LidarFrame`.

    Parameters
    ----------
    frame : LidarFrame
    color_by : {'z', 'intensity', 'ring'}
        Channel to use for colour mapping.
    title : str
    save_path : str, optional
        File path to save the figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if frame.num_points == 0:
        fig, ax = plt.subplots()
        ax.set_title(f"{title} — no points")
        return fig

    x = frame.points[:, 0]
    y = frame.points[:, 1]
    z = frame.points[:, 2]

    if color_by == "intensity" and frame.intensity is not None:
        c = frame.intensity
        clabel = "Intensity"
    elif color_by == "ring" and frame.ring is not None:
        c = frame.ring.astype(float)
        clabel = "Ring ID"
    else:
        c = z
        clabel = "Z (m)"

    fig, ax = plt.subplots(figsize=(8, 8))
    sc = ax.scatter(x, y, c=c, s=0.5, cmap="plasma", alpha=0.7)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(clabel)
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_range_distribution(
    frame: LidarFrame,
    bins: int = 60,
    title: str = "LiDAR Range Distribution",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Histogram of point ranges (Euclidean distance from origin)."""
    ranges = np.linalg.norm(frame.points, axis=1)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(ranges, bins=bins, edgecolor="black", alpha=0.7, color="steelblue")
    ax.set_title(title)
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Count")
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
