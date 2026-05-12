"""
stereo/data_parser.py — Parser for stereo camera disparity/depth CSV logs.

Expected CSV columns:
    timestamp, row, col, disparity [, depth_m]
"""

import csv
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from common.base_parser import BaseDataParser


@dataclass
class StereoFrame:
    """One stereo depth frame."""

    timestamp: float
    disparity: np.ndarray    # 2-D array (H, W)
    depth: Optional[np.ndarray] = field(default=None)  # 2-D array (H, W), metres

    @property
    def shape(self):
        return self.disparity.shape


class StereoDataParser(BaseDataParser):
    """Parse stereo camera disparity data from a CSV file.

    The CSV represents a flat list of per-pixel measurements that are
    re-assembled into 2-D matrices.
    """

    def parse_csv(self, filepath: str) -> List[StereoFrame]:
        """Parse *filepath* and return a list of :class:`StereoFrame`."""
        rows_data: dict = {}
        with open(filepath, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = float(row["timestamp"])
                r = int(row["row"])
                c = int(row["col"])
                disp = float(row["disparity"])
                depth = float(row["depth_m"]) if "depth_m" in row else None
                if ts not in rows_data:
                    rows_data[ts] = {"rows": [], "cols": [], "disp": [], "depth": []}
                rows_data[ts]["rows"].append(r)
                rows_data[ts]["cols"].append(c)
                rows_data[ts]["disp"].append(disp)
                if depth is not None:
                    rows_data[ts]["depth"].append(depth)

        frames = []
        for ts in sorted(rows_data):
            d = rows_data[ts]
            rows_arr = np.array(d["rows"])
            cols_arr = np.array(d["cols"])
            H = int(rows_arr.max()) + 1
            W = int(cols_arr.max()) + 1
            disp_mat = np.full((H, W), np.nan)
            disp_mat[rows_arr, cols_arr] = d["disp"]
            depth_mat = None
            if d["depth"]:
                depth_mat = np.full((H, W), np.nan)
                depth_mat[rows_arr, cols_arr] = d["depth"]
            frames.append(StereoFrame(timestamp=ts, disparity=disp_mat, depth=depth_mat))
        return frames

    def parse_matrix(
        self, timestamp: float, disparity: np.ndarray, depth: Optional[np.ndarray] = None
    ) -> StereoFrame:
        """Build a :class:`StereoFrame` directly from NumPy arrays (useful in tests)."""
        return StereoFrame(timestamp=timestamp, disparity=disparity, depth=depth)
