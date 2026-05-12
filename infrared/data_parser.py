"""
infrared/data_parser.py — Parser for infrared (thermal) camera CSV logs.

Expected CSV layout — each row represents one pixel of the temperature matrix:
    timestamp, row, col, temperature_celsius
"""

import csv
from dataclasses import dataclass
from typing import List

import numpy as np

from common.base_parser import BaseDataParser


@dataclass
class InfraredFrame:
    """One infrared (thermal) camera frame."""

    timestamp: float
    temperature: np.ndarray   # 2-D array (H, W), degrees Celsius

    @property
    def shape(self):
        return self.temperature.shape

    @property
    def min_temp(self) -> float:
        return float(np.nanmin(self.temperature))

    @property
    def max_temp(self) -> float:
        return float(np.nanmax(self.temperature))

    @property
    def mean_temp(self) -> float:
        return float(np.nanmean(self.temperature))


class InfraredDataParser(BaseDataParser):
    """Parse infrared temperature data from a CSV file."""

    def parse_csv(self, filepath: str) -> List[InfraredFrame]:
        """Read *filepath* and reconstruct temperature matrices per timestamp."""
        raw: dict = {}
        with open(filepath, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = float(row["timestamp"])
                r = int(row["row"])
                c = int(row["col"])
                temp = float(row["temperature_celsius"])
                if ts not in raw:
                    raw[ts] = {"rows": [], "cols": [], "temps": []}
                raw[ts]["rows"].append(r)
                raw[ts]["cols"].append(c)
                raw[ts]["temps"].append(temp)

        frames = []
        for ts in sorted(raw):
            d = raw[ts]
            rows_arr = np.array(d["rows"])
            cols_arr = np.array(d["cols"])
            H = int(rows_arr.max()) + 1
            W = int(cols_arr.max()) + 1
            mat = np.full((H, W), np.nan)
            mat[rows_arr, cols_arr] = d["temps"]
            frames.append(InfraredFrame(timestamp=ts, temperature=mat))
        return frames

    def from_matrix(self, timestamp: float, temperature: np.ndarray) -> InfraredFrame:
        """Build an :class:`InfraredFrame` directly from a NumPy array (for tests)."""
        return InfraredFrame(timestamp=timestamp, temperature=temperature)
