"""
common/visualization.py — Shared visualization helpers for all sensor modules.
"""

from typing import Optional, Sequence

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")  # Non-interactive backend; call plt.show() or savefig() explicitly


def plot_time_series(
    timestamps: Sequence,
    values: Sequence,
    title: str = "Sensor Time Series",
    xlabel: str = "Time",
    ylabel: str = "Value",
    label: Optional[str] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a single time series.

    Parameters
    ----------
    timestamps : sequence
        X-axis values (time).
    values : sequence
        Y-axis values.
    title : str
        Plot title.
    xlabel, ylabel : str
        Axis labels.
    label : str, optional
        Legend label for the series.
    save_path : str, optional
        If provided, save the figure to this path instead of displaying it.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(timestamps, values, label=label)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if label:
        ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_multi_series(
    timestamps: Sequence,
    series: dict,
    title: str = "Multi-Channel Sensor Data",
    xlabel: str = "Time",
    ylabel: str = "Value",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot multiple time series on the same axes.

    Parameters
    ----------
    timestamps : sequence
        Shared X-axis values.
    series : dict
        Mapping of ``label -> values`` sequence.
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    for lbl, vals in series.items():
        ax.plot(timestamps, vals, label=lbl)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_histogram(
    values: Sequence,
    bins: int = 50,
    title: str = "Value Distribution",
    xlabel: str = "Value",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a histogram for a flat array of values."""
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(values, bins=bins, edgecolor="black", alpha=0.7)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Count")
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_heatmap(
    matrix: np.ndarray,
    title: str = "Heatmap",
    xlabel: str = "Column",
    ylabel: str = "Row",
    colorbar_label: str = "Value",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a 2-D NumPy array as a colour-mapped heatmap."""
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(matrix, aspect="auto", cmap="viridis")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(colorbar_label)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
