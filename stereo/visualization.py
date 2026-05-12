"""
stereo/visualization.py — Visualization helpers for stereo camera data.
"""

from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from stereo.data_parser import StereoFrame

matplotlib.use("Agg")


def plot_disparity(
    frame: StereoFrame,
    title: str = "Stereo Disparity Map",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot the disparity map of a :class:`StereoFrame`."""
    fig, ax = plt.subplots(figsize=(9, 5))
    im = ax.imshow(frame.disparity, cmap="plasma", aspect="auto")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Disparity (pixels)")
    ax.set_title(f"{title} — t={frame.timestamp:.3f}s")
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_depth(
    frame: StereoFrame,
    title: str = "Stereo Depth Map",
    save_path: Optional[str] = None,
) -> Optional[plt.Figure]:
    """Plot the depth map of a :class:`StereoFrame` (if depth is available)."""
    if frame.depth is None:
        return None
    fig, ax = plt.subplots(figsize=(9, 5))
    im = ax.imshow(frame.depth, cmap="viridis", aspect="auto")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Depth (m)")
    ax.set_title(f"{title} — t={frame.timestamp:.3f}s")
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
