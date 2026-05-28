import argparse
from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def resolve_xy_columns(df: pd.DataFrame, x_col: Optional[str], y_col: Optional[str]) -> Tuple[str, str]:
    candidates = [
        (x_col, y_col),
        ("x_m", "y_m"),
        ("x", "y"),
    ]
    for x_name, y_name in candidates:
        if x_name and y_name and x_name in df.columns and y_name in df.columns:
            return x_name, y_name
    raise ValueError("CSV must contain x/y or x_m/y_m columns, or pass --x-col and --y-col")


def plot_2d(df: pd.DataFrame, x_col: str, y_col: str, output: Optional[str]) -> None:
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.scatter(df[x_col], df[y_col], s=12, alpha=0.75)
    ax.scatter(0, 0, color="black", s=40, label="origin")
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title("UWB XY trajectory")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_aspect("equal", adjustable="box")
    ax.legend()
    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=160)
    else:
        plt.show()


def plot_3d(df: pd.DataFrame, x_col: str, y_col: str, output: Optional[str]) -> None:
    if "pitch" not in df.columns or "原始距离" not in df.columns:
        raise ValueError("3D mode requires columns: pitch, 原始距离")
    pitch_rad = np.radians(df["pitch"])
    z = df["原始距离"] * np.sin(pitch_rad)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(df[x_col], df[y_col], z, s=12, alpha=0.75)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_zlabel("z")
    ax.set_title("UWB 3D trajectory")
    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=160)
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot UWB CSV trajectory data")
    parser.add_argument("csv", help="Input CSV file")
    parser.add_argument("--mode", choices=["2d", "3d"], default="2d")
    parser.add_argument("--x-col", help="X column name")
    parser.add_argument("--y-col", help="Y column name")
    parser.add_argument("-o", "--output", help="Output image path. If omitted, opens an interactive window.")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    df = pd.read_csv(csv_path)
    x_col, y_col = resolve_xy_columns(df, args.x_col, args.y_col)

    if args.mode == "2d":
        plot_2d(df, x_col, y_col, args.output)
    else:
        plot_3d(df, x_col, y_col, args.output)


if __name__ == "__main__":
    main()
