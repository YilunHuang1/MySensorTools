"""
imu/visualization.py — Plotting helpers for IMU data.
"""

from typing import List, Optional, Sequence

import matplotlib
import matplotlib.pyplot as plt

from imu.data_parser import IMURecord

matplotlib.use("Agg")


def plot_accelerometer(
    records: Sequence[IMURecord],
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot accelerometer X/Y/Z vs time."""
    ts = [r.timestamp for r in records]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(ts, [r.acc_x for r in records], label="acc_x")
    ax.plot(ts, [r.acc_y for r in records], label="acc_y")
    ax.plot(ts, [r.acc_z for r in records], label="acc_z")
    ax.set_title("IMU — Accelerometer")
    ax.set_xlabel("Timestamp (s)")
    ax.set_ylabel("Acceleration (m/s²)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_gyroscope(
    records: Sequence[IMURecord],
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot gyroscope X/Y/Z vs time."""
    ts = [r.timestamp for r in records]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(ts, [r.gyro_x for r in records], label="gyro_x")
    ax.plot(ts, [r.gyro_y for r in records], label="gyro_y")
    ax.plot(ts, [r.gyro_z for r in records], label="gyro_z")
    ax.set_title("IMU — Gyroscope")
    ax.set_xlabel("Timestamp (s)")
    ax.set_ylabel("Angular Rate (deg/s)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_orientation(
    records: Sequence[IMURecord],
    save_path: Optional[str] = None,
) -> Optional[plt.Figure]:
    """Plot roll/pitch/yaw vs time (only if present in records)."""
    if not records or records[0].roll is None:
        return None
    ts = [r.timestamp for r in records]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(ts, [r.roll for r in records], label="roll")
    ax.plot(ts, [r.pitch for r in records], label="pitch")
    ax.plot(ts, [r.yaw for r in records], label="yaw")
    ax.set_title("IMU — Orientation (Euler Angles)")
    ax.set_xlabel("Timestamp (s)")
    ax.set_ylabel("Angle (deg)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
