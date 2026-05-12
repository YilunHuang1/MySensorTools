"""
lidar/data_parser.py — Parser for LiDAR point cloud data.

Supported formats:
  - CSV  (columns: x, y, z [, intensity [, ring]])
  - PCD  (ASCII PCD files, subset of the PCL PCD format)
"""

import csv
import io
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from common.base_parser import BaseDataParser


@dataclass
class LidarFrame:
    """A single LiDAR scan frame (collection of 3-D points)."""

    points: np.ndarray          # shape (N, 3) — x, y, z in metres
    intensity: Optional[np.ndarray] = field(default=None)   # shape (N,)
    ring: Optional[np.ndarray] = field(default=None)        # shape (N,), int
    timestamp: Optional[float] = field(default=None)

    @property
    def num_points(self) -> int:
        return len(self.points)


class LidarDataParser(BaseDataParser):
    """Parse LiDAR data from CSV or ASCII PCD files."""

    def parse_csv(self, filepath: str) -> List[LidarFrame]:
        """Parse a CSV file where each row is one point.

        Expected header: ``x,y,z[,intensity[,ring]]``
        All rows are treated as a single frame.
        """
        xs, ys, zs, ints, rings = [], [], [], [], []
        with open(filepath, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                xs.append(float(row["x"]))
                ys.append(float(row["y"]))
                zs.append(float(row["z"]))
                if "intensity" in row:
                    ints.append(float(row["intensity"]))
                if "ring" in row:
                    rings.append(int(row["ring"]))

        points = np.column_stack([xs, ys, zs])
        frame = LidarFrame(
            points=points,
            intensity=np.array(ints) if ints else None,
            ring=np.array(rings, dtype=int) if rings else None,
        )
        return [frame]

    def parse_pcd(self, filepath: str) -> List[LidarFrame]:
        """Parse an ASCII PCD file into a list of :class:`LidarFrame`.

        Only the ``DATA ascii`` section is supported.  One file → one frame.
        """
        with open(filepath, "r", encoding="utf-8") as fh:
            content = fh.read()
        return self._parse_pcd_text(content)

    def _parse_pcd_text(self, text: str) -> List[LidarFrame]:
        """Internal: parse PCD-formatted text (used in tests)."""
        lines = text.splitlines()
        fields = []
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("FIELDS"):
                fields = stripped.split()[1:]
            if stripped.startswith("DATA"):
                data_start = i + 1
                break

        xs, ys, zs, ints, rings = [], [], [], [], []
        for line in lines[data_start:]:
            line = line.strip()
            if not line:
                continue
            vals = line.split()
            val_map = {f: v for f, v in zip(fields, vals)}
            xs.append(float(val_map.get("x", 0.0)))
            ys.append(float(val_map.get("y", 0.0)))
            zs.append(float(val_map.get("z", 0.0)))
            if "intensity" in val_map:
                ints.append(float(val_map["intensity"]))
            if "ring" in val_map:
                rings.append(int(val_map["ring"]))

        points = np.column_stack([xs, ys, zs]) if xs else np.empty((0, 3))
        frame = LidarFrame(
            points=points,
            intensity=np.array(ints) if ints else None,
            ring=np.array(rings, dtype=int) if rings else None,
        )
        return [frame]

    def parse_file(self, filepath: str) -> List[LidarFrame]:
        """Dispatch to :meth:`parse_pcd` or :meth:`parse_csv` based on extension."""
        if filepath.lower().endswith(".pcd"):
            return self.parse_pcd(filepath)
        return self.parse_csv(filepath)
