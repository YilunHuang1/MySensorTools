"""
infrared/visualization.py — Visualization helpers for infrared / thermal cameras.
"""

from typing import Optional

import matplotlib
import matplotlib.pyplot as plt

from infrared.data_parser import InfraredFrame

matplotlib.use("Agg")


def plot_thermal_image(
    frame: InfraredFrame,
    colormap: str = "inferno",
    title: str = "Infrared Thermal Image",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot the temperature map of an :class:`InfraredFrame`.

    Parameters
    ----------
    frame : InfraredFrame
    colormap : str
        Matplotlib colormap name.  ``'inferno'`` mimics typical thermal camera output.
    title : str
    save_path : str, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(frame.temperature, cmap=colormap, aspect="auto")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Temperature (°C)")
    ax.set_title(f"{title} — t={frame.timestamp:.3f}s | "
                 f"min={frame.min_temp:.1f} max={frame.max_temp:.1f} °C")
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
