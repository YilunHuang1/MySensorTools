"""
uwb/visualization.py — Visualization helpers for UWB positioning data.
"""

from typing import Dict, List, Optional, Sequence

import matplotlib
import matplotlib.pyplot as plt

from uwb.data_parser import UWBRecord

matplotlib.use("Agg")


def plot_trajectory_2d(
    records: Sequence[UWBRecord],
    title: str = "UWB Tag Trajectory (top-down)",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot the 2-D (X-Y) trajectory of a single UWB tag."""
    xs = [r.x for r in records]
    ys = [r.y for r in records]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot(xs, ys, "-o", markersize=3, linewidth=1, alpha=0.8)
    if records:
        ax.plot(xs[0], ys[0], "gs", markersize=8, label="Start")
        ax.plot(xs[-1], ys[-1], "r^", markersize=8, label="End")
    tag_id = records[0].tag_id if records else ""
    ax.set_title(f"{title} — Tag {tag_id}")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_multi_tag_trajectories(
    tag_groups: Dict[str, List[UWBRecord]],
    title: str = "UWB Multi-Tag Trajectories",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot 2-D trajectories for multiple UWB tags on the same axes."""
    fig, ax = plt.subplots(figsize=(9, 7))
    for tag_id, records in tag_groups.items():
        xs = [r.x for r in records]
        ys = [r.y for r in records]
        ax.plot(xs, ys, "-o", markersize=2, linewidth=1, alpha=0.7, label=tag_id)
    ax.set_title(title)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
